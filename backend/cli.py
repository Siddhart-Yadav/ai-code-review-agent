"""
CLI entry point for the AI Code Review Agent.
Usage: python cli.py <PR_URL>
"""

import argparse
import asyncio
import json
import sys

import httpx


DEFAULT_API_URL = "http://localhost:8000/api/v1"


async def submit_review(api_url: str, pr_url: str) -> dict:
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{api_url}/reviews",
            json={"pr_url": pr_url, "triggered_by": "cli"},
        )
        response.raise_for_status()
        return response.json()


def format_review(review: dict) -> str:
    lines = [
        f"\n{'='*60}",
        f"  AI CODE REVIEW REPORT",
        f"{'='*60}",
        f"  Repo:           {review.get('repo_full_name', 'N/A')}",
        f"  PR:             #{review.get('pr_number', 'N/A')} — {review.get('pr_title', 'N/A')}",
        f"  Score:           {review.get('overall_score', 'N/A')}/10",
        f"  Recommendation:  {review.get('recommendation', 'N/A')}",
        f"  Files Reviewed:  {review.get('files_reviewed', 0)}",
        f"  Total Issues:    {review.get('total_issues', 0)}",
        f"  Duration:        {review.get('duration_seconds', 0):.1f}s",
        f"{'='*60}",
        f"\n  Summary: {review.get('summary', 'N/A')}",
    ]

    meta = review.get("meta_review", {})
    key_issues = meta.get("key_issues", [])
    positives = meta.get("positive_aspects", [])

    if key_issues:
        lines.append(f"\n  Key Issues:")
        for issue in key_issues:
            lines.append(f"    - {issue}")

    if positives:
        lines.append(f"\n  Positive Aspects:")
        for pos in positives:
            lines.append(f"    + {pos}")

    categories = [
        ("Security", "security_findings"),
        ("Performance", "performance_findings"),
        ("Style", "style_findings"),
        ("Test Coverage", "test_coverage_findings"),
    ]

    for name, key in categories:
        findings = review.get(key, [])
        if findings:
            lines.append(f"\n  {name} ({len(findings)} issues):")
            for f in findings[:5]:
                sev = f.get("severity", "info")
                title = f.get("title", "N/A")
                file = f.get("file", "N/A")
                lines.append(f"    [{sev.upper()}] {title} — {file}")

    lines.append(f"\n{'='*60}\n")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="AI Code Review Agent CLI")
    parser.add_argument("pr_url", help="GitHub PR URL to review")
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"API base URL (default: {DEFAULT_API_URL})",
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()

    print(f"\nSubmitting PR for review: {args.pr_url}")
    print("This may take 1-2 minutes...\n")

    try:
        review = asyncio.run(submit_review(args.api_url, args.pr_url))

        if args.json:
            print(json.dumps(review, indent=2, default=str))
        else:
            print(format_review(review))

    except httpx.HTTPStatusError as e:
        print(f"API Error ({e.response.status_code}): {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.ConnectError:
        print(f"Cannot connect to API at {args.api_url}", file=sys.stderr)
        print("Make sure the backend is running: docker compose up", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
