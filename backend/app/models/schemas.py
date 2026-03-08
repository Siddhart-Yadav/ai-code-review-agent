from pydantic import BaseModel, Field, HttpUrl
from datetime import datetime
from enum import Enum


class ReviewRequest(BaseModel):
    pr_url: str = Field(..., description="Full GitHub PR URL")
    triggered_by: str = Field(default="web_ui", pattern="^(web_ui|github_action|cli)$")


class WebhookPayload(BaseModel):
    action: str
    number: int
    pull_request: dict
    repository: dict


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Finding(BaseModel):
    file: str
    line_start: int
    line_end: int | None = None
    severity: Severity
    category: str  # security | performance | style | test_coverage
    title: str
    description: str
    suggestion: str | None = None
    code_snippet: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class AgentResult(BaseModel):
    agent_name: str
    findings: list[Finding] = []
    summary: str
    score: float = Field(ge=0.0, le=10.0)
    execution_time_ms: int


class MetaReviewResult(BaseModel):
    overall_score: float = Field(ge=0.0, le=10.0)
    recommendation: str = Field(pattern="^(approve|request_changes|comment)$")
    summary: str
    key_issues: list[str]
    positive_aspects: list[str]
    risk_assessment: str


class ReviewResponse(BaseModel):
    id: str
    repo_full_name: str
    pr_number: int
    pr_title: str | None
    pr_url: str | None
    status: str
    overall_score: float | None
    summary: str | None
    recommendation: str | None
    security_findings: list[dict] = []
    performance_findings: list[dict] = []
    style_findings: list[dict] = []
    test_coverage_findings: list[dict] = []
    meta_review: dict = {}
    files_reviewed: int = 0
    total_issues: int = 0
    created_at: datetime | None
    completed_at: datetime | None
    duration_seconds: float | None
    triggered_by: str | None

    class Config:
        from_attributes = True


class ReviewListItem(BaseModel):
    id: str
    repo_full_name: str
    pr_number: int
    pr_title: str | None
    status: str
    overall_score: float | None
    recommendation: str | None
    total_issues: int
    created_at: datetime | None

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    redis: str
