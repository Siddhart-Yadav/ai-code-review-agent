"""
LangGraph multi-agent orchestration pipeline.

Flow:
  PR Diff → Semgrep static analysis (deterministic)
         → [Security, Performance, Style, TestCoverage] (parallel fan-out, LLM)
         → Aggregator (fan-in) → Meta Reviewer → Final Output

Hybrid architecture:
- Semgrep MCP: deterministic SAST with guaranteed detection of known patterns
- LLM agents: probabilistic reasoning for logic bugs, design issues, test gaps
- Semgrep findings are injected into the Security Agent as ground-truth context

Uses LangGraph's Send API for true parallel execution of specialist agents.
All LLM calls use Gemini's response_schema for guaranteed structured JSON.
"""

import json
import time
import logging
from typing import TypedDict, Annotated
from operator import add

from langgraph.graph import StateGraph, END, START
from langgraph.types import Send

from app.agents.llm import call_llm_structured
from app.agents.schemas import (
    SpecialistOutput,
    AggregatorOutput,
    MetaReviewOutput,
)
from app.agents.prompts import (
    SECURITY_AGENT_PROMPT,
    PERFORMANCE_AGENT_PROMPT,
    STYLE_AGENT_PROMPT,
    TEST_COVERAGE_AGENT_PROMPT,
    AGGREGATOR_PROMPT,
    META_REVIEWER_PROMPT,
)
from app.services.semgrep_service import run_semgrep_scan

logger = logging.getLogger(__name__)

SPECIALIST_AGENTS = {
    "security": SECURITY_AGENT_PROMPT,
    "performance": PERFORMANCE_AGENT_PROMPT,
    "style": STYLE_AGENT_PROMPT,
    "test_coverage": TEST_COVERAGE_AGENT_PROMPT,
}


class SpecialistResult(TypedDict):
    agent_name: str
    findings: list
    summary: str
    score: float
    execution_time_ms: int
    error: str | None


class ReviewState(TypedDict):
    diff_chunks: list[dict]
    diff_text: str
    pr_info: dict
    semgrep_findings: list[dict]
    specialist_results: Annotated[list[SpecialistResult], add]
    aggregated_result: dict
    meta_review: dict
    error: str | None


class SpecialistInput(TypedDict):
    diff_chunks: list[dict]
    pr_info: dict
    agent_name: str
    system_prompt: str
    semgrep_findings: list[dict]


def _format_chunks_for_prompt(chunks: list[dict], pr_info: dict) -> str:
    priority_labels = {0: "HIGH RISK", 1: "MEDIUM", 2: "NORMAL"}

    header = (
        f"PR: {pr_info.get('title', 'N/A')}\n"
        f"Repo: {pr_info.get('repo_full_name', 'N/A')}\n"
        f"Author: {pr_info.get('author', 'N/A')}\n"
        f"Description: {pr_info.get('description', 'N/A')[:500]}\n\n"
        "--- Code Changes ---\n\n"
    )

    chunk_texts = []
    for chunk in chunks:
        priority = chunk.get("priority", 2)
        chunk_text = f"File: {chunk['file_path']} ({chunk['language']}) [{priority_labels.get(priority, 'NORMAL')}]\n"
        if chunk.get("scope_name"):
            chunk_text += f"Scope: {chunk['scope_name']}\n"
        if chunk.get("is_new_file"):
            chunk_text += "[NEW FILE]\n"
        for hunk in chunk.get("hunks", []):
            chunk_text += f"\n{hunk.get('content', '')}\n"
        chunk_texts.append(chunk_text)

    return header + "\n---\n".join(chunk_texts)


def _format_semgrep_context(findings: list[dict]) -> str:
    """Format Semgrep findings as context for the Security Agent."""
    if not findings:
        return ""

    lines = [
        "\n\n--- Semgrep Static Analysis Results (deterministic, high-confidence) ---\n",
        f"Semgrep found {len(findings)} issue(s). Validate these and include them "
        "in your review with additional context. Also look for issues Semgrep may have missed.\n",
    ]
    for i, f in enumerate(findings, 1):
        cwe = f", CWE: {f['cwe']}" if f.get("cwe") else ""
        owasp = f", OWASP: {f['owasp']}" if f.get("owasp") else ""
        lines.append(
            f"{i}. [{f.get('severity', 'medium').upper()}] {f.get('title', 'Finding')}\n"
            f"   File: {f.get('file', '?')}:{f.get('line', '?')}\n"
            f"   Rule: {f.get('rule_id', '?')}{cwe}{owasp}\n"
            f"   {f.get('description', '')}\n"
        )
    return "\n".join(lines)


# --- Step 1: Semgrep static analysis ---

async def semgrep_scan_node(state: ReviewState) -> dict:
    """Run Semgrep deterministic scan via MCP before LLM agents."""
    diff_text = state.get("diff_text", "")
    if not diff_text:
        logger.info("Semgrep: no diff_text provided, skipping scan")
        return {"semgrep_findings": []}

    start = time.time()
    try:
        findings = await run_semgrep_scan(diff_text)
        elapsed = time.time() - start
        logger.info("Semgrep scan: %d findings in %.1fs", len(findings), elapsed)
        return {"semgrep_findings": findings}
    except Exception as e:
        elapsed = time.time() - start
        logger.warning("Semgrep scan failed after %.1fs: %s (continuing without)", elapsed, e)
        return {"semgrep_findings": []}


# --- Step 2: Parallel fan-out to specialist agents ---

def dispatch_specialists(state: ReviewState) -> list[Send]:
    """Fan-out: send diff chunks to all specialist agents in parallel."""
    sends = []
    for agent_name, prompt in SPECIALIST_AGENTS.items():
        sends.append(
            Send(
                "specialist_agent",
                {
                    "diff_chunks": state["diff_chunks"],
                    "pr_info": state["pr_info"],
                    "agent_name": agent_name,
                    "system_prompt": prompt,
                    "semgrep_findings": state.get("semgrep_findings", []),
                },
            )
        )
    return sends


def specialist_agent(state: SpecialistInput) -> dict:
    """Run a single specialist agent. Called in parallel via Send."""
    agent_name = state["agent_name"]
    start = time.time()

    formatted_input = _format_chunks_for_prompt(
        state["diff_chunks"], state["pr_info"]
    )

    if agent_name == "security" and state.get("semgrep_findings"):
        formatted_input += _format_semgrep_context(state["semgrep_findings"])

    try:
        result = call_llm_structured(
            system_prompt=state["system_prompt"],
            user_prompt=formatted_input,
            response_model=SpecialistOutput,
        )

        findings = [f.model_dump() for f in result.findings]
        elapsed_ms = int((time.time() - start) * 1000)

        logger.info("Agent %s completed: %d findings in %dms", agent_name, len(findings), elapsed_ms)

        return {
            "specialist_results": [
                {
                    "agent_name": agent_name,
                    "findings": findings,
                    "summary": f"{len(findings)} issues found",
                    "score": max(0, 10 - len(findings) * 0.5),
                    "execution_time_ms": elapsed_ms,
                    "error": None,
                }
            ]
        }
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        logger.error("Agent %s failed after %dms: %s", agent_name, elapsed_ms, e)
        return {
            "specialist_results": [
                {
                    "agent_name": agent_name,
                    "findings": [],
                    "summary": f"Agent error: {str(e)}",
                    "score": 5.0,
                    "execution_time_ms": elapsed_ms,
                    "error": str(e),
                }
            ]
        }


# --- Step 3: Fan-in aggregation and meta-review ---

def should_skip_aggregation(state: ReviewState) -> str:
    """Conditional edge: skip aggregation if no findings from any agent."""
    results = state.get("specialist_results", [])
    total_findings = sum(len(r.get("findings", [])) for r in results)
    if total_findings == 0:
        return "meta_reviewer"
    return "aggregator"


def aggregator_node(state: ReviewState) -> dict:
    results = state.get("specialist_results", [])
    all_findings = {}
    for r in results:
        all_findings[r["agent_name"]] = r.get("findings", [])

    semgrep = state.get("semgrep_findings", [])
    if semgrep:
        all_findings["semgrep_static_analysis"] = semgrep

    user_prompt = (
        "Here are the findings from all specialist agents"
        + (" and Semgrep static analysis" if semgrep else "")
        + ":\n\n"
        f"{json.dumps(all_findings, indent=2, default=str)}\n\n"
        "Deduplicate, prioritize, and aggregate these findings."
    )

    try:
        result = call_llm_structured(
            system_prompt=AGGREGATOR_PROMPT,
            user_prompt=user_prompt,
            response_model=AggregatorOutput,
            temperature=0.05,
        )
        return {"aggregated_result": result.model_dump()}
    except Exception as e:
        logger.error("Aggregator failed: %s", e)
        return {
            "aggregated_result": {
                "findings": [],
                "summary": f"Aggregation error: {str(e)}",
                "stats": {},
            }
        }


def meta_reviewer_node(state: ReviewState) -> dict:
    aggregated = state.get("aggregated_result", {})
    results = state.get("specialist_results", [])
    agent_scores = {r["agent_name"]: r.get("score", 5.0) for r in results}
    semgrep_count = len(state.get("semgrep_findings", []))

    user_prompt = (
        "Aggregated findings:\n"
        f"{json.dumps(aggregated, indent=2, default=str)}\n\n"
        "Individual agent scores:\n"
        f"{json.dumps(agent_scores, indent=2)}\n\n"
        f"Semgrep static analysis found {semgrep_count} deterministic issue(s).\n\n"
        "Provide your final meta-review."
    )

    try:
        result = call_llm_structured(
            system_prompt=META_REVIEWER_PROMPT,
            user_prompt=user_prompt,
            response_model=MetaReviewOutput,
            temperature=0.05,
        )
        return {"meta_review": result.model_dump()}
    except Exception as e:
        logger.error("Meta reviewer failed: %s", e)
        review = _default_meta_review()
        review["summary"] = f"Meta-review error: {str(e)}"
        return {"meta_review": review}


def _default_meta_review() -> dict:
    return {
        "overall_score": 5.0,
        "recommendation": "comment",
        "summary": "Review completed",
        "key_issues": [],
        "positive_aspects": [],
        "risk_assessment": "medium",
    }


# --- Build the graph ---

def build_review_graph() -> StateGraph:
    """
    Build the LangGraph review pipeline.

    Graph topology:
      START ──→ semgrep_scan ──dispatch──→ specialist_agent (×4 in parallel)
                                               │
                                          (fan-in via Annotated[list, add])
                                               │
                                          conditional ──→ aggregator ──→ meta_reviewer ──→ END
                                               │                                           ↑
                                               └──── (no findings) ────────────────────────┘
    """
    graph = StateGraph(ReviewState)

    graph.add_node("semgrep_scan", semgrep_scan_node)
    graph.add_node("specialist_agent", specialist_agent)
    graph.add_node("aggregator", aggregator_node)
    graph.add_node("meta_reviewer", meta_reviewer_node)

    graph.add_edge(START, "semgrep_scan")
    graph.add_conditional_edges("semgrep_scan", dispatch_specialists, ["specialist_agent"])

    graph.add_conditional_edges(
        "specialist_agent",
        should_skip_aggregation,
        {"aggregator": "aggregator", "meta_reviewer": "meta_reviewer"},
    )

    graph.add_edge("aggregator", "meta_reviewer")
    graph.add_edge("meta_reviewer", END)

    return graph.compile()


review_pipeline = build_review_graph()
