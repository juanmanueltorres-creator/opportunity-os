from pathlib import Path
import tomllib

from app.main import create_app


def test_package_version_is_v02c_prerelease() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert payload["project"]["version"] == "0.2.0c1"


def test_fastapi_metadata_matches_v02c_prerelease() -> None:
    api = create_app(enable_default_radar=False)
    assert api.version == "0.2.0c1"


def test_readme_documents_operator_boundary() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "V0.2C" in text
    assert "does not create Gmail drafts automatically" in text
    assert "Approval is not a send command" in text
    assert "ApplicationPacket" in text
    assert "OutreachBrief" in text
    assert "SendRequest" in text
    assert "SendReceipt" in text


def test_outreach_private_paths_are_ignored_and_ci_guarded() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")
    assert "state/outreach.local.sqlite3" in gitignore
    assert "artifacts/applications/*/outreach/" in gitignore
    assert "state/outreach.local.sqlite3" in workflow
    assert "artifacts/applications/**/outreach/**" in workflow


def test_existing_privacy_rules_remain_present() -> None:
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")
    for required in (
        ".scrapy",
        "activemq-data/",
        "profile/master_facts.local.yaml",
        "profile/evidence_catalog.local.yaml",
        "artifacts/applications/",
    ):
        assert required in gitignore
    for required in (
        ".env",
        "profile.local.yaml",
        "sources.local.yaml",
        "profile/master_facts.local.yaml",
        "profile/evidence_catalog.local.yaml",
        "artifacts/applications/**",
        "*.pdf",
        "*.docx",
    ):
        assert required in workflow


def test_v02c_spec_is_marked_approved() -> None:
    text = Path(
        "docs/superpowers/specs/2026-08-28-opportunity-os-v0.2c-email-outreach-design.md"
    ).read_text(encoding="utf-8")
    assert "Status: approved" in text.splitlines()[:8]
