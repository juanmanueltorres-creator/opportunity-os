from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.contributions.observations import (
    GitHubCheckSnapshot,
    GitHubContributionSelection,
    GitHubIssueSnapshot,
    GitHubPullRequestSnapshot,
    GitHubReviewSnapshot,
)

_ALLOWED_REVIEW_STATES = {"APPROVED", "COMMENTED", "CHANGES_REQUESTED", "DISMISSED"}
_AUTHORIZATION_PHRASES = (
    "team authorization required",
    "authorization required",
    "permission required",
    "access authorization required",
)


class GitHubContributionProvider(Protocol):
    def fetch(
        self,
        selection: GitHubContributionSelection,
        *,
        captured_at: datetime,
    ) -> GitHubIssueSnapshot | GitHubPullRequestSnapshot: ...


def _parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("GitHub timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _authorization_code(*values: str | None) -> str | None:
    text = " ".join(value for value in values if value).casefold()
    if any(phrase in text for phrase in _AUTHORIZATION_PHRASES):
        return "EXTERNAL_AUTHORIZATION_REQUIRED"
    return None


def selection_from_github_url(
    url: str,
    *,
    operator_github_login: str,
    entry_id: str | None = None,
) -> GitHubContributionSelection:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        raise ValueError("URL must be a public https://github.com issue or pull request")
    if parsed.query or parsed.fragment or parsed.params:
        raise ValueError("GitHub selection URL cannot contain query, fragment, or params")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 4:
        raise ValueError("GitHub selection URL must identify exactly one issue or pull request")
    owner, repo, resource, raw_number = parts
    if resource not in {"issues", "pull"}:
        raise ValueError("GitHub selection URL must contain issues or pull")
    try:
        number = int(raw_number)
    except ValueError as exc:
        raise ValueError("GitHub resource number must be an integer") from exc
    kind = "ISSUE" if resource == "issues" else "PULL_REQUEST"
    return GitHubContributionSelection(
        resource_kind=kind,
        repository_full_name=f"{owner}/{repo}",
        number=number,
        source_url=url,
        operator_github_login=operator_github_login,
        entry_id=entry_id,
    )


class GitHubPublicContributionProvider:
    def __init__(self, client: httpx.Client, *, token: str | None = None) -> None:
        self._client = client
        self._token = token

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "opportunity-os-contribution-intake",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _get_json(self, path: str):
        response = self._client.get(path, headers=self._headers())
        response.raise_for_status()
        return response.json()

    def _fetch_issue(
        self,
        selection: GitHubContributionSelection,
        *,
        captured_at: datetime,
    ) -> GitHubIssueSnapshot:
        payload = self._get_json(
            f"/repos/{selection.repository_full_name}/issues/{selection.number}"
        )
        if "pull_request" in payload:
            raise ValueError("issue endpoint returned pull request payload")
        return GitHubIssueSnapshot(
            repository_full_name=selection.repository_full_name,
            issue_number=selection.number,
            issue_url=payload["html_url"],
            title=payload["title"],
            state=str(payload["state"]).upper(),
            assignee_logins=[
                item["login"] for item in payload.get("assignees", []) if item.get("login")
            ],
            author_login=(payload.get("user") or {}).get("login"),
            created_at=_parse_time(payload["created_at"]),
            updated_at=_parse_time(payload["updated_at"]),
            closed_at=_parse_time(payload.get("closed_at")),
            captured_at=captured_at,
        )

    def _reviews(self, selection: GitHubContributionSelection) -> list[GitHubReviewSnapshot]:
        payload = self._get_json(
            f"/repos/{selection.repository_full_name}/pulls/{selection.number}/reviews"
        )
        reviews: list[GitHubReviewSnapshot] = []
        for item in payload:
            state = str(item.get("state") or "").upper()
            submitted_at = _parse_time(item.get("submitted_at"))
            if state not in _ALLOWED_REVIEW_STATES or submitted_at is None:
                continue
            review_id = item.get("id")
            if review_id is None:
                continue
            reviews.append(
                GitHubReviewSnapshot(
                    review_ref=f"review:{review_id}",
                    reviewer_login=(item.get("user") or {}).get("login"),
                    state=state,
                    submitted_at=submitted_at,
                )
            )
        return reviews

    def _checks(
        self,
        selection: GitHubContributionSelection,
        *,
        head_sha: str,
        captured_at: datetime,
    ) -> list[GitHubCheckSnapshot]:
        check_payload = self._get_json(
            f"/repos/{selection.repository_full_name}/commits/{head_sha}/check-runs"
        )
        status_payload = self._get_json(
            f"/repos/{selection.repository_full_name}/commits/{head_sha}/status"
        )
        checks: list[GitHubCheckSnapshot] = []
        for item in check_payload.get("check_runs", []):
            check_id = item.get("id")
            if check_id is None:
                continue
            conclusion = str(item.get("conclusion") or item.get("status") or "UNKNOWN")
            output = item.get("output") or {}
            description_code = None
            if conclusion.upper() == "ACTION_REQUIRED":
                description_code = "EXTERNAL_AUTHORIZATION_REQUIRED"
            else:
                description_code = _authorization_code(
                    output.get("title"),
                    output.get("summary"),
                )
            fact_at = (
                _parse_time(item.get("completed_at"))
                or _parse_time(item.get("started_at"))
                or captured_at
            )
            checks.append(
                GitHubCheckSnapshot(
                    check_ref=f"check-run:{check_id}",
                    name=str(item.get("name") or "GitHub check"),
                    state_or_conclusion=conclusion,
                    description_code=description_code,
                    fact_at=fact_at,
                )
            )

        for item in status_payload.get("statuses", []):
            status_id = item.get("id")
            if status_id is None:
                continue
            checks.append(
                GitHubCheckSnapshot(
                    check_ref=f"status:{status_id}",
                    name=str(item.get("context") or "GitHub status"),
                    state_or_conclusion=str(item.get("state") or "UNKNOWN"),
                    description_code=_authorization_code(item.get("description")),
                    fact_at=(
                        _parse_time(item.get("updated_at"))
                        or _parse_time(item.get("created_at"))
                        or captured_at
                    ),
                )
            )
        return checks

    def _fetch_pull_request(
        self,
        selection: GitHubContributionSelection,
        *,
        captured_at: datetime,
    ) -> GitHubPullRequestSnapshot:
        payload = self._get_json(
            f"/repos/{selection.repository_full_name}/pulls/{selection.number}"
        )
        head_sha = payload["head"]["sha"]
        reviews = self._reviews(selection)
        checks = self._checks(selection, head_sha=head_sha, captured_at=captured_at)
        return GitHubPullRequestSnapshot(
            repository_full_name=selection.repository_full_name,
            pr_number=selection.number,
            pr_url=payload["html_url"],
            state=str(payload["state"]).upper(),
            merged=bool(payload.get("merged")),
            draft=bool(payload.get("draft")),
            author_login=(payload.get("user") or {}).get("login"),
            created_at=_parse_time(payload["created_at"]),
            updated_at=_parse_time(payload["updated_at"]),
            closed_at=_parse_time(payload.get("closed_at")),
            merged_at=_parse_time(payload.get("merged_at")),
            head_sha=head_sha,
            reviews=reviews,
            checks=checks,
            captured_at=captured_at,
        )

    def fetch(
        self,
        selection: GitHubContributionSelection,
        *,
        captured_at: datetime,
    ) -> GitHubIssueSnapshot | GitHubPullRequestSnapshot:
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("captured_at must be timezone-aware")
        captured_at = captured_at.astimezone(timezone.utc)
        if selection.resource_kind == "ISSUE":
            return self._fetch_issue(selection, captured_at=captured_at)
        return self._fetch_pull_request(selection, captured_at=captured_at)
