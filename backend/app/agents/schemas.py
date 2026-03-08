"""
Pydantic schemas for structured LLM output.

These serve dual purpose:
1. Passed to Gemini's response_schema for guaranteed valid JSON
2. Used for post-generation validation with retry
"""

from enum import Enum
from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Finding(BaseModel):
    file: str = Field(description="File path where the issue was found")
    line: int = Field(description="Line number of the issue")
    severity: Severity = Field(description="Issue severity level")
    title: str = Field(description="Short descriptive title")
    description: str = Field(description="Detailed explanation of the issue")
    suggestion: str = Field(description="Concrete fix or improvement suggestion")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")


class SpecialistOutput(BaseModel):
    findings: list[Finding] = Field(default_factory=list, description="List of issues found")


class AggregatorOutput(BaseModel):
    findings: list[Finding] = Field(default_factory=list, description="Deduplicated findings")
    summary: str = Field(description="2-3 sentence overview")
    stats: dict = Field(default_factory=dict, description="Counts by severity")


class MetaReviewOutput(BaseModel):
    overall_score: float = Field(ge=0.0, le=10.0, description="Code quality score 0-10")
    recommendation: str = Field(description="approve, request_changes, or comment")
    summary: str = Field(description="Concise summary for PR comment")
    key_issues: list[str] = Field(default_factory=list, description="Top issues to address")
    positive_aspects: list[str] = Field(default_factory=list, description="Good things about the code")
    risk_assessment: str = Field(description="low, medium, or high")
