from pathlib import Path
import tomllib


def test_package_version_is_v02b_prerelease() -> None:
    payload = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    assert payload["project"]["version"] == "0.2.0b1"


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
