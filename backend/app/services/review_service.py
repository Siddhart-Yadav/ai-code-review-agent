"""
Review orchestration service.
Coordinates GitHub data fetching, caching, diff parsing, and agent pipeline execution.
"""

import time
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.review import Review, ReviewStatus
from app.services.github_service import GitHubService
from app.utils.code_parser import parse_unified_diff, chunk_for_agents
from app.core.cache import compute_diff_hash, get_cached_review, set_cached_review
from app.agents.graph import review_pipeline

logger = logging.getLogger(__name__)


def _extract_agent_findings(results: list[dict], agent_name: str) -> list:
    for r in results:
        if r.get("agent_name") == agent_name:
            return r.get("findings", [])
    return []


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.github = GitHubService()

    async def create_review(self, pr_url: str, triggered_by: str = "web_ui") -> Review:
        pr_info = await self.github.get_pr_info(pr_url)

        diff_hash = compute_diff_hash(pr_info.diff_text)

        # Check DB directly as source of truth (cache is an optimization hint only)
        existing = await self._find_by_diff_hash(diff_hash)
        if existing:
            logger.info("Returning existing review for diff %s", diff_hash[:12])
            return existing

        review = Review(
            repo_full_name=pr_info.repo_full_name,
            pr_number=pr_info.pr_number,
            pr_title=pr_info.title,
            pr_url=pr_info.url,
            commit_sha=pr_info.head_sha,
            diff_hash=diff_hash,
            status=ReviewStatus.IN_PROGRESS,
            triggered_by=triggered_by,
            files_reviewed=len(pr_info.changed_files),
        )
        self.db.add(review)
        await self.db.flush()

        start_time = time.time()

        try:
            file_diffs = parse_unified_diff(pr_info.diff_text)
            chunks = chunk_for_agents(file_diffs)

            if not chunks:
                review.status = ReviewStatus.COMPLETED
                review.summary = "No reviewable code changes found."
                review.overall_score = 10.0
                review.recommendation = "approve"
                review.total_issues = 0
                review.completed_at = datetime.utcnow()
                review.duration_seconds = time.time() - start_time
                await self.db.commit()
                return review

            state = {
                "diff_chunks": chunks,
                "diff_text": pr_info.diff_text,
                "pr_info": {
                    "title": pr_info.title,
                    "description": pr_info.description,
                    "repo_full_name": pr_info.repo_full_name,
                    "author": pr_info.author,
                    "base_branch": pr_info.base_branch,
                    "head_branch": pr_info.head_branch,
                },
                "semgrep_findings": [],
                "specialist_results": [],
                "aggregated_result": {},
                "meta_review": {},
                "error": None,
            }

            result = await review_pipeline.ainvoke(state)

            specialist_results = result.get("specialist_results", [])
            review.security_findings = _extract_agent_findings(specialist_results, "security")
            review.performance_findings = _extract_agent_findings(specialist_results, "performance")
            review.style_findings = _extract_agent_findings(specialist_results, "style")
            review.test_coverage_findings = _extract_agent_findings(specialist_results, "test_coverage")
            review.aggregated_findings = result.get("aggregated_result", {}).get("findings", [])
            review.meta_review = result.get("meta_review", {})

            meta = result.get("meta_review", {})
            review.overall_score = meta.get("overall_score", 5.0)
            review.summary = meta.get("summary", "Review completed.")
            review.recommendation = meta.get("recommendation", "comment")
            review.total_issues = (
                len(review.security_findings)
                + len(review.performance_findings)
                + len(review.style_findings)
                + len(review.test_coverage_findings)
            )
            review.status = ReviewStatus.COMPLETED
            review.completed_at = datetime.utcnow()
            review.duration_seconds = time.time() - start_time

            await set_cached_review(diff_hash, {
                "review_id": str(review.id),
                "overall_score": review.overall_score,
                "recommendation": review.recommendation,
            })

            await self.db.commit()
            logger.info(
                "Review completed for %s#%d: score=%.1f, issues=%d, duration=%.1fs",
                review.repo_full_name, review.pr_number,
                review.overall_score, review.total_issues, review.duration_seconds,
            )
            return review

        except Exception as e:
            review.status = ReviewStatus.FAILED
            review.summary = f"Review failed: {str(e)}"
            review.duration_seconds = time.time() - start_time
            await self.db.commit()
            logger.exception("Review failed for %s: %s", pr_url, e)
            raise

    async def get_review(self, review_id: str) -> Review | None:
        result = await self.db.execute(
            select(Review).where(Review.id == review_id)
        )
        return result.scalar_one_or_none()

    async def list_reviews(
        self, skip: int = 0, limit: int = 20, repo: str | None = None
    ) -> list[Review]:
        query = select(Review).order_by(desc(Review.created_at))
        if repo:
            query = query.where(Review.repo_full_name == repo)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _find_by_diff_hash(self, diff_hash: str) -> Review | None:
        result = await self.db.execute(
            select(Review)
            .where(Review.diff_hash == diff_hash)
            .where(Review.status == ReviewStatus.COMPLETED)
            .order_by(desc(Review.created_at))
            .limit(1)
        )
        return result.scalars().first()

    async def post_review_to_github(self, review: Review) -> None:
        """Post the review summary as a PR comment."""
        if not review.pr_url or not review.meta_review:
            return

        meta = review.meta_review
        score = meta.get("overall_score", "N/A")
        recommendation = meta.get("recommendation", "N/A")
        summary = meta.get("summary", "")
        risk = meta.get("risk_assessment", "N/A")

        key_issues = meta.get("key_issues", [])
        positives = meta.get("positive_aspects", [])

        body = (
            f"## AI Code Review Agent\n\n"
            f"**Score:** {score}/10 | **Recommendation:** {recommendation} | **Risk:** {risk}\n\n"
            f"### Summary\n{summary}\n\n"
        )

        if key_issues:
            body += "### Key Issues\n"
            for issue in key_issues:
                body += f"- {issue}\n"
            body += "\n"

        if positives:
            body += "### Positive Aspects\n"
            for pos in positives:
                body += f"- {pos}\n"
            body += "\n"

        body += (
            f"---\n"
            f"*{review.total_issues} issues found across {review.files_reviewed} files "
            f"in {review.duration_seconds:.1f}s*"
        )

        await self.github.post_review_comment(
            review.repo_full_name,
            review.pr_number,
            body,
            review.commit_sha,
        )
