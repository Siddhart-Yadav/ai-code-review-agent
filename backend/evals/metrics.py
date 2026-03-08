"""
Comprehensive evaluation metrics for AI code review pipeline.

Metrics computed:
1. Context Precision — fraction of chunks/tokens sent to LLM that are relevant
2. Context Recall — fraction of relevant files actually included in chunks
3. File Filtering Accuracy — precision/recall of the skip-file classifier
4. Chunk Relevance Score — per-chunk relevance (0/1) with aggregate stats
5. NDCG (Normalized Discounted Cumulative Gain) — ranking quality of priority sort
6. F1 Score — harmonic mean of precision and recall
7. Token Efficiency — token savings from smart vs naive chunking
8. MRR (Mean Reciprocal Rank) — how early high-priority files appear in chunks
9. Latency — wall-clock time for parsing, chunking, and full pipeline

All metrics are computed against ground truth annotations from real PRs.
"""

import math
import sys
import time
from dataclasses import dataclass, field
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
    """Approximate token count (chars / 4)."""
    return max(1, len(text) // 4)


# ── Data structures ──────────────────────────────────────────────────────────


@dataclass
class ChunkMetrics:
    """Metrics for a single chunk."""
    file_path: str
    tokens: int
    is_relevant: bool  # based on ground truth
    is_high_priority: bool  # based on ground truth
    priority_score: int  # 0=high, 1=medium, 2=low from code_parser
    has_scope: bool  # whether scope_name was detected
    language: str


@dataclass
class PRMetricsResult:
    """Full metrics result for a single PR."""
    pr_number: int
    pr_title: str

    # File-level
    total_files_in_diff: int
    files_after_filter: int
    files_skipped: int
    gt_relevant_files: int
    gt_noise_files: int

    # Context Precision (what fraction of chunks are relevant)
    context_precision: float  # relevant_chunks / total_chunks
    context_precision_weighted: float  # relevant_tokens / total_tokens

    # Context Recall (what fraction of relevant files got included)
    context_recall: float  # included_relevant / total_relevant

    # F1
    f1_score: float

    # File Filtering
    filter_precision: float  # true_skips / (true_skips + false_skips)
    filter_recall: float  # true_skips / (true_skips + missed_noise)
    filter_f1: float

    # Ranking quality
    ndcg: float  # how well priority ordering matches ground truth
    mrr: float  # mean reciprocal rank of first high-priority chunk

    # Token efficiency
    naive_tokens: int
    smart_tokens: int
    token_savings_pct: float

    # Chunk stats
    total_chunks: int
    relevant_chunks: int
    scoped_chunks: int
    scope_rate: float
    avg_tokens_per_chunk: float

    # Latency (milliseconds)
    parse_latency_ms: float  # time to parse unified diff into FileDiff objects
    chunk_latency_ms: float  # time to run smart chunking (filter + sort + scope)
    naive_chunk_latency_ms: float  # time to run naive chunking (baseline)
    total_pipeline_latency_ms: float  # parse + smart chunk combined

    # Per-chunk detail
    chunk_details: list[ChunkMetrics] = field(default_factory=list)


# ── Core metric functions ────────────────────────────────────────────────────


def _context_precision(chunks: list[ChunkMetrics]) -> tuple[float, float]:
    """
    Compute context precision two ways:
    - Unweighted: fraction of chunks that are relevant
    - Weighted: fraction of tokens in relevant chunks / total tokens
    """
    if not chunks:
        return 0.0, 0.0

    relevant_count = sum(1 for c in chunks if c.is_relevant)
    relevant_tokens = sum(c.tokens for c in chunks if c.is_relevant)
    total_tokens = sum(c.tokens for c in chunks)

    precision_unweighted = relevant_count / len(chunks)
    precision_weighted = relevant_tokens / total_tokens if total_tokens > 0 else 0.0

    return round(precision_unweighted, 4), round(precision_weighted, 4)


def _context_recall(
    chunks: list[ChunkMetrics], gt_relevant_files: list[str]
) -> float:
    """
    Fraction of ground-truth relevant files that appear in at least one chunk.
    """
    if not gt_relevant_files:
        return 1.0  # vacuously true

    included_files = {c.file_path for c in chunks}
    hits = sum(1 for f in gt_relevant_files if f in included_files)
    return round(hits / len(gt_relevant_files), 4)


def _f1(precision: float, recall: float) -> float:
    """Harmonic mean of precision and recall."""
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _filter_metrics(
    file_diffs_paths: list[str],
    gt_relevant: list[str],
    gt_noise: list[str],
) -> tuple[float, float, float]:
    """
    Evaluate the file-skip classifier against ground truth.

    Returns: (precision, recall, f1) for the noise-detection task.
    Precision = of files we skipped, how many were actually noise?
    Recall = of actual noise files, how many did we skip?
    """
    skipped_by_system = {p for p in file_diffs_paths if should_skip_file(p)}
    gt_noise_set = set(gt_noise)

    true_positives = len(skipped_by_system & gt_noise_set)
    false_positives = len(skipped_by_system - gt_noise_set)
    false_negatives = len(gt_noise_set - skipped_by_system)

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 1.0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 1.0

    return round(precision, 4), round(recall, 4), round(_f1(precision, recall), 4)


def _dcg(relevance_scores: list[float], k: int | None = None) -> float:
    """Discounted Cumulative Gain at position k."""
    if k is None:
        k = len(relevance_scores)
    dcg = 0.0
    for i, rel in enumerate(relevance_scores[:k]):
        dcg += rel / math.log2(i + 2)  # i+2 because positions are 1-indexed
    return dcg


def _ndcg(chunks: list[ChunkMetrics]) -> float:
    """
    NDCG: measures how well the chunk ordering matches ideal priority ordering.

    Relevance scores:
    - 3 for high-priority + relevant
    - 2 for relevant (non-high-priority)
    - 0 for irrelevant
    """
    if not chunks:
        return 0.0

    actual_scores = []
    for c in chunks:
        if c.is_high_priority and c.is_relevant:
            actual_scores.append(3.0)
        elif c.is_relevant:
            actual_scores.append(2.0)
        else:
            actual_scores.append(0.0)

    ideal_scores = sorted(actual_scores, reverse=True)

    actual_dcg = _dcg(actual_scores)
    ideal_dcg = _dcg(ideal_scores)

    if ideal_dcg == 0:
        return 0.0

    return round(actual_dcg / ideal_dcg, 4)


def _mrr(chunks: list[ChunkMetrics]) -> float:
    """
    Mean Reciprocal Rank: 1/position of the first high-priority relevant chunk.
    """
    for i, c in enumerate(chunks):
        if c.is_high_priority and c.is_relevant:
            return round(1.0 / (i + 1), 4)
    return 0.0


# ── Naive chunking (baseline) ───────────────────────────────────────────────


def _naive_chunk_tokens(diff_text: str, max_chunk_size: int = 8000) -> int:
    """Count total tokens from naive fixed-size chunking (no filtering)."""
    lines = diff_text.split("\n")
    total_tokens = 0
    current_size = 0
    current_lines = []

    for line in lines:
        current_lines.append(line)
        current_size += len(line) + 1
        if current_size >= max_chunk_size:
            total_tokens += _estimate_tokens("\n".join(current_lines))
            current_lines = []
            current_size = 0

    if current_lines:
        total_tokens += _estimate_tokens("\n".join(current_lines))

    return total_tokens


# ── Main evaluation function ─────────────────────────────────────────────────


def evaluate_pr(
    diff_text: str,
    gt_relevant_files: list[str],
    gt_noise_files: list[str],
    gt_high_priority_files: list[str],
    pr_number: int = 0,
    pr_title: str = "",
) -> PRMetricsResult:
    """
    Run all metrics on a single PR diff against ground truth.

    Args:
        diff_text: raw unified diff string
        gt_relevant_files: list of file paths considered meaningful for review
        gt_noise_files: list of file paths that are noise (locks, snapshots, etc.)
        gt_high_priority_files: subset of relevant files that are high priority
        pr_number: PR identifier
        pr_title: PR title string

    Returns:
        PRMetricsResult with all computed metrics
    """
    # Parse and chunk — with latency measurement
    t0 = time.perf_counter()
    file_diffs = parse_unified_diff(diff_text)
    t1 = time.perf_counter()
    smart_chunks = chunk_for_agents(file_diffs)
    t2 = time.perf_counter()

    parse_latency_ms = round((t1 - t0) * 1000, 3)
    chunk_latency_ms = round((t2 - t1) * 1000, 3)
    total_pipeline_latency_ms = round((t2 - t0) * 1000, 3)

    all_paths = [fd.path for fd in file_diffs]

    gt_relevant_set = set(gt_relevant_files)
    gt_high_set = set(gt_high_priority_files)

    # Build per-chunk metrics
    chunk_metrics: list[ChunkMetrics] = []
    for chunk in smart_chunks:
        fp = chunk["file_path"]
        tokens = sum(_estimate_tokens(h.get("content", "")) for h in chunk.get("hunks", []))
        chunk_metrics.append(ChunkMetrics(
            file_path=fp,
            tokens=tokens,
            is_relevant=fp in gt_relevant_set,
            is_high_priority=fp in gt_high_set,
            priority_score=chunk.get("priority", 2),
            has_scope=bool(chunk.get("scope_name")),
            language=chunk.get("language", "unknown"),
        ))

    # Context precision
    cp_unweighted, cp_weighted = _context_precision(chunk_metrics)

    # Context recall
    cr = _context_recall(chunk_metrics, gt_relevant_files)

    # F1
    f1 = _f1(cp_weighted, cr)

    # File filter accuracy
    fp_prec, fp_rec, fp_f1 = _filter_metrics(all_paths, gt_relevant_files, gt_noise_files)

    # NDCG ranking quality
    ndcg = _ndcg(chunk_metrics)

    # MRR
    mrr = _mrr(chunk_metrics)

    # Token efficiency — with naive chunking latency
    t3 = time.perf_counter()
    naive_tokens = _naive_chunk_tokens(diff_text)
    t4 = time.perf_counter()
    naive_chunk_latency_ms = round((t4 - t3) * 1000, 3)

    smart_tokens = sum(c.tokens for c in chunk_metrics)
    savings = round((naive_tokens - smart_tokens) / naive_tokens * 100, 1) if naive_tokens > 0 else 0.0

    # Chunk stats
    scoped = sum(1 for c in chunk_metrics if c.has_scope)
    scope_rate = round(scoped / len(chunk_metrics) * 100, 1) if chunk_metrics else 0.0
    avg_tok = round(smart_tokens / len(chunk_metrics)) if chunk_metrics else 0

    return PRMetricsResult(
        pr_number=pr_number,
        pr_title=pr_title,
        total_files_in_diff=len(file_diffs),
        files_after_filter=len([fd for fd in file_diffs if not should_skip_file(fd.path)]),
        files_skipped=len([fd for fd in file_diffs if should_skip_file(fd.path)]),
        gt_relevant_files=len(gt_relevant_files),
        gt_noise_files=len(gt_noise_files),
        context_precision=cp_unweighted,
        context_precision_weighted=cp_weighted,
        context_recall=cr,
        f1_score=f1,
        filter_precision=fp_prec,
        filter_recall=fp_rec,
        filter_f1=fp_f1,
        ndcg=ndcg,
        mrr=mrr,
        naive_tokens=naive_tokens,
        smart_tokens=smart_tokens,
        token_savings_pct=savings,
        total_chunks=len(chunk_metrics),
        relevant_chunks=sum(1 for c in chunk_metrics if c.is_relevant),
        scoped_chunks=scoped,
        scope_rate=scope_rate,
        avg_tokens_per_chunk=avg_tok,
        parse_latency_ms=parse_latency_ms,
        chunk_latency_ms=chunk_latency_ms,
        naive_chunk_latency_ms=naive_chunk_latency_ms,
        total_pipeline_latency_ms=total_pipeline_latency_ms,
        chunk_details=chunk_metrics,
    )


def aggregate_metrics(results: list[PRMetricsResult]) -> dict:
    """Compute aggregate statistics across multiple PR evaluations."""
    n = len(results)
    if n == 0:
        return {}

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    return {
        "num_prs": n,
        "avg_context_precision": _avg([r.context_precision for r in results]),
        "avg_context_precision_weighted": _avg([r.context_precision_weighted for r in results]),
        "avg_context_recall": _avg([r.context_recall for r in results]),
        "avg_f1_score": _avg([r.f1_score for r in results]),
        "avg_filter_precision": _avg([r.filter_precision for r in results]),
        "avg_filter_recall": _avg([r.filter_recall for r in results]),
        "avg_filter_f1": _avg([r.filter_f1 for r in results]),
        "avg_ndcg": _avg([r.ndcg for r in results]),
        "avg_mrr": _avg([r.mrr for r in results]),
        "avg_token_savings_pct": _avg([r.token_savings_pct for r in results]),
        "total_naive_tokens": sum(r.naive_tokens for r in results),
        "total_smart_tokens": sum(r.smart_tokens for r in results),
        "total_chunks": sum(r.total_chunks for r in results),
        "total_relevant_chunks": sum(r.relevant_chunks for r in results),
        "avg_scope_rate": _avg([r.scope_rate for r in results]),
        "avg_parse_latency_ms": _avg([r.parse_latency_ms for r in results]),
        "avg_chunk_latency_ms": _avg([r.chunk_latency_ms for r in results]),
        "avg_naive_chunk_latency_ms": _avg([r.naive_chunk_latency_ms for r in results]),
        "avg_total_pipeline_latency_ms": _avg([r.total_pipeline_latency_ms for r in results]),
        "p95_pipeline_latency_ms": round(sorted([r.total_pipeline_latency_ms for r in results])[int(n * 0.95)] if n > 1 else results[0].total_pipeline_latency_ms, 3),
        "max_pipeline_latency_ms": round(max(r.total_pipeline_latency_ms for r in results), 3),
        "latency_speedup_vs_naive": round(
            _avg([r.naive_chunk_latency_ms for r in results])
            / _avg([r.chunk_latency_ms for r in results]), 2
        ) if _avg([r.chunk_latency_ms for r in results]) > 0 else 0.0,
    }
