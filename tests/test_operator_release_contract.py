from pathlib import Path

from app.main import create_app
from app.operator_bridge.models import OperatorObservation


def test_operator_bridge_has_no_provider_network_or_send_dependency() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted(Path("app/operator_bridge").glob("*.py"))
    )
    forbidden = {
        "import gmail",
        "from gmail",
        "import apollo",
        "from apollo",
        "import httpx",
        "from httpx",
        "import requests",
        "from requests",
        "sqliteoutreachrepository",
        "sendgate",
        "record_successful_send",
        "sendreceipt",
    }
    assert [token for token in sorted(forbidden) if token in text] == []


def test_operator_observation_contract_forbids_raw_provider_archives() -> None:
    forbidden_fields = {
        "body",
        "raw_body",
        "message_body",
        "raw_payload",
        "provider_payload",
        "mailbox_dump",
        "conversation_history",
        "metadata",
    }
    assert forbidden_fields.isdisjoint(OperatorObservation.model_fields)


def test_operator_routes_are_absent_from_default_openapi() -> None:
    api = create_app(
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )
    assert not any(path.startswith("/api/v1/operator/") for path in api.openapi()["paths"])


def test_operator_import_flag_is_documented_disabled_by_default() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")
    assert "OPPORTUNITY_OPERATOR_IMPORT_ENABLED=false" in env_example


def test_readme_documents_observe_preview_confirm_boundary() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "V0.2E" in text
    assert "Operator Observation Bridge" in text
    assert "Observe → preview → confirm → import local fact" in text
    assert (
        "An imported observation is evidence about what happened; "
        "it is not authority to make something happen."
    ) in text
    assert "CV Factory does not send email and does not submit applications" in text
    assert "Opportunity OS does not create Gmail drafts automatically" in text
    assert "Approval is not a send command" in text


def test_roadmap_keeps_v02e_done_after_gmail_read_release() -> None:
    text = Path("ROADMAP.md").read_text(encoding="utf-8")
    assert "### ✅ V0.2E — Operator Observation Bridge" in text
    assert "### ✅ V0.2E1 — Gmail Read Adapter" in text
    assert "bridge sigue provider-neutral" in text


def test_v02e_spec_is_marked_approved() -> None:
    text = Path(
        "docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e-operator-observation-bridge-design.md"
    ).read_text(encoding="utf-8")
    assert "Status: approved" in text.splitlines()[:8]
