from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _public_docs() -> str:
    return "\n".join(
        [
            (ROOT / "README.md").read_text(encoding="utf-8"),
            (ROOT / "ROADMAP.md").read_text(encoding="utf-8"),
        ]
    )


def test_public_docs_expose_process_email_evidence_and_authority_boundary() -> None:
    docs = _public_docs()

    for required in (
        "Process Email",
        "selected inbound message",
        "body access != body persistence",
        "classification != authority",
        "APPLICATION_ACKNOWLEDGED",
        "OPPORTUNITY_PROCESS_EMAIL_ENABLED=false",
        "human confirmation",
    ):
        assert required in docs


def test_public_docs_describe_only_the_implemented_process_email_scope() -> None:
    docs = _public_docs().lower()

    assert "explicit inbound gmail message" in docs
    assert "transient full content" in docs
    assert "deterministic es/en" in docs
    assert "zero/one candidate operatorobservation" in docs
    assert "existing operator bridge preview" in docs
    assert "explicit human confirm/import" in docs
    assert "ack != process open" in docs

    for forbidden_claim in (
        "mailbox-wide sync is implemented",
        "automatic process mutation",
        "automatic process follow-up",
        "external llm classification",
        "attachments are classified",
        "gmail threads are classified",
    ):
        assert forbidden_claim not in docs


def test_roadmap_keeps_conversation_providers_future_and_does_not_expand_search_health_metrics() -> None:
    roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
    lowered = roadmap.lower()

    assert "Process Email" in roadmap
    assert "implemented" in lowered
    assert "whatsapp" in lowered
    assert "future" in lowered
    assert "search health offer" not in lowered
