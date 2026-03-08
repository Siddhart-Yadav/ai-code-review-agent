"""
Semgrep integration — deterministic static analysis for the review pipeline.

Two modes:
1. MCP client: calls Semgrep MCP server via stdio (when available + authenticated)
2. CLI fallback: runs `semgrep scan --json` directly (works with OSS rules, no login)

The findings are fed into the LLM Security Agent as ground-truth context,
creating a hybrid deterministic + probabilistic review pipeline.
"""

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

SEMGREP_TIMEOUT = 60


def _reconstruct_files_from_diff(diff_text: str) -> dict[str, str]:
    """
    Extract the '+' side of each file from a unified diff.
    Returns {filename: reconstructed_content} for Semgrep to scan.
    """
    files: dict[str, str] = {}
    current_file = None
    lines: list[str] = []

    for raw_line in diff_text.split("\n"):
        if raw_line.startswith("+++ b/"):
            if current_file and lines:
                files[current_file] = "\n".join(lines)
            current_file = raw_line[6:]
            lines = []
        elif raw_line.startswith("--- "):
            continue
        elif raw_line.startswith("diff --git"):
            continue
        elif raw_line.startswith("@@"):
            continue
        elif current_file is not None:
            if raw_line.startswith("+"):
                lines.append(raw_line[1:])
            elif raw_line.startswith("-"):
                continue
            else:
                lines.append(raw_line[1:] if raw_line.startswith(" ") else raw_line)

    if current_file and lines:
        files[current_file] = "\n".join(lines)

    return files


async def run_semgrep_scan(diff_text: str) -> list[dict]:
    """
    Run Semgrep static analysis on a diff.

    Tries MCP protocol first, falls back to direct CLI invocation.
    Writes reconstructed files to a temp dir, scans, returns findings.
    """
    files = _reconstruct_files_from_diff(diff_text)
    if not files:
        logger.info("Semgrep: no files to scan from diff")
        return []

    with tempfile.TemporaryDirectory(prefix="semgrep_scan_") as tmpdir:
        for filename, content in files.items():
            filepath = Path(tmpdir) / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content)

        findings = await _try_mcp_scan(tmpdir)
        if findings is None:
            findings = await _run_cli_scan(tmpdir)

    logger.info("Semgrep scan complete: %d findings", len(findings))
    return findings


async def _try_mcp_scan(scan_dir: str) -> list[dict] | None:
    """Try scanning via Semgrep MCP server. Returns None if unavailable."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command="semgrep",
            args=["mcp"],
            env={**os.environ},
        )

        async with asyncio.timeout(SEMGREP_TIMEOUT):
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("security_check", {
                        "code_or_dir": scan_dir,
                    })

                    if result.content:
                        text = result.content[0].text
                        try:
                            data = json.loads(text)
                            raw = data.get("findings", data.get("results", []))
                            if isinstance(raw, list):
                                return [_normalize_finding(f) for f in raw]
                        except json.JSONDecodeError:
                            pass
                    return []
    except Exception as e:
        logger.info("Semgrep MCP unavailable (%s), falling back to CLI", type(e).__name__)
        return None


async def _run_cli_scan(scan_dir: str) -> list[dict]:
    """Run Semgrep directly via CLI with auto-detected rules."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "semgrep", "scan",
            "--json",
            "--config", "p/default",
            "--no-git-ignore",
            "--timeout", str(SEMGREP_TIMEOUT),
            scan_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=SEMGREP_TIMEOUT + 10
        )

        if stderr:
            stderr_text = stderr.decode(errors="replace")
            if "error" in stderr_text.lower() and "warn" not in stderr_text.lower():
                logger.warning("Semgrep stderr: %s", stderr_text[:500])

        if stdout:
            try:
                data = json.loads(stdout.decode())
                results = data.get("results", [])
                return [_normalize_finding(f) for f in results]
            except json.JSONDecodeError:
                logger.warning("Semgrep returned non-JSON output")
                return []

        return []
    except asyncio.TimeoutError:
        logger.warning("Semgrep CLI scan timed out after %ds", SEMGREP_TIMEOUT)
        return []
    except FileNotFoundError:
        logger.warning("Semgrep binary not found — skipping static analysis")
        return []
    except Exception as e:
        logger.warning("Semgrep CLI scan failed: %s", e)
        return []


def _normalize_finding(finding: dict) -> dict:
    """Normalize a Semgrep finding into our standard format."""
    extra = finding.get("extra", {})
    metadata = extra.get("metadata", {})

    return {
        "source": "semgrep",
        "rule_id": finding.get("check_id") or finding.get("rule_id") or "unknown",
        "file": finding.get("path") or finding.get("file", "unknown"),
        "line": finding.get("start", {}).get("line") or finding.get("line", 0),
        "end_line": finding.get("end", {}).get("line"),
        "severity": _map_severity(extra.get("severity") or finding.get("severity", "WARNING")),
        "title": extra.get("message") or finding.get("message", "Semgrep finding"),
        "description": metadata.get("description", ""),
        "cwe": metadata.get("cwe", []),
        "owasp": metadata.get("owasp", []),
        "fix": extra.get("fix", ""),
        "confidence": 1.0,
    }


def _map_severity(sev: str) -> str:
    """Map Semgrep severity levels to our severity scale."""
    mapping = {
        "ERROR": "critical",
        "WARNING": "high",
        "INFO": "medium",
        "INVENTORY": "info",
        "EXPERIMENT": "info",
    }
    return mapping.get(sev.upper(), sev.lower())
