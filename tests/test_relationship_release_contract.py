from pathlib import Path

from app.main import create_app


def test_relationship_private_paths_are_configured_ignored_and_ci_guarded() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")
    gitignore = Path(".gitignore").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")

    assert "OPPORTUNITY_RELATIONSHIPS_PATH=state/relationships.local.sqlite3" in env_example
    assert "state/relationships.local.sqlite3" in gitignore
    assert "state/relationships.local.sqlite3-*" in gitignore
    assert "artifacts/relationships/*.local.*" in gitignore
    assert "state/relationships.local.sqlite3" in workflow
    assert "artifacts/relationships/**" in workflow


def test_relationship_api_surface_is_read_only() -> None:
    api = create_app(
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )
    paths = api.openapi()["paths"]
    relationship_paths = {
        path: operations
        for path, operations in paths.items()
        if path.startswith("/api/v1/relationships")
    }

    assert set(relationship_paths) == {
        "/api/v1/relationships/context",
        "/api/v1/relationships/{account_id}/context",
    }
    for operations in relationship_paths.values():
        assert "get" in operations
        for forbidden in ("post", "put", "patch", "delete"):
            assert forbidden not in operations


def test_readme_documents_relationship_memory_without_provider_sync_claims() -> None:
    text = Path("README.md").read_text(encoding="utf-8")

    assert "V0.2D" in text
    assert "Relationship Memory" in text
    assert "Context Bridge" in text
    assert "FOLLOW_UP" in text
    assert "DORMANT" in text
    assert "OPPORTUNITY_RELATIONSHIPS_PATH" in text
    assert "GET  /api/v1/relationships/context" in text
    assert "GET  /api/v1/relationships/{account_id}/context" in text
    assert "no importa automáticamente Gmail, Apollo ni el CRM" in text
    assert "CV Factory does not send email and does not submit applications" in text
    assert "Opportunity OS does not create Gmail drafts automatically" in text
    assert "Approval is not a send command" in text


def test_roadmap_marks_v02d_done_and_operator_integration_next() -> None:
    text = Path("ROADMAP.md").read_text(encoding="utf-8")

    assert "### ✅ V0.2D — Relationship Memory / Context Bridge" in text
    assert "## NEXT — Operator integration" in text
    assert "Relationship Memory" in text
    assert "FOLLOW_UP" in text


def test_v02d_spec_is_marked_approved() -> None:
    text = Path(
        "docs/superpowers/specs/2026-08-29-opportunity-os-v0.2d-relationship-memory-context-bridge-design.md"
    ).read_text(encoding="utf-8")
    assert "Status: approved" in text.splitlines()[:8]


def test_relationship_core_has_no_gmail_or_apollo_dependency() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted(Path("app/relationships").glob("*.py"))
    )
    assert "import gmail" not in combined
    assert "from gmail" not in combined
    assert "import apollo" not in combined
    assert "from apollo" not in combined
