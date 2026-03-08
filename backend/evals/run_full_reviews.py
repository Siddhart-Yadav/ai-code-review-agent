#!/usr/bin/env python3
"""
Run the FULL AI code review agent on real PRs — LLM, Semgrep, all 4 agents.

Requires: GCP credentials (gcloud auth application-default login),
          backend/.env with GCP_PROJECT_ID, GEMINI_MODEL

Usage:
    cd backend && python -m evals.run_full_reviews freeCodeCamp/freeCodeCamp 3
"""

import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

# Load backend .env before any app imports
backend_dir = Path(__file__).resolve().parent.parent
env_file = backend_dir / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)

# Use localhost for DB/Redis so imports don't fail (we won't connect)
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/code_review")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

sys.path.insert(0, str(backend_dir))

from app.services.github_service import GitHubService
from app.utils.code_parser import parse_unified_diff, chunk_for_agents
from app.agents.graph import review_pipeline


async def run_full_review(pr_url: str) -> dict | None:
    """Run the complete pipeline on a PR. Returns result dict or None on failure."""
    gh = GitHubService()
    try:
        pr_info = await gh.get_pr_info(pr_url)
    except Exception as e:
        print(f"  GitHub fetch failed: {e}")
        return None

    file_diffs = parse_unified_diff(pr_info.diff_text)
    chunks = chunk_for_agents(file_diffs)

    if not chunks:
        return {
            "pr_number": pr_info.pr_number,
            "pr_title": pr_info.title,
            "pr_url": pr_info.url,
            "status": "skipped",
            "reason": "No reviewable chunks",
            "files": len(pr_info.changed_files),
        }

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

    start = time.time()
    try:
        result = await review_pipeline.ainvoke(state)
    except Exception as e:
        import traceback
        traceback.print_exc()
        elapsed = time.time() - start
        return {
            "pr_number": pr_info.pr_number,
            "pr_title": pr_info.title,
            "pr_url": pr_info.url,
            "status": "error",
            "error": str(e),
            "elapsed_seconds": round(elapsed, 1),
        }

    elapsed = time.time() - start
    specialist_results = result.get("specialist_results", [])
    meta = result.get("meta_review", {})

    total_findings = sum(len(r.get("findings", [])) for r in specialist_results)

    return {
        "pr_number": pr_info.pr_number,
        "pr_title": pr_info.title,
        "pr_url": pr_info.url,
        "status": "completed",
        "elapsed_seconds": round(elapsed, 1),
        "files_reviewed": len(pr_info.changed_files),
        "total_findings": total_findings,
        "overall_score": meta.get("overall_score"),
        "recommendation": meta.get("recommendation"),
        "summary": meta.get("summary", "")[:200],
        "security": len(next((r["findings"] for r in specialist_results if r.get("agent_name") == "security"), [])),
        "performance": len(next((r["findings"] for r in specialist_results if r.get("agent_name") == "performance"), [])),
        "style": len(next((r["findings"] for r in specialist_results if r.get("agent_name") == "style"), [])),
        "test_coverage": len(next((r["findings"] for r in specialist_results if r.get("agent_name") == "test_coverage"), [])),
        "semgrep_findings": len(result.get("semgrep_findings", [])),
    }


async def main():
    if len(sys.argv) < 2:
        print("Usage: cd backend && python -m evals.run_full_reviews <owner/repo> [num_prs]")
        print("Example: python -m evals.run_full_reviews freeCodeCamp/freeCodeCamp 3")
        sys.exit(1)

    repo = sys.argv[1]
    num_prs = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    owner, repo_name = repo.split("/")

    print(f"Fetching {num_prs} open PRs from {repo}...")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo_name}/pulls?state=open&per_page={num_prs}",
        headers={"User-Agent": "review-benchmark"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        prs = json.loads(resp.read().decode())

    print(f"\nRunning FULL agent pipeline on {len(prs)} PRs (LLM + Semgrep)...")
    print("This will take ~60-90 seconds per PR.\n")

    results = []
    for i, pr in enumerate(prs):
        url = pr["html_url"]
        print(f"[{i+1}/{len(prs)}] PR #{pr['number']}: {pr['title'][:50]}...")
        result = await run_full_review(url)
        if result:
            results.append(result)
            if result.get("status") == "completed":
                print(f"       → {result['elapsed_seconds']}s | score {result['overall_score']} | "
                      f"{result['total_findings']} findings | {result['recommendation']}")
            else:
                print(f"       → {result.get('status', '?')}: {result.get('reason', result.get('error', ''))[:60]}")
        print()

    # Report
    print("=" * 70)
    print("  FULL AGENT BENCHMARK — Real Reviews from freeCodeCamp/freeCodeCamp")
    print("=" * 70)

    completed = [r for r in results if r.get("status") == "completed"]
    for r in completed:
        print(f"\n  PR #{r['pr_number']}: {r['pr_title'][:55]}")
        print(f"  Time: {r['elapsed_seconds']}s | Score: {r['overall_score']}/10 | "
              f"Findings: {r['total_findings']} (S:{r['security']} P:{r['performance']} St:{r['style']} T:{r['test_coverage']})")
        print(f"  Recommendation: {r['recommendation']}")
        print(f"  Summary: {r['summary'][:120]}...")

    if completed:
        avg_time = sum(r["elapsed_seconds"] for r in completed) / len(completed)
        avg_score = sum(r["overall_score"] or 0 for r in completed) / len(completed)
        total_findings = sum(r["total_findings"] for r in completed)
        print(f"\n  AGGREGATE: {len(completed)} reviews | avg {avg_time:.1f}s | avg score {avg_score:.1f} | {total_findings} total findings")

    out_path = Path(__file__).parent / "full_review_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n  Results saved to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
