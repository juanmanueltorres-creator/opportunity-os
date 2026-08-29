from pathlib import Path

from app.adapters.gmail_read.models import GmailMessageEnvelope, GmailObservationResult
from app.adapters.gmail_read.provider import GmailReadProvider
from app.main import create_app


FORBIDDEN_MODEL_FIELDS = {
    "body",
    "raw_body",
    "message_body",
    "raw_payload",
    "provider_payload",
    "token",
    "access_token",
    "attachments",
    "metadata",
}


def _gmail_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(Path("app/adapters/gmail_read").glob("*.py"))
    )


def test_operator_bridge_remains_provider_neutral() -> None:
    text = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for path in sorted(Path("app/operator_bridge").glob("*.py"))
    )
    assert "gmail_read" not in text
    assert "gmail.googleapis" not in text
    assert "gmailrestreadprovider" not in text


def test_gmail_domain_models_forbid_raw_content_and_credentials() -> None:
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(GmailMessageEnvelope.model_fields)
    assert FORBIDDEN_MODEL_FIELDS.isdisjoint(GmailObservationResult.model_fields)


def test_gmail_provider_protocol_exposes_read_operations_only() -> None:
    public_methods = {
        name
        for name, value in GmailReadProvider.__dict__.items()
        if callable(value) and not name.startswith("_")
    }
    assert public_methods == {"get_message", "get_thread"}


def test_gmail_adapter_has_no_relationship_import_or_outreach_send_dependency() -> None:
    text = _gmail_source().lower()
    forbidden = {
        "import_observation(",
        "sqliterelationshiprepository",
        "relationshipservice",
        "sendgate",
        "sendreceipt",
        "record_successful_send",
        "def send(",
        "def reply(",
        "def create_draft(",
        "def update_draft(",
        "def trash(",
        "def archive(",
        "def modify_labels(",
        "def mark_read(",
    }
    assert [token for token in sorted(forbidden) if token in text] == []


def test_gmail_route_is_absent_from_default_openapi() -> None:
    api = create_app(
        enable_default_radar=False,
        enable_default_targets=False,
        enable_default_relationships=False,
    )
    assert "/api/v1/adapters/gmail/observe" not in api.openapi()["paths"]


def test_gmail_read_flag_is_documented_disabled_by_default_without_secret() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")
    assert "OPPORTUNITY_GMAIL_READ_ENABLED=false" in env_example
    assert "GMAIL_ACCESS_TOKEN=" not in env_example
    assert "GMAIL_REFRESH_TOKEN=" not in env_example


def test_readme_documents_selective_gmail_read_without_write_authority() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "Gmail Read Adapter V0.2E1" in text
    assert "selected Gmail message/thread" in text
    assert "OperatorObservation" in text
    assert "does not create drafts" in text
    assert "does not send" in text
    assert "does not import Relationship Memory" in text


def test_roadmap_marks_v02e1_done_and_whatsapp_as_future_not_implemented() -> None:
    text = Path("ROADMAP.md").read_text(encoding="utf-8")
    assert "### ✅ V0.2E1 — Gmail Read Adapter" in text
    assert "WhatsApp" in text
    assert "candidate" in text.lower() or "candidato" in text.lower()
    assert "WhatsApp Relationship Adapter ✅" not in text


def test_v02e1_spec_is_marked_approved() -> None:
    text = Path(
        "docs/superpowers/specs/2026-08-29-opportunity-os-v0.2e1-gmail-read-adapter-design.md"
    ).read_text(encoding="utf-8")
    assert "Status: approved" in text.splitlines()[:8]
