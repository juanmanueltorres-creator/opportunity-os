from pathlib import Path

import pytest

from app.cv.loaders import (
    load_evidence_catalog,
    load_master_facts,
    validate_catalog_against_facts,
)

ROOT = Path(__file__).parents[1]


def _verified_skill_yaml(fact_id: str, value: str) -> str:
    return (
        f"  - id: {fact_id}\n"
        "    kind: skill\n"
        f"    value: {value}\n"
        "    track_ids: [tech]\n"
        "    verified: true\n"
        "    verification_method: repository_evidence\n"
        "    verified_at: 2026-08-28T12:00:00+00:00\n"
        f"    source_ref: https://example.test/{fact_id}\n"
    )


def test_master_facts_hash_is_independent_of_yaml_item_order(tmp_path: Path) -> None:
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    python = _verified_skill_yaml("skill-python", "Python")
    postgis = _verified_skill_yaml("skill-postgis", "PostGIS")
    a.write_text(
        "schema_version: v1\nfacts:\n" + python + postgis,
        encoding="utf-8",
    )
    b.write_text(
        "schema_version: v1\nfacts:\n" + postgis + python,
        encoding="utf-8",
    )

    first = load_master_facts(a)
    second = load_master_facts(b)

    assert [fact.id for fact in first.facts] == ["skill-postgis", "skill-python"]
    assert first.content_sha256 == second.content_sha256


def test_duplicate_fact_ids_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "facts.yaml"
    path.write_text(
        "schema_version: v1\n"
        "facts:\n"
        "  - id: same\n"
        "    kind: skill\n"
        "    value: Python\n"
        "    verified: false\n"
        "  - id: same\n"
        "    kind: skill\n"
        "    value: SQL\n"
        "    verified: false\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate fact id"):
        load_master_facts(path)


def test_loader_errors_do_not_echo_private_yaml_contents(tmp_path: Path) -> None:
    secret = "PRIVATE-SENTINEL-DO-NOT-ECHO"
    path = tmp_path / "broken.yaml"
    path.write_text(f"schema_version: [\nsecret: {secret}\n", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        load_master_facts(path)

    assert secret not in str(exc_info.value)


def test_catalog_validation_rejects_missing_fact_reference(tmp_path: Path) -> None:
    facts_path = tmp_path / "facts.yaml"
    facts_path.write_text(
        "schema_version: v1\n"
        "facts:\n"
        "  - id: skill-python\n"
        "    kind: skill\n"
        "    value: Python\n"
        "    track_ids: [tech]\n"
        "    verified: false\n",
        encoding="utf-8",
    )
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "schema_version: v1\n"
        "modules:\n"
        "  - id: module-tech\n"
        "    track_ids: [tech]\n"
        "    label: Technical evidence\n"
        "    fact_ids: [missing-fact]\n"
        "    verified: false\n",
        encoding="utf-8",
    )

    facts = load_master_facts(facts_path)
    catalog = load_evidence_catalog(catalog_path)

    with pytest.raises(ValueError, match="missing-fact"):
        validate_catalog_against_facts(catalog, facts)


def test_verified_module_cannot_depend_on_unverified_fact(tmp_path: Path) -> None:
    facts_path = tmp_path / "facts.yaml"
    facts_path.write_text(
        "schema_version: v1\n"
        "facts:\n"
        "  - id: skill-python\n"
        "    kind: skill\n"
        "    value: Python\n"
        "    track_ids: [tech]\n"
        "    verified: false\n",
        encoding="utf-8",
    )
    catalog_path = tmp_path / "catalog.yaml"
    catalog_path.write_text(
        "schema_version: v1\n"
        "modules:\n"
        "  - id: module-tech\n"
        "    track_ids: [tech]\n"
        "    label: Technical evidence\n"
        "    fact_ids: [skill-python]\n"
        "    verified: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unverified fact"):
        validate_catalog_against_facts(
            load_evidence_catalog(catalog_path),
            load_master_facts(facts_path),
        )


def test_public_examples_are_fictional_and_loadable() -> None:
    facts_path = ROOT / "config" / "master_facts.example.yaml"
    catalog_path = ROOT / "config" / "evidence_catalog.example.yaml"

    facts = load_master_facts(facts_path)
    catalog = load_evidence_catalog(catalog_path)
    validate_catalog_against_facts(catalog, facts)

    raw = facts_path.read_text(encoding="utf-8") + catalog_path.read_text(encoding="utf-8")
    assert "Alex Example" in raw
    assert "example.test" in raw
    assert {"tech", "hospitality"}.issubset(
        {track for fact in facts.facts for track in fact.track_ids}
    )


def test_private_cv_paths_are_gitignored_and_guarded_by_ci() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "tests.yml").read_text(
        encoding="utf-8"
    )

    for path in (
        "profile/master_facts.local.yaml",
        "profile/evidence_catalog.local.yaml",
        "artifacts/applications/",
    ):
        assert path in gitignore

    assert "profile/master_facts.local.yaml" in workflow
    assert "profile/evidence_catalog.local.yaml" in workflow
    assert "artifacts/applications/**" in workflow
