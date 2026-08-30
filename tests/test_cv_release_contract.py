from pathlib import Path
import tomllib


def test_package_version_preserves_v02_lineage() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert payload["project"]["version"].startswith("0.2.0")


def test_readme_documents_cv_factory_without_auto_send_claim() -> None:
    text = Path("README.md").read_text(encoding="utf-8")
    assert "CV Factory" in text
    assert "ApplicationPacket" in text
    assert "does not send" in text
    assert "does not submit" in text
    assert "profile/master_facts.local.yaml" in text
    assert "profile/evidence_catalog.local.yaml" in text
    assert "artifacts/applications/<application_id>/cv.pdf" in text


def test_cv_privacy_rules_preserve_existing_gitignore_contract() -> None:
    lines = {
        line.strip()
        for line in Path(".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    assert ".scrapy" in lines
    assert "activemq-data/" in lines
    assert "profile/master_facts.local.yaml" in lines
    assert "profile/evidence_catalog.local.yaml" in lines
    assert "artifacts/applications/" in lines


def test_renderer_v2_remains_ats_safe_by_source_contract() -> None:
    renderer_source = Path("app/cv/renderer.py").read_text(encoding="utf-8")

    assert 'renderer_version = "ats-pdf-v2"' in renderer_source
    assert 'body_font_name = "Helvetica"' in renderer_source
    assert 'bold_font_name = "Helvetica-Bold"' in renderer_source
    for forbidden in ("Image(", "Table(", "ImageReader", "registerFont", "TTFont"):
        assert forbidden not in renderer_source


def test_layout_qa_policy_thresholds_are_frozen() -> None:
    source = Path("app/cv/layout_qa.py").read_text(encoding="utf-8")

    assert "LOW_UTILIZATION = 0.58" in source
    assert "HIGH_UTILIZATION = 0.96" in source
    assert "TINY_TRAILING_PAGE_MAX_TOTAL_UTILIZATION = 1.20" in source
    assert "MAX_PAGES = 2" in source
    assert "MIN_BODY_FONT = 9.0" in source


def test_readme_documents_v02b1_polish_without_new_claim_authority() -> None:
    text = Path("README.md").read_text(encoding="utf-8")

    assert "V0.2B1" in text
    assert "ats-pdf-v2" in text
    assert "Layout QA" in text
    assert "one-column" in text
    assert "unsupported target skills remain gaps" in text


def test_roadmap_marks_v02b1_as_implemented_without_changing_next_provider_slice() -> None:
    text = Path("ROADMAP.md").read_text(encoding="utf-8")

    assert "✅ V0.2B1 — ATS Polished Renderer + Layout QA" in text
    assert "ats-pdf-v2" in text
    assert "Layout QA" in text
    assert "## NEXT — V0.2E2 — Conversation-provider adapter design" in text
