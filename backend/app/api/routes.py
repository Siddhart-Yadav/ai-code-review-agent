"""
FastAPI API routes for the code review agent.
"""

import hashlib
import hmac
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, Header
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.database import get_db
from app.core.config import get_settings
from app.models.schemas import (
    ReviewRequest,
    ReviewResponse,
    ReviewListItem,
    HealthResponse,
    WebhookPayload,
)
from app.services.review_service import ReviewService
from app.demo.sample_reviews import get_demo_review, get_demo_reviews_list, DEMO_REVIEWS
from app.core.rate_limit import review_rate_limiter

settings = get_settings()
router = APIRouter()


# ── Demo endpoints (no DB, no LLM — works without any API key) ───────────


@router.get("/demo/reviews")
async def list_demo_reviews():
    """List pre-computed demo reviews. No API key or database required."""
    return get_demo_reviews_list()


@router.get("/demo/reviews/{review_id}")
async def get_demo_review_endpoint(review_id: str):
    """Get a single demo review by ID. No API key or database required."""
    review = get_demo_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Demo review not found")
    return review


@router.get("/demo/status")
async def demo_status():
    """Check whether the app is in demo mode (no LLM configured)."""
    return {
        "demo_mode": settings.DEMO_MODE,
        "llm_configured": settings.llm_configured,
        "llm_provider": settings.LLM_PROVIDER if settings.llm_configured else None,
        "available_demo_reviews": len(DEMO_REVIEWS),
    }


@router.get("/health", response_model=HealthResponse)
async def health_check():
    db_status = "connected"
    redis_status = "connected"

    try:
        from app.core.database import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_status = "disconnected"

    try:
        from app.core.cache import redis_client
        await redis_client.ping()
    except Exception:
        redis_status = "disconnected"

    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        database=db_status,
        redis=redis_status,
    )


@router.post("/reviews", response_model=ReviewResponse, status_code=201)
async def create_review(
    request: ReviewRequest,
    raw_request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    # Rate limit: 5 reviews/hour per IP (protects hosted Groq key)
    review_rate_limiter.check(raw_request)

    service = ReviewService(db)

    try:
        review = await service.create_review(
            pr_url=request.pr_url,
            triggered_by=request.triggered_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("Unexpected error creating review: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")

    background_tasks.add_task(service.post_review_to_github, review)

    return _review_to_response(review)


@router.get("/reviews", response_model=list[ReviewListItem])
async def list_reviews(
    skip: int = 0,
    limit: int = 20,
    repo: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    service = ReviewService(db)
    reviews = await service.list_reviews(skip=skip, limit=limit, repo=repo)
    return [
        ReviewListItem(
            id=str(r.id),
            repo_full_name=r.repo_full_name,
            pr_number=r.pr_number,
            pr_title=r.pr_title,
            status=r.status.value if r.status else "unknown",
            overall_score=r.overall_score,
            recommendation=r.recommendation,
            total_issues=r.total_issues or 0,
            created_at=r.created_at,
        )
        for r in reviews
    ]


@router.get("/reviews/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: str,
    db: AsyncSession = Depends(get_db),
):
    # Check demo reviews first (works without DB)
    if review_id.startswith("demo-"):
        demo = get_demo_review(review_id)
        if demo:
            return demo
        raise HTTPException(status_code=404, detail="Demo review not found")

    service = ReviewService(db)
    review = await service.get_review(review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return _review_to_response(review)


@router.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    if not settings.GITHUB_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=403,
            detail="Webhook secret not configured. Set GITHUB_WEBHOOK_SECRET to enable webhooks.",
        )

    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    expected = "sha256=" + hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "event": x_github_event}

    try:
        payload = WebhookPayload(**(await request.json()))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    if payload.action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "action": payload.action}

    pr_url = payload.pull_request.get("html_url")

    if not pr_url:
        raise HTTPException(status_code=400, detail="Missing PR URL in payload")

    service = ReviewService(db)
    background_tasks.add_task(
        _run_webhook_review, service, pr_url
    )

    return {"status": "accepted", "pr_url": pr_url}


async def _run_webhook_review(service: ReviewService, pr_url: str):
    try:
        review = await service.create_review(pr_url=pr_url, triggered_by="github_webhook")
        await service.post_review_to_github(review)
    except Exception as e:
        logger.exception("Webhook review failed for %s: %s", pr_url, e)
        # create_review already persists FAILED status to DB — no additional handling needed


def _review_to_response(review) -> ReviewResponse:
    return ReviewResponse(
        id=str(review.id),
        repo_full_name=review.repo_full_name,
        pr_number=review.pr_number,
        pr_title=review.pr_title,
        pr_url=review.pr_url,
        status=review.status.value if review.status else "unknown",
        overall_score=review.overall_score,
        summary=review.summary,
        recommendation=review.recommendation,
        security_findings=review.security_findings or [],
        performance_findings=review.performance_findings or [],
        style_findings=review.style_findings or [],
        test_coverage_findings=review.test_coverage_findings or [],
        meta_review=review.meta_review or {},
        files_reviewed=review.files_reviewed or 0,
        total_issues=review.total_issues or 0,
        created_at=review.created_at,
        completed_at=review.completed_at,
        duration_seconds=review.duration_seconds,
        triggered_by=review.triggered_by,
    )
