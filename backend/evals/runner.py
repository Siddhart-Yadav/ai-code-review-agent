"""
Evaluation runner — feeds known-bad code through the pipeline and scores detection.

Metrics:
- Detection rate: % of expected findings that were detected
- False negative rate: expected findings the agents missed
- Per-agent breakdown of precision

Usage:
    python -m evals.runner                     # run all cases
    python -m evals.runner --case sql_injection # run one case
    python -m evals.runner --verbose            # show full findings
"""

import asyncio
import json
import sys
import time
import logging
from argparse import ArgumentParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.code_parser import parse_unified_diff, chunk_for_agents
from app.agents.graph import review_pipeline
from evals.test_cases import EVAL_CASES

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _matches_expected(finding: dict, expected: dict) -> bool:
    """Check if a finding matches an expected detection."""
    if finding.get("agent_name") and finding["agent_name"] != expected["agent"]:
        return False

    finding_text = json.dumps(finding, default=str).lower()
    keyword_hits = sum(
        1 for kw in expected["keywords"] if kw.lower() in finding_text
    )
    if keyword_hits == 0:
        return False

    min_sev = expected.get("severity_min", "info")
    finding_sev = (finding.get("severity") or "info").lower()
    if SEVERITY_RANK.get(finding_sev, 0) < SEVERITY_RANK.get(min_sev, 0):
        return False

    return True


def _tag_findings_with_agent(specialist_results: list[dict]) -> list[dict]:
    """Flatten specialist results into a single list with agent_name tagged."""
    tagged = []
    for sr in specialist_results:
        agent = sr.get("agent_name", "unknown")
        for f in sr.get("findings", []):
            f_copy = dict(f)
            f_copy["agent_name"] = agent
            tagged.append(f_copy)
    return tagged


async def run_case(case: dict, verbose: bool = False) -> dict:
    """Run a single eval case through the pipeline and score it."""
    case_id = case["id"]
    print(f"\n{'='*60}")
    print(f"  EVAL: {case['name']} ({case_id})")
    print(f"{'='*60}")

    file_diffs = parse_unified_diff(case["diff"])
    chunks = chunk_for_agents(file_diffs)

    state = {
        "diff_chunks": chunks,
        "diff_text": case["diff"],
        "pr_info": {
            "title": f"[EVAL] {case['name']}",
            "description": "Evaluation test case with known issues",
            "repo_full_name": "eval/test-repo",
            "author": "eval-bot",
            "base_branch": "main",
            "head_branch": "feature/eval",
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
        print(f"  PIPELINE ERROR: {e}")
        return {
            "case_id": case_id,
            "detected": 0,
            "expected": len(case["expected"]),
            "detection_rate": 0.0,
            "error": str(e),
        }

    elapsed = time.time() - start
    specialist_results = result.get("specialist_results", [])
    all_findings = _tag_findings_with_agent(specialist_results)

    detected = []
    missed = []
    for exp in case["expected"]:
        found = any(_matches_expected(f, exp) for f in all_findings)
        if found:
            detected.append(exp)
        else:
            missed.append(exp)

    detection_rate = len(detected) / len(case["expected"]) * 100 if case["expected"] else 100.0

    print(f"\n  Time: {elapsed:.1f}s | Findings: {len(all_findings)} | "
          f"Detected: {len(detected)}/{len(case['expected'])} ({detection_rate:.0f}%)")

    if detected:
        print(f"  DETECTED:")
        for d in detected:
            print(f"    [{d['agent']}] {', '.join(d['keywords'][:3])}")

    if missed:
        print(f"  MISSED:")
        for m in missed:
            print(f"    [{m['agent']}] {', '.join(m['keywords'][:3])}")

    if verbose and all_findings:
        print(f"\n  ALL FINDINGS:")
        for f in all_findings:
            sev = f.get("severity", "?")
            title = f.get("title", "untitled")
            agent = f.get("agent_name", "?")
            print(f"    [{agent}] [{sev}] {title}")

    return {
        "case_id": case_id,
        "name": case["name"],
        "detected": len(detected),
        "expected": len(case["expected"]),
        "total_findings": len(all_findings),
        "detection_rate": detection_rate,
        "missed": [{"agent": m["agent"], "keywords": m["keywords"]} for m in missed],
        "elapsed_seconds": elapsed,
        "error": None,
    }


async def run_all(case_filter: str | None = None, verbose: bool = False):
    """Run all eval cases and print a summary scorecard."""
    cases = EVAL_CASES
    if case_filter:
        cases = [c for c in cases if c["id"] == case_filter]
        if not cases:
            print(f"No eval case found with id '{case_filter}'")
            print(f"Available: {[c['id'] for c in EVAL_CASES]}")
            return

    results = []
    for case in cases:
        r = await run_case(case, verbose=verbose)
        results.append(r)

    # Scorecard
    total_expected = sum(r["expected"] for r in results)
    total_detected = sum(r["detected"] for r in results)
    total_findings = sum(r.get("total_findings", 0) for r in results)
    overall_rate = total_detected / total_expected * 100 if total_expected else 0
    errors = sum(1 for r in results if r.get("error"))

    print(f"\n{'='*60}")
    print(f"  EVALUATION SCORECARD")
    print(f"{'='*60}")
    print(f"  Cases run:          {len(results)}")
    print(f"  Pipeline errors:    {errors}")
    print(f"  Total findings:     {total_findings}")
    print(f"  Expected detections:{total_expected}")
    print(f"  Actual detections:  {total_detected}")
    print(f"  Detection rate:     {overall_rate:.1f}%")
    print(f"{'='*60}")

    print(f"\n  Per-case breakdown:")
    for r in results:
        status = "PASS" if r["detection_rate"] == 100 else ("PARTIAL" if r["detection_rate"] > 0 else "FAIL")
        icon = {"PASS": "+", "PARTIAL": "~", "FAIL": "x"}[status]
        print(f"    [{icon}] {r['case_id']:<25} {r['detected']}/{r['expected']} detected  ({r['detection_rate']:.0f}%)")
        if r.get("missed"):
            for m in r["missed"]:
                print(f"        missed: [{m['agent']}] {', '.join(m['keywords'][:3])}")

    # Write results to JSON for CI
    output_path = Path(__file__).parent / "results.json"
    output_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n  Results saved to {output_path}")

    return overall_rate


if __name__ == "__main__":
    parser = ArgumentParser(description="Run AI Code Review Agent evaluation suite")
    parser.add_argument("--case", type=str, help="Run a specific case by ID")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show all findings")
    args = parser.parse_args()

    asyncio.run(run_all(case_filter=args.case, verbose=args.verbose))
