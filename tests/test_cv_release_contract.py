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
    assert "profile/*.local.yaml" in lines
    assert "*.local.yaml" in lines
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


def test_public_recruiter_fixtures_are_fictional() -> None:
    paths = [
        Path("tests/fixtures/recruiter_software.json"),
        Path("tests/fixtures/recruiter_tech_operations.json"),
    ]
    forbidden = [
        "juan.manuel.torres@",
        "+54 9 351",
        "master_facts.local.yaml",
        "evidence_catalog.local.yaml",
    ]
    payload = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for token in forbidden:
        assert token not in payload


def test_agent_runbook_opens_with_exact_safety_contract() -> None:
    expected = """# Opportunity OS Agent Runbook

DO NOT reconstruct CV generation from memory.
DO NOT hand-build recruiter PDFs when the canonical command is available.
PREPARED requires exactly one recruiter-quality A4 page.
PREPARED != APPROVE != SEND.
Private candidate snapshots and generated artifacts never enter the public repo.
"""
    text = Path("docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md").read_text(encoding="utf-8")
    assert text.startswith(expected)


def test_v02b2_docs_expose_canonical_recruiter_pipeline_and_command() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    runbook = Path("docs/OPPORTUNITY_OS_AGENT_RUNBOOK.md").read_text(encoding="utf-8")
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")

    flow = [
        "RadarAssessment",
        "EvidenceSelector",
        "CVComposer",
        "ClaimValidator",
        "RecruiterDocumentComposer",
        "RecruiterDocumentValidator",
        "RenderCV/Typst",
        "RecruiterQualityQA",
        "ApplicationPacket",
    ]
    for token in flow:
        assert token in readme
        assert token in runbook

    command = "python -m app.application.prepare"
    assert command in readme
    assert command in runbook
    assert "✅ V0.2B2" in roadmap
    assert "exactly one" in runbook
    assert "ACTIVE_POSTING" in runbook
    assert "TARGET_ACCOUNT" in runbook
    assert "unsupported" in runbook.casefold()


def test_ci_uses_single_dev_environment_for_recruiter_verification() -> None:
    workflow = Path(".github/workflows/tests.yml").read_text(encoding="utf-8")
    assert 'python -m pip install -e ".[dev]"' in workflow
    assert "python -m pytest" in workflow
    assert "python -m compileall app" in workflow
