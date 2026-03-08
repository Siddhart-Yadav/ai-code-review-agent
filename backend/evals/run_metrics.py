#!/usr/bin/env python3
"""
Run comprehensive evaluation metrics on real freeCodeCamp PRs.

Computes context precision, recall, F1, NDCG, MRR, token efficiency,
and file-filter accuracy using ground-truth annotations.

Usage:
    python -m evals.run_metrics
"""

import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.metrics import evaluate_pr, aggregate_metrics, PRMetricsResult
from evals.real_pr_dataset import get_dataset


def _result_to_dict(r: PRMetricsResult) -> dict:
    """Convert PRMetricsResult to JSON-serializable dict (without chunk_details)."""
    d = asdict(r)
    # Remove verbose per-chunk data from saved output
    d.pop("chunk_details", None)
    return d


def print_pr_report(r: PRMetricsResult) -> None:
    """Pretty-print metrics for a single PR."""
    print(f"\n  PR #{r.pr_number}: {r.pr_title[:60]}")
    print(f"  {'─' * 65}")
    print(f"  Files: {r.total_files_in_diff} total, "
          f"{r.files_after_filter} reviewable, "
          f"{r.files_skipped} skipped")
    print(f"  Ground truth: {r.gt_relevant_files} relevant, "
          f"{r.gt_noise_files} noise")
    print()
    print(f"  Context Precision (chunk):    {r.context_precision:.2%}")
    print(f"  Context Precision (weighted): {r.context_precision_weighted:.2%}")
    print(f"  Context Recall:               {r.context_recall:.2%}")
    print(f"  F1 Score:                     {r.f1_score:.2%}")
    print()
    print(f"  File Filter Precision:        {r.filter_precision:.2%}")
    print(f"  File Filter Recall:           {r.filter_recall:.2%}")
    print(f"  File Filter F1:               {r.filter_f1:.2%}")
    print()
    print(f"  NDCG (ranking quality):       {r.ndcg:.4f}")
    print(f"  MRR (first high-pri chunk):   {r.mrr:.4f}")
    print()
    print(f"  Naive tokens:                 {r.naive_tokens:,}")
    print(f"  Smart tokens:                 {r.smart_tokens:,}")
    print(f"  Token savings:                {r.token_savings_pct:.1f}%")
    print(f"  Chunks: {r.total_chunks} total, "
          f"{r.relevant_chunks} relevant, "
          f"{r.scoped_chunks} scoped ({r.scope_rate:.1f}%)")
    if r.avg_tokens_per_chunk:
        print(f"  Avg tokens/chunk:             {r.avg_tokens_per_chunk:,}")
    print()
    print(f"  Latency (parse):              {r.parse_latency_ms:.3f} ms")
    print(f"  Latency (smart chunk):        {r.chunk_latency_ms:.3f} ms")
    print(f"  Latency (naive chunk):        {r.naive_chunk_latency_ms:.3f} ms")
    print(f"  Latency (total pipeline):     {r.total_pipeline_latency_ms:.3f} ms")


def print_aggregate(agg: dict) -> None:
    """Pretty-print aggregate metrics."""
    print(f"\n  {'═' * 70}")
    print(f"  AGGREGATE METRICS ({agg['num_prs']} PRs from freeCodeCamp/freeCodeCamp)")
    print(f"  {'═' * 70}")
    print()
    print(f"  Context Precision (avg):      {agg['avg_context_precision']:.2%}")
    print(f"  Context Precision (weighted): {agg['avg_context_precision_weighted']:.2%}")
    print(f"  Context Recall (avg):         {agg['avg_context_recall']:.2%}")
    print(f"  F1 Score (avg):               {agg['avg_f1_score']:.2%}")
    print()
    print(f"  File Filter Precision (avg):  {agg['avg_filter_precision']:.2%}")
    print(f"  File Filter Recall (avg):     {agg['avg_filter_recall']:.2%}")
    print(f"  File Filter F1 (avg):         {agg['avg_filter_f1']:.2%}")
    print()
    print(f"  NDCG (avg):                   {agg['avg_ndcg']:.4f}")
    print(f"  MRR (avg):                    {agg['avg_mrr']:.4f}")
    print()
    print(f"  Token savings (avg):          {agg['avg_token_savings_pct']:.1f}%")
    print(f"  Total naive tokens:           {agg['total_naive_tokens']:,}")
    print(f"  Total smart tokens:           {agg['total_smart_tokens']:,}")
    print(f"  Overall token reduction:      "
          f"{(agg['total_naive_tokens'] - agg['total_smart_tokens']) / agg['total_naive_tokens'] * 100:.1f}%")
    print()
    print(f"  Total chunks generated:       {agg['total_chunks']}")
    print(f"  Total relevant chunks:        {agg['total_relevant_chunks']}")
    print(f"  Avg scope rate:               {agg['avg_scope_rate']:.1f}%")
    print()
    print(f"  {'─' * 70}")
    print(f"  LATENCY")
    print(f"  {'─' * 70}")
    print(f"  Avg parse latency:            {agg['avg_parse_latency_ms']:.3f} ms")
    print(f"  Avg smart chunk latency:      {agg['avg_chunk_latency_ms']:.3f} ms")
    print(f"  Avg naive chunk latency:      {agg['avg_naive_chunk_latency_ms']:.3f} ms")
    print(f"  Avg total pipeline:           {agg['avg_total_pipeline_latency_ms']:.3f} ms")
    print(f"  P95 pipeline latency:         {agg['p95_pipeline_latency_ms']:.3f} ms")
    print(f"  Max pipeline latency:         {agg['max_pipeline_latency_ms']:.3f} ms")
    print(f"  Smart/Naive speed ratio:      {agg['latency_speedup_vs_naive']:.2f}x")


def main():
    dataset = get_dataset()

    print("=" * 75)
    print("  COMPREHENSIVE EVALUATION METRICS")
    print("  Real PRs from freeCodeCamp/freeCodeCamp with ground-truth annotations")
    print("=" * 75)

    results: list[PRMetricsResult] = []

    for diff_text, gt in dataset:
        r = evaluate_pr(
            diff_text=diff_text,
            gt_relevant_files=gt.relevant_files,
            gt_noise_files=gt.noise_files,
            gt_high_priority_files=gt.high_priority_files,
            pr_number=gt.pr_number,
            pr_title=gt.pr_title,
        )
        results.append(r)
        print_pr_report(r)

    agg = aggregate_metrics(results)
    print_aggregate(agg)

    # Save results
    output = {
        "per_pr": [_result_to_dict(r) for r in results],
        "aggregate": agg,
        "dataset": {
            "source": "freeCodeCamp/freeCodeCamp",
            "num_prs": len(results),
            "pr_numbers": [r.pr_number for r in results],
        },
    }

    out_path = Path(__file__).parent / "metrics_results.json"
    out_path.write_text(json.dumps(output, indent=2))
    print(f"\n  Results saved to {out_path}")
    print()


if __name__ == "__main__":
    main()
