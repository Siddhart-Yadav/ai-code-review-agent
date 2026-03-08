"""
GitHub integration service using PyGithub for API access.
Extracts PR diffs, file contents, and posts review comments.
Works without a token for public repos (read-only, 60 req/hr rate limit).
"""

import logging
import re
from dataclasses import dataclass

from github import Github, GithubException
from github.PullRequest import PullRequest

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


@dataclass
class PRInfo:
    repo_full_name: str
    pr_number: int
    title: str
    description: str
    url: str
    head_sha: str
    base_branch: str
    head_branch: str
    diff_text: str
    changed_files: list[dict]
    author: str


ALLOWED_GITHUB_HOSTS = {"github.com"}


def parse_pr_url(pr_url: str) -> tuple[str, int]:
    """Extract owner/repo and PR number from a GitHub PR URL.

    Only allows URLs from trusted GitHub hosts to prevent SSRF.
    """
    match = re.match(
        r"https://([^/]+)/([^/]+/[^/]+)/pull/(\d+)", pr_url
    )
    if not match:
        raise ValueError(f"Invalid GitHub PR URL: {pr_url}")

    host = match.group(1)
    if host not in ALLOWED_GITHUB_HOSTS:
        raise ValueError(f"Untrusted GitHub host: {host}")

    return match.group(2), int(match.group(3))


class GitHubService:
    def __init__(self, token: str | None = None):
        self.token = token or settings.GITHUB_TOKEN or None
        self.client = Github(self.token) if self.token else Github()

        if not self.token:
            logger.info("No GitHub token configured — using unauthenticated access (60 req/hr, public repos only)")

    @property
    def has_token(self) -> bool:
        return bool(self.token)

    async def get_pr_info(self, pr_url: str) -> PRInfo:
        repo_full_name, pr_number = parse_pr_url(pr_url)
        return await self._fetch_pr_data(repo_full_name, pr_number)

    async def get_pr_info_by_parts(self, repo_full_name: str, pr_number: int) -> PRInfo:
        return await self._fetch_pr_data(repo_full_name, pr_number)

    async def _fetch_pr_data(self, repo_full_name: str, pr_number: int) -> PRInfo:
        try:
            repo = self.client.get_repo(repo_full_name)
            pr: PullRequest = repo.get_pull(pr_number)

            # Fetch files once and reuse for both diff and file list (fixes N+1 API call)
            pr_files = list(pr.get_files())

            diff_text = self._get_diff_from_files(pr_files)

            changed_files = []
            for f in pr_files:
                changed_files.append({
                    "filename": f.filename,
                    "status": f.status,
                    "additions": f.additions,
                    "deletions": f.deletions,
                    "changes": f.changes,
                    "patch": f.patch or "",
                })

            return PRInfo(
                repo_full_name=repo_full_name,
                pr_number=pr_number,
                title=pr.title,
                description=pr.body or "",
                url=pr.html_url,
                head_sha=pr.head.sha,
                base_branch=pr.base.ref,
                head_branch=pr.head.ref,
                diff_text=diff_text,
                changed_files=changed_files,
                author=pr.user.login,
            )
        except GithubException as e:
            msg = e.data.get("message", str(e)) if hasattr(e, "data") and isinstance(e.data, dict) else str(e)
            raise RuntimeError(f"GitHub API error: {msg}") from e

    @staticmethod
    def _get_diff_from_files(pr_files: list) -> str:
        """Build unified diff from pre-fetched file list."""
        patches = []
        for f in pr_files:
            if f.patch:
                patches.append(
                    f"diff --git a/{f.filename} b/{f.filename}\n"
                    f"--- a/{f.filename}\n"
                    f"+++ b/{f.filename}\n"
                    f"{f.patch}"
                )
        return "\n".join(patches)

    async def post_review_comment(
        self,
        repo_full_name: str,
        pr_number: int,
        body: str,
        commit_sha: str | None = None,
    ):
        if not self.has_token:
            logger.info("Skipping PR comment — no GitHub token configured")
            return

        try:
            repo = self.client.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            pr.create_issue_comment(body)
        except GithubException as e:
            msg = e.data.get("message", str(e)) if hasattr(e, "data") and isinstance(e.data, dict) else str(e)
            raise RuntimeError(f"Failed to post comment: {msg}") from e

    async def post_inline_comments(
        self,
        repo_full_name: str,
        pr_number: int,
        commit_sha: str,
        comments: list[dict],
    ):
        """Post inline review comments on specific lines."""
        if not self.has_token:
            logger.info("Skipping inline comments — no GitHub token configured")
            return

        try:
            repo = self.client.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)
            commit = repo.get_commit(commit_sha)

            pr.create_review(
                commit=commit,
                body="AI Code Review Agent Analysis",
                event="COMMENT",
                comments=[
                    {
                        "path": c["file"],
                        "position": c.get("position", 1),
                        "body": c["body"],
                    }
                    for c in comments
                ],
            )
        except GithubException as e:
            msg = e.data.get("message", str(e)) if hasattr(e, "data") and isinstance(e.data, dict) else str(e)
            raise RuntimeError(f"Failed to post inline comments: {msg}") from e
