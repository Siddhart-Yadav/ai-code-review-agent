# AI Code Review Agent

**Multi-agent AI system that reviews GitHub pull requests using 4 specialized LLM agents + Semgrep static analysis running in parallel, catching security vulnerabilities, performance issues, style violations, and test gaps — categorized by severity with exact line numbers.**

## Why This Matters

Manual code reviews are bottlenecked by reviewer availability and cognitive load. This agent reviews PRs in 30-90 seconds with consistent coverage across security, performance, style, and testing — areas where human reviewers frequently skip or rush through due to time pressure.

## Architecture

```
                          ┌─────────────────┐
                          │  Entry Points    │
                          │ Web UI │ CLI │   │
                          │ GitHub Action    │
                          │ MCP Server       │
                          └────────┬────────┘
                                   │
                          ┌────────▼────────┐
                          │    FastAPI       │
                          │  Backend API     │
                          └────────┬────────┘
                                   │
                   ┌───────────────▼───────────────┐
                   │     GitHub Service (PyGithub)  │
                   │     Fetch PR diff + metadata   │
                   └───────────────┬───────────────┘
                                   │
                   ┌───────────────▼───────────────┐
                   │     Diff Parser & Chunker      │
                   │  Smart splitting by function   │
                   │  boundaries + file priority     │
                   └───────────────┬───────────────┘
                                   │
              ┌────────────────────▼────────────────────┐
              │        LangGraph Orchestration           │
              │                                          │
              │  ┌────────────────────────────────────┐  │
              │  │  Semgrep MCP (deterministic SAST)  │  │
              │  │  Security scan → ground truth       │  │
              │  └──────────────┬─────────────────────┘  │
              │                 │                         │
              │  ┌──────────┐ ┌▼─────────┐ ┌──────────┐ │
              │  │ Security │ │  Perf    │ │  Style   │ │
              │  │  Agent   │ │  Agent   │ │  Agent   │ │
              │  │+Semgrep  │ └────┬─────┘ └────┬─────┘ │
              │  └────┬─────┘      │             │       │
              │       │  ┌─────────┴─────────────┘       │
              │       │  │  ┌──────────┐                 │
              │       │  │  │  Tests   │                 │
              │       │  │  │  Agent   │                 │
              │       │  │  └────┬─────┘                 │
              │       │  │       │                       │
              │  ┌────▼──▼───────▼────────────────────┐  │
              │  │           Aggregator                │  │
              │  │    Dedup + rank + cross-validate    │  │
              │  └──────────────┬─────────────────────┘  │
              │                 │                         │
              │       ┌────────▼────────┐                │
              │       │  Meta Reviewer  │                │
              │       │ Score & Verdict │                │
              │       └────────┬────────┘                │
              └────────────────┼─────────────────────────┘
                               │
              ┌────────────────▼────────────────┐
              │  PostgreSQL        Redis         │
              │  (review history)  (diff cache)  │
              └─────────────────────────────────┘
```

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Frontend | Next.js 14, TypeScript, Tailwind, shadcn/ui | SSR, great DX, modern component library |
| Backend | FastAPI, Python 3.12, Pydantic | Async-native, auto-generated OpenAPI, strong typing |
| Agent Framework | LangGraph | True parallel fan-out/fan-in, conditional routing, state management |
| LLM | Vertex AI (Gemini 3.1 Pro) | Direct SDK, response_schema for guaranteed structured JSON |
| Static Analysis | Semgrep (via MCP + CLI) | Deterministic SAST — zero false negatives for known vulnerability patterns |
| Structured Output | Pydantic schemas + Gemini response_schema | Every LLM call returns validated JSON; auto-retry on malformed output |
| MCP | FastMCP server + Semgrep MCP client | Expose agent as tool AND consume external tools via Model Context Protocol |
| Git | PyGithub | PR diff extraction, review comment posting |
| Database | PostgreSQL 16 | Review history, async via asyncpg |
| Cache | Redis 7 | Skip re-reviewing identical diffs (SHA-256 hash) |
| Deployment | Docker Compose, Vercel | Full-stack local dev, frontend deployment |

## Key Design: Hybrid Analysis Pipeline

The agent combines **deterministic** and **probabilistic** analysis:

| Layer | Tool | Strength | Weakness |
|-------|------|----------|----------|
| **Deterministic** | Semgrep (3000+ rules) | Zero false negatives for known patterns, exact CWE/OWASP tags, line-precise | Can't reason about business logic or novel bugs |
| **Probabilistic** | Gemini LLM (4 agents) | Catches logic errors, design issues, missing tests, contextual problems | May hallucinate or miss things |
| **Hybrid** | Semgrep → Security Agent | Semgrep findings injected as ground truth, LLM validates + extends | Best of both: coverage AND reasoning |

## Structured Output Enforcement

Every LLM call uses a 3-layer guarantee:

1. **Gemini `response_schema`** — model is forced to output JSON matching the Pydantic schema
2. **Pydantic validation** — response is parsed and validated with strict types
3. **Automatic retry** — on validation failure, the error is appended to the prompt and retried (up to 2x)

This eliminates the "sometimes the LLM returns garbage" problem entirely.

## Evaluation Suite

8 test cases of intentionally bad code with known bugs:

| Case | Expected Detections | Category |
|------|-------------------|----------|
| SQL injection via f-string | SQL injection + parameterized query fix | Security |
| Hardcoded API keys + passwords | Secret detection | Security |
| N+1 query in ORM loop | Query optimization | Performance |
| Missing try/except on file I/O + API | Error handling | Style |
| Payment processor with zero tests | Test coverage gaps | Test Coverage |
| Blocking I/O in async function | async + resource leak | Performance |
| XSS + pickle deserialization + CSRF | Multi-vulnerability | Security |
| O(n²) duplicate finder | Algorithm optimization | Performance |

Run the evaluation:
```bash
docker exec ai-code-review-agent-backend-1 python -m evals.runner
docker exec ai-code-review-agent-backend-1 python -m evals.runner --case sql_injection -v
```

Results: **100% detection rate** on tested cases (SQL injection, hardcoded secrets, missing tests).

## Entry Points

| Method | Description |
|--------|-------------|
| **Web UI** | Paste a PR URL at `http://localhost:3000`, get a visual review report |
| **CLI** | `python backend/cli.py https://github.com/owner/repo/pull/123` |
| **GitHub Action** | Auto-triggers on PR open/update, posts review as PR comment |
| **MCP Server** | Use from Claude Desktop or Cursor: "review this PR for me" |

## Technical Decisions

| Decision | Trade-off | Rationale |
|----------|-----------|-----------|
| **LangGraph over CrewAI** | Steeper learning curve | True parallel execution via `Send` API, conditional routing, first-class state management |
| **Parallel fan-out** | More complex graph topology | 4 agents run simultaneously → ~4x faster than sequential |
| **Semgrep + LLM hybrid** | Extra dependency (Semgrep) | Deterministic SAST catches what LLMs miss; LLMs catch what rules can't express |
| **Gemini response_schema** | Restricts output format | Eliminates JSON parsing failures; retry handles edge cases |
| **Direct Google GenAI SDK** | No LangChain abstraction | Fewer dependencies, full control, supports latest models immediately |
| **Redis diff-hash cache** | Extra infrastructure | Identical diffs return instantly; SHA-256 ensures correctness |
| **Conditional aggregation skip** | Slightly more edges in graph | If no findings, skip straight to meta-reviewer to save an LLM call |
| **Regex diff parser + smart chunking** | Less precise than Tree-sitter AST | Handles all languages, splits by function boundaries, token-budget aware |
| **MCP bidirectional** | Two protocols to maintain | Agent is both an MCP server (callable by IDE) AND an MCP client (calls Semgrep) |

## Quick Start

### Prerequisites

- Docker & Docker Compose
- One of: [Vertex AI (GCP)](https://cloud.google.com/vertex-ai) or [Gemini API key](https://aistudio.google.com/apikey)

### Setup

```bash
git clone <repo-url>
cd ai-code-review-agent

cp backend/.env.example backend/.env
# Edit backend/.env — set GCP_PROJECT_ID or GEMINI_API_KEY

docker compose up -d
```

### Usage

**Web UI:** Open `http://localhost:3000`

**CLI:**
```bash
python backend/cli.py https://github.com/owner/repo/pull/123
```

**Evaluation:**
```bash
docker exec ai-code-review-agent-backend-1 python -m evals.runner -v
```

**MCP Server (Claude Desktop):**
```bash
# See mcp-config.example.json for configuration
python backend/mcp_server.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/reviews` | Submit a PR for review |
| GET | `/api/v1/reviews` | List review history |
| GET | `/api/v1/reviews/{id}` | Get review details |
| POST | `/api/v1/webhook/github` | GitHub webhook receiver |
| GET | `/api/v1/health` | Health check |

## MCP Tools

| Tool | Direction | Description |
|------|-----------|-------------|
| `review_pull_request` | Server (exposed) | Review a GitHub PR by URL |
| `review_diff` | Server (exposed) | Review a raw git diff |
| `get_supported_languages` | Server (exposed) | List analyzable languages |
| `security_check` | Client (consumed) | Calls Semgrep MCP for SAST scan |

## Agents

| Agent | Responsibility | Key Checks |
|-------|---------------|------------|
| **Semgrep** | Deterministic SAST | CWE/OWASP rule-based scanning, 3000+ patterns |
| **Security** | Vulnerability detection (LLM) | SQL injection, XSS, hardcoded secrets, auth flaws, SSRF + Semgrep context |
| **Performance** | Efficiency analysis | N+1 queries, memory leaks, O(n²) algorithms, blocking I/O |
| **Style** | Code quality | Naming, DRY, SOLID, error handling, readability, type annotations |
| **Test Coverage** | Testing gaps | Missing tests, edge cases, assertion quality |
| **Aggregator** | Result merging | Deduplication, prioritization, false positive removal |
| **Meta Reviewer** | Final verdict | Overall score (0-10), recommendation, risk assessment |

## Project Structure

```
ai-code-review-agent/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── graph.py          # LangGraph pipeline (Semgrep → 4 agents → aggregator)
│   │   │   ├── llm.py            # Google GenAI SDK + structured output + retry
│   │   │   ├── schemas.py        # Pydantic response models for LLM output
│   │   │   └── prompts.py        # Agent system prompts
│   │   ├── api/routes.py         # FastAPI endpoints
│   │   ├── core/
│   │   │   ├── config.py         # Pydantic settings (Vertex AI / API key)
│   │   │   ├── database.py       # PostgreSQL async
│   │   │   └── cache.py          # Redis caching
│   │   ├── models/
│   │   │   ├── review.py         # SQLAlchemy models
│   │   │   └── schemas.py        # API Pydantic schemas
│   │   ├── services/
│   │   │   ├── github_service.py # GitHub API integration
│   │   │   ├── review_service.py # Review orchestration
│   │   │   └── semgrep_service.py# Semgrep MCP client + CLI fallback
│   │   ├── utils/code_parser.py  # Diff parsing & smart chunking
│   │   └── main.py               # FastAPI app
│   ├── evals/
│   │   ├── test_cases.py         # 8 known-bad code samples
│   │   └── runner.py             # Eval CLI with scoring metrics
│   ├── mcp_server.py             # MCP Server entry point
│   ├── cli.py                    # CLI entry point
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                  # Next.js pages
│   │   ├── components/           # React components + shadcn/ui
│   │   └── lib/api.ts            # API client
│   └── Dockerfile
├── mcp-config.example.json       # MCP client configuration
├── docker-compose.yml
└── README.md
```
