from datetime import datetime, timezone

import httpx
import pytest

from app.contributions.github_provider import (
    GitHubPublicContributionProvider,
    selection_from_github_url,
)
from app.contributions.observations import GitHubContributionSelection

NOW = datetime(2026, 9, 4, 7, 30, tzinfo=timezone.utc)
TOKEN = "ghp_super_secret_token"


def make_client(handler):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://api.github.com",
    )


def test_selection_from_issue_url():
    selection = selection_from_github_url(
        "https://github.com/trixocom/odoo-argentina-trx-ce/issues/1",
        operator_github_login="juan",
    )
    assert selection.resource_kind == "ISSUE"
    assert selection.repository_full_name == "trixocom/odoo-argentina-trx-ce"
    assert selection.number == 1
    assert selection.entry_id is None


def test_selection_from_pr_url_requires_explicit_entry_id():
    selection = selection_from_github_url(
        "https://github.com/WesleyHanauer/moracarta/pull/42",
        operator_github_login="juanmanueltorres-creator",
        entry_id="contrib-moracarta-25",
    )
    assert selection.resource_kind == "PULL_REQUEST"
    assert selection.repository_full_name == "WesleyHanauer/moracarta"
    assert selection.number == 42
    assert selection.entry_id == "contrib-moracarta-25"


def test_selection_rejects_non_github_or_malformed_url():
    with pytest.raises(ValueError):
        selection_from_github_url(
            "https://example.com/owner/repo/issues/1",
            operator_github_login="juan",
        )
    with pytest.raises(ValueError):
        selection_from_github_url(
            "https://github.com/owner/repo/issues/nope",
            operator_github_login="juan",
        )


def test_issue_fetch_is_get_only_and_discards_body():
    requests_seen = []

    def handler(request: httpx.Request):
        assert request.method == "GET"
        requests_seen.append((request.method, request.url.path))
        return httpx.Response(
            200,
            json={
                "number": 1,
                "html_url": "https://github.com/trixocom/odoo-argentina-trx-ce/issues/1",
                "title": "Invalid language code: es_419 en l10n_ar_edi_base",
                "state": "open",
                "body": "private-ish raw body must not persist",
                "assignees": [],
                "user": {"login": "fernandogiacomino"},
                "created_at": "2026-08-12T15:26:47Z",
                "updated_at": "2026-08-12T15:26:47Z",
                "closed_at": None,
            },
            request=request,
        )

    client = make_client(handler)
    provider = GitHubPublicContributionProvider(client)
    selection = selection_from_github_url(
        "https://github.com/trixocom/odoo-argentina-trx-ce/issues/1",
        operator_github_login="juan",
    )
    snapshot = provider.fetch(selection, captured_at=NOW)
    assert requests_seen == [
        ("GET", "/repos/trixocom/odoo-argentina-trx-ce/issues/1")
    ]
    assert snapshot.title.startswith("Invalid language")
    assert "body" not in snapshot.model_dump()
    assert "private-ish" not in snapshot.model_dump_json()


def test_issue_endpoint_rejects_pr_payload():
    def handler(request: httpx.Request):
        return httpx.Response(
            200,
            json={
                "number": 1,
                "html_url": "https://github.com/owner/repo/issues/1",
                "title": "actually a PR",
                "state": "open",
                "assignees": [],
                "user": {"login": "alice"},
                "created_at": "2026-09-01T00:00:00Z",
                "updated_at": "2026-09-01T00:00:00Z",
                "closed_at": None,
                "pull_request": {
                    "url": "https://api.github.com/repos/owner/repo/pulls/1"
                },
            },
            request=request,
        )

    provider = GitHubPublicContributionProvider(make_client(handler))
    selection = selection_from_github_url(
        "https://github.com/owner/repo/issues/1",
        operator_github_login="juan",
    )
    with pytest.raises(ValueError, match="pull request payload"):
        provider.fetch(selection, captured_at=NOW)


def test_optional_token_is_request_only_and_never_serialized():
    def handler(request: httpx.Request):
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(
            200,
            json={
                "number": 1,
                "html_url": "https://github.com/owner/repo/issues/1",
                "title": "Bug",
                "state": "open",
                "assignees": [],
                "user": {"login": "alice"},
                "created_at": "2026-09-01T00:00:00Z",
                "updated_at": "2026-09-01T00:00:00Z",
                "closed_at": None,
            },
            request=request,
        )

    provider = GitHubPublicContributionProvider(make_client(handler), token=TOKEN)
    selection = selection_from_github_url(
        "https://github.com/owner/repo/issues/1",
        operator_github_login="juan",
    )
    snapshot = provider.fetch(selection, captured_at=NOW)
    assert TOKEN not in snapshot.model_dump_json()


def test_token_is_not_leaked_in_http_error():
    def handler(request: httpx.Request):
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(500, json={"message": "boom"}, request=request)

    provider = GitHubPublicContributionProvider(make_client(handler), token=TOKEN)
    selection = selection_from_github_url(
        "https://github.com/owner/repo/issues/1",
        operator_github_login="juan",
    )
    with pytest.raises(httpx.HTTPStatusError) as exc:
        provider.fetch(selection, captured_at=NOW)
    assert TOKEN not in str(exc.value)


def test_pr_fetch_reads_only_required_subresources_and_discards_text():
    requests_seen = []

    def handler(request: httpx.Request):
        assert request.method == "GET"
        requests_seen.append((request.method, request.url.path))
        path = request.url.path
        if path.endswith("/pulls/42"):
            payload = {
                "number": 42,
                "html_url": "https://github.com/WesleyHanauer/moracarta/pull/42",
                "state": "open",
                "merged": False,
                "draft": False,
                "body": "Closes #25 should remain transient",
                "user": {"login": "juanmanueltorres-creator"},
                "created_at": "2026-09-04T02:22:25Z",
                "updated_at": "2026-09-04T02:22:25Z",
                "closed_at": None,
                "merged_at": None,
                "head": {"sha": "abc123"},
            }
        elif path.endswith("/pulls/42/reviews"):
            payload = [
                {
                    "id": 99,
                    "user": {"login": "maintainer"},
                    "state": "APPROVED",
                    "submitted_at": "2026-09-04T03:00:00Z",
                    "body": "LGTM raw review text",
                },
                {
                    "id": 100,
                    "user": {"login": "maintainer"},
                    "state": "PENDING",
                    "submitted_at": None,
                    "body": "ignored",
                },
            ]
        elif path.endswith("/commits/abc123/check-runs"):
            payload = {
                "check_runs": [
                    {
                        "id": 7,
                        "name": "CI",
                        "status": "completed",
                        "conclusion": "failure",
                        "completed_at": "2026-09-04T03:01:00Z",
                        "output": {
                            "title": "tests failed",
                            "summary": "raw log-like text",
                        },
                    },
                    {
                        "id": 8,
                        "name": "Deploy",
                        "status": "completed",
                        "conclusion": "action_required",
                        "completed_at": "2026-09-04T03:02:00Z",
                        "output": {
                            "title": "authorization",
                            "summary": "secret-ish message",
                        },
                    },
                ]
            }
        elif path.endswith("/commits/abc123/status"):
            payload = {
                "statuses": [
                    {
                        "id": 44,
                        "context": "Vercel",
                        "state": "failure",
                        "description": "team authorization required",
                        "updated_at": "2026-09-04T03:03:00Z",
                    }
                ]
            }
        else:
            raise AssertionError(path)
        return httpx.Response(200, json=payload, request=request)

    provider = GitHubPublicContributionProvider(make_client(handler))
    selection = selection_from_github_url(
        "https://github.com/WesleyHanauer/moracarta/pull/42",
        operator_github_login="juanmanueltorres-creator",
        entry_id="contrib-moracarta-25",
    )
    snapshot = provider.fetch(selection, captured_at=NOW)
    assert requests_seen == [
        ("GET", "/repos/WesleyHanauer/moracarta/pulls/42"),
        ("GET", "/repos/WesleyHanauer/moracarta/pulls/42/reviews"),
        ("GET", "/repos/WesleyHanauer/moracarta/commits/abc123/check-runs"),
        ("GET", "/repos/WesleyHanauer/moracarta/commits/abc123/status"),
    ]
    assert len(snapshot.reviews) == 1
    assert snapshot.reviews[0].state == "APPROVED"
    checks = {check.check_ref: check for check in snapshot.checks}
    assert checks["check-run:7"].description_code is None
    assert (
        checks["check-run:8"].description_code
        == "EXTERNAL_AUTHORIZATION_REQUIRED"
    )
    assert checks["status:44"].description_code == "EXTERNAL_AUTHORIZATION_REQUIRED"
    serialized = snapshot.model_dump_json().lower()
    assert "closes #25" not in serialized
    assert "lgtm raw" not in serialized
    assert "raw log-like" not in serialized
    assert "secret-ish" not in serialized
    assert "team authorization required" not in serialized


def test_manually_constructed_mismatched_selection_fails_before_provider():
    with pytest.raises(Exception):
        GitHubContributionSelection(
            resource_kind="ISSUE",
            repository_full_name="owner/repo",
            number=2,
            source_url="https://github.com/owner/repo/issues/1",
            operator_github_login="juan",
        )
