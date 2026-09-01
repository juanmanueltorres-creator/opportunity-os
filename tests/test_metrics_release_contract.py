from pathlib import Path


def _public_docs() -> str:
    return "\n".join(
        [
            Path("README.md").read_text(encoding="utf-8"),
            Path("ROADMAP.md").read_text(encoding="utf-8"),
        ]
    ).lower()


def test_public_docs_describe_search_health_evidence_boundary():
    docs = _public_docs()

    assert "search health" in docs
    assert "complete" in docs
    assert "partial" in docs
    assert "unknown" in docs
    assert "native history != reconstructed history" in docs
    assert "missing evidence is not zero" in docs


def test_public_docs_keep_metrics_outside_action_authority():
    docs = _public_docs()

    assert "metrics do not grant" in docs
    assert "send" in docs
    assert "apply" in docs
    assert "follow-up" in docs
