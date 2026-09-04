from __future__ import annotations

import importlib
from pathlib import Path
import subprocess

from app.contributions.github_provider import GitHubPublicContributionProvider
from app.contributions.observations import ContributionImportReceipt, ContributionObservation


def test_contribution_intake_does_not_register_fastapi_routes():
    from app.main import app as fastapi_app

    before = set(fastapi_app.openapi()["paths"])
    importlib.import_module("app.contributions.bridge")
    importlib.import_module("app.contributions.intake_cli")

    fastapi_app.openapi_schema = None
    after = set(fastapi_app.openapi()["paths"])
    assert after == before


def test_contribution_runtime_has_no_cross_domain_imports():
    forbidden = [
        "app.relationships",
        "app.operator_bridge",
        "app.outreach",
        "app.process_email",
        "app.cv",
    ]
    paths = [
        Path("app/contributions/observations.py"),
        Path("app/contributions/repository.py"),
        Path("app/contributions/github_provider.py"),
        Path("app/contributions/normalizer.py"),
        Path("app/contributions/bridge.py"),
        Path("app/contributions/intake_cli.py"),
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for module in forbidden:
        assert module not in text


def test_observation_and_receipt_fields_have_no_hiring_authority_names():
    field_names = {
        *ContributionObservation.model_fields,
        *ContributionImportReceipt.model_fields,
    }
    lowered = " ".join(sorted(field_names)).lower()
    for forbidden in ["employment", "salary", "hiring", "contact_permission"]:
        assert forbidden not in lowered


def test_provider_exposes_no_github_mutation_methods():
    for name in ["post", "put", "patch", "delete", "assign", "comment", "merge"]:
        assert not hasattr(GitHubPublicContributionProvider, name)


def test_pyproject_is_unchanged_in_feature_diff():
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD", "--", "pyproject.toml"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == ""


def test_workflow_private_guard_contains_contribution_sqlite_glob():
    workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")
    assert "state/contributions.local.sqlite3*" in workflow
