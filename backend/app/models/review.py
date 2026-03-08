import uuid
from datetime import datetime

from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, Float, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
import enum

from app.core.database import Base


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class Review(Base):
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    repo_full_name = Column(String(255), nullable=False, index=True)
    pr_number = Column(Integer, nullable=False)
    pr_title = Column(String(500))
    pr_url = Column(String(500))
    commit_sha = Column(String(40))
    diff_hash = Column(String(64), index=True)
    status = Column(SAEnum(ReviewStatus), default=ReviewStatus.PENDING)

    # Agent results stored as JSON
    security_findings = Column(JSON, default=list)
    performance_findings = Column(JSON, default=list)
    style_findings = Column(JSON, default=list)
    test_coverage_findings = Column(JSON, default=list)
    aggregated_findings = Column(JSON, default=list)
    meta_review = Column(JSON, default=dict)

    overall_score = Column(Float)
    summary = Column(Text)
    recommendation = Column(String(50))  # approve / request_changes / comment

    files_reviewed = Column(Integer, default=0)
    total_issues = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    triggered_by = Column(String(50))  # web_ui / github_action / cli

    def __repr__(self):
        return f"<Review {self.repo_full_name}#{self.pr_number}>"
