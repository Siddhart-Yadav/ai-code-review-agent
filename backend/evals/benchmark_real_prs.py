#!/usr/bin/env python3
"""
Run context precision benchmark on real PRs from a given repo.

Fetches diffs via GitHub API, runs naive vs semantic chunking, reports numbers.

Usage:
    python -m evals.benchmark_real_prs freeCodeCamp/freeCodeCamp 5
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.code_parser import (
    parse_unified_diff,
    chunk_for_agents,
    should_skip_file,
    detect_language,
    _file_priority,
)


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def fetch_pr_diff(owner: str, repo: str, pr_number: int) -> str | None:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    req = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github.v3.diff", "User-Agent": "benchmark-script"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Failed to fetch PR #{pr_number}: {e}")
        return None


def naive_chunk(diff_text: str, max_chunk_size: int = 8000) -> list[dict]:
    lines = diff_text.split("\n")
    chunks = []
    current_lines = []
    current_size = 0
    current_file = "unknown"

    for line in lines:
        if line.startswith("+++ b/"):
            current_file = line[6:]
        current_lines.append(line)
        current_size += len(line) + 1
        if current_size >= max_chunk_size:
            content = "\n".join(current_lines)
            chunks.append({
                "file_path": current_file,
                "tokens": _estimate_tokens(content),
                "skippable": should_skip_file(current_file),
            })
            current_lines = []
            current_size = 0

    if current_lines:
        content = "\n".join(current_lines)
        chunks.append({
            "file_path": current_file,
            "tokens": _estimate_tokens(content),
            "skippable": should_skip_file(current_file),
        })

    return chunks


def _count_relevant_tokens(diff_text: str) -> tuple[int, int]:
    """Relevant = tokens from files we DON'T skip (reviewable). Noise = skipped files (lock, minified, etc)."""
    lines = diff_text.split("\n")
    current_file = "unknown"
    relevant, noise = 0, 0

    for line in lines:
        if line.startswith("+++ b/"):
            current_file = line[6:]
        t = _estimate_tokens(line)
        if should_skip_file(current_file):
            noise += t
        else:
            relevant += t

    return relevant, noise


def run_benchmark_on_diff(diff_text: str, pr_number: int, pr_title: str) -> dict | None:
    if not diff_text or len(diff_text) < 100:
        return None

    file_diffs = parse_unified_diff(diff_text)
    smart_chunks = chunk_for_agents(file_diffs)

    # Naive stats
    naive_chunks = naive_chunk(diff_text)
    naive_tokens = sum(c["tokens"] for c in naive_chunks)
    naive_skippable = sum(1 for c in naive_chunks if c["skippable"])
    relevant_t, noise_t = _count_relevant_tokens(diff_text)
    total_t = relevant_t + noise_t
    naive_precision = round(relevant_t / total_t * 100, 1) if total_t else 0

    # Smart stats — we only send non-skipped files, so precision = 100% by design
    smart_tokens = 0
    scoped = 0
    for chunk in smart_chunks:
        for hunk in chunk.get("hunks", []):
            smart_tokens += _estimate_tokens(hunk.get("content", ""))
        if chunk.get("scope_name"):
            scoped += 1

    smart_precision = 100.0 if smart_chunks else 0.0  # all chunks are from reviewable files
    scope_rate = round(scoped / len(smart_chunks) * 100, 1) if smart_chunks else 0

    skipped = [fd.path for fd in file_diffs if should_skip_file(fd.path)]

    return {
        "pr_number": pr_number,
        "pr_title": pr_title[:60],
        "diff_lines": len(diff_text.split("\n")),
        "total_files": len(file_diffs),
        "skipped_files": len(skipped),
        "skipped_names": skipped[:5],
        "naive": {
            "chunks": len(naive_chunks),
            "tokens": naive_tokens,
            "precision": naive_precision,
            "chunks_with_junk": naive_skippable,
        },
        "smart": {
            "chunks": len(smart_chunks),
            "tokens": smart_tokens,
            "precision": smart_precision,
            "scoped_chunks_pct": scope_rate,
        },
        "improvement": {
            "precision_gain": round(smart_precision - naive_precision, 1),
            "token_savings": naive_tokens - smart_tokens,
            "token_savings_pct": round((naive_tokens - smart_tokens) / naive_tokens * 100, 1) if naive_tokens else 0,
        },
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m evals.benchmark_real_prs <owner/repo> [num_prs]")
        print("Example: python -m evals.benchmark_real_prs freeCodeCamp/freeCodeCamp 5")
        sys.exit(1)

    repo = sys.argv[1]
    num_prs = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    owner, repo_name = repo.split("/")

    print(f"Fetching {num_prs} open PRs from {repo}...")
    req = urllib.request.Request(
        f"https://api.github.com/repos/{owner}/{repo_name}/pulls?state=open&per_page={num_prs}",
        headers={"User-Agent": "benchmark-script"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        prs = json.loads(resp.read().decode())

    results = []
    for pr in prs:
        num = pr["number"]
        title = pr["title"]
        print(f"  Fetching PR #{num}: {title[:50]}...")
        diff = fetch_pr_diff(owner, repo_name, num)
        if diff:
            r = run_benchmark_on_diff(diff, num, title)
            if r:
                results.append(r)

    if not results:
        print("No valid PRs to benchmark.")
        sys.exit(1)

    # Report
    print("\n" + "=" * 75)
    print("  CONTEXT PRECISION BENCHMARK — Real PRs from freeCodeCamp/freeCodeCamp")
    print("=" * 75)

    for r in results:
        print(f"\n  PR #{r['pr_number']}: {r['pr_title']}")
        print(f"  Diff: {r['diff_lines']} lines, {r['total_files']} files ({r['skipped_files']} skipped)")
        print(f"  Naive:  {r['naive']['chunks']} chunks, {r['naive']['tokens']:,} tokens, precision {r['naive']['precision']}%")
        print(f"  Smart:  {r['smart']['chunks']} chunks, {r['smart']['tokens']:,} tokens, precision {r['smart']['precision']}%")
        print(f"  → Precision +{r['improvement']['precision_gain']}%, tokens -{r['improvement']['token_savings_pct']}%")
        if r["skipped_names"]:
            print(f"  Skipped: {r['skipped_names']}")

    # Aggregate
    avg_naive_prec = sum(r["naive"]["precision"] for r in results) / len(results)
    avg_smart_prec = sum(r["smart"]["precision"] for r in results) / len(results)
    avg_token_savings = sum(r["improvement"]["token_savings_pct"] for r in results) / len(results)

    print("\n" + "=" * 75)
    print("  AGGREGATE (across PRs)")
    print("=" * 75)
    print(f"  PRs benchmarked:        {len(results)}")
    print(f"  Avg naive precision:   {avg_naive_prec:.1f}%")
    print(f"  Avg smart precision:   {avg_smart_prec:.1f}%")
    print(f"  Avg precision gain:    +{avg_smart_prec - avg_naive_prec:.1f}%")
    print(f"  Avg token savings:     {avg_token_savings:.1f}%")
    print()

    out_path = Path(__file__).parent / "real_pr_benchmark_results.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"  Results saved to {out_path}")


if __name__ == "__main__":
    main()
