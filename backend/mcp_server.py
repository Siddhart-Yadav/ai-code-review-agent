"""
MCP Server for the AI Code Review Agent.

Exposes the code review pipeline as MCP tools that can be used by
Claude Desktop, Cursor, or any MCP-compatible client.

Usage:
  Run standalone:   python mcp_server.py
  With Claude:      Add to claude_desktop_config.json
"""

import asyncio
import json
import logging

from fastmcp import FastMCP

from app.core.config import get_settings
from app.services.github_service import GitHubService, parse_pr_url
from app.utils.code_parser import parse_unified_diff, chunk_for_agents
from app.agents.graph import review_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

mcp = FastMCP(
    "AI Code Review Agent",
    description="Multi-agent AI system that reviews GitHub pull requests for security, performance, style, and test coverage issues.",
)


@mcp.tool
async def review_pull_request(pr_url: str) -> str:
    """Review a GitHub pull request using 4 specialized AI agents (Security, Performance, Style, Test Coverage).

    Takes a GitHub PR URL, fetches the diff, runs parallel agent analysis,
    aggregates findings, and returns a structured review with scores and recommendations.

    Args:
        pr_url: Full GitHub PR URL (e.g. https://github.com/owner/repo/pull/123)
    """
    github = GitHubService()

    logger.info("Fetching PR info for %s", pr_url)
    pr_info = await github.get_pr_info(pr_url)

    file_diffs = parse_unified_diff(pr_info.diff_text)
    chunks = chunk_for_agents(file_diffs)

    if not chunks:
        return json.dumps({
            "status": "completed",
            "summary": "No reviewable code changes found.",
            "overall_score": 10.0,
            "recommendation": "approve",
            "total_issues": 0,
        }, indent=2)

    state = {
        "diff_chunks": chunks,
        "pr_info": {
            "title": pr_info.title,
            "description": pr_info.description,
            "repo_full_name": pr_info.repo_full_name,
            "author": pr_info.author,
            "base_branch": pr_info.base_branch,
            "head_branch": pr_info.head_branch,
        },
        "specialist_results": [],
        "aggregated_result": {},
        "meta_review": {},
        "error": None,
    }

    logger.info("Running review pipeline on %d chunks...", len(chunks))
    result = await review_pipeline.ainvoke(state)

    specialist_results = result.get("specialist_results", [])
    meta = result.get("meta_review", {})

    output = {
        "repo": pr_info.repo_full_name,
        "pr_number": pr_info.pr_number,
        "pr_title": pr_info.title,
        "overall_score": meta.get("overall_score", 5.0),
        "recommendation": meta.get("recommendation", "comment"),
        "risk_assessment": meta.get("risk_assessment", "medium"),
        "summary": meta.get("summary", "Review completed."),
        "key_issues": meta.get("key_issues", []),
        "positive_aspects": meta.get("positive_aspects", []),
        "files_reviewed": len(pr_info.changed_files),
        "agent_results": {
            r["agent_name"]: {
                "findings_count": len(r.get("findings", [])),
                "score": r.get("score", 5.0),
                "top_findings": r.get("findings", [])[:3],
            }
            for r in specialist_results
        },
    }

    return json.dumps(output, indent=2, default=str)


@mcp.tool
async def review_diff(diff_text: str, title: str = "Direct diff review") -> str:
    """Review a raw git diff without needing a GitHub PR URL.

    Useful for reviewing local changes before pushing. Paste the output
    of `git diff` or `git diff --staged` directly.

    Args:
        diff_text: Raw unified diff text (output of git diff)
        title: Optional title/description for context
    """
    file_diffs = parse_unified_diff(diff_text)
    chunks = chunk_for_agents(file_diffs)

    if not chunks:
        return json.dumps({
            "status": "completed",
            "summary": "No reviewable code changes found in the diff.",
            "overall_score": 10.0,
            "recommendation": "approve",
        }, indent=2)

    state = {
        "diff_chunks": chunks,
        "pr_info": {
            "title": title,
            "description": "",
            "repo_full_name": "local",
            "author": "local",
            "base_branch": "main",
            "head_branch": "feature",
        },
        "specialist_results": [],
        "aggregated_result": {},
        "meta_review": {},
        "error": None,
    }

    result = await review_pipeline.ainvoke(state)
    meta = result.get("meta_review", {})
    specialist_results = result.get("specialist_results", [])

    total_issues = sum(len(r.get("findings", [])) for r in specialist_results)

    output = {
        "overall_score": meta.get("overall_score", 5.0),
        "recommendation": meta.get("recommendation", "comment"),
        "summary": meta.get("summary", "Review completed."),
        "key_issues": meta.get("key_issues", []),
        "positive_aspects": meta.get("positive_aspects", []),
        "total_issues": total_issues,
        "findings_by_agent": {
            r["agent_name"]: r.get("findings", [])
            for r in specialist_results
        },
    }

    return json.dumps(output, indent=2, default=str)


@mcp.tool
def get_supported_languages() -> str:
    """List all programming languages the code review agent can analyze."""
    from app.utils.code_parser import LANGUAGE_MAP
    languages = sorted(set(LANGUAGE_MAP.values()))
    return json.dumps({
        "supported_languages": languages,
        "total": len(languages),
        "file_extensions": dict(sorted(LANGUAGE_MAP.items())),
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
