from pathlib import Path

from app.radar.taxonomy import AliasRegistry, TaxonomyResolver


DATA_PATH = Path("data/skill_aliases.yaml")


def _resolver(*, taxonomy_path: Path | None = None) -> TaxonomyResolver:
    return TaxonomyResolver(
        alias_registry=AliasRegistry.load(DATA_PATH),
        taxonomy_path=taxonomy_path,
    )


def test_exact_candidate_skill_has_full_weight() -> None:
    result = _resolver().resolve_skill("python", ["Python", "SQL"])

    assert result.level == "EXACT_VERIFIED"
    assert result.matched_skill == "Python"
    assert result.multiplier == 1.0


def test_approved_equivalence_scores_as_exact() -> None:
    result = _resolver().resolve_skill("postgres", ["PostgreSQL"])

    assert result.level == "APPROVED_ALIAS"
    assert result.matched_skill == "PostgreSQL"
    assert result.multiplier == 1.0


def test_related_term_is_not_silent_equivalence() -> None:
    result = _resolver().resolve_skill("spatial database", ["PostGIS"])

    assert result.level == "TAXONOMY_RELATED"
    assert result.matched_skill == "PostGIS"
    assert result.multiplier == 0.70


def test_spanish_generic_database_requirement_is_related_to_postgresql() -> None:
    result = _resolver().resolve_skill("bases de datos", ["PostgreSQL"])

    assert result.level == "TAXONOMY_RELATED"
    assert result.matched_skill == "PostgreSQL"
    assert result.multiplier == 0.70
    assert result.taxonomy_source == "aliases:2"


def test_unknown_skill_has_zero_weight() -> None:
    result = _resolver().resolve_skill("COBOL", ["Python", "PostGIS"])

    assert result.level == "UNKNOWN"
    assert result.matched_skill is None
    assert result.multiplier == 0.0


def test_missing_taxonomy_snapshot_does_not_break_exact_or_alias_resolution(tmp_path: Path) -> None:
    resolver = _resolver(taxonomy_path=tmp_path / "missing-taxonomy.json")

    exact = resolver.resolve_skill("python", ["Python"])
    alias = resolver.resolve_skill("js", ["JavaScript"])

    assert exact.level == "EXACT_VERIFIED"
    assert alias.level == "APPROVED_ALIAS"


def test_local_taxonomy_snapshot_can_supply_reviewed_related_relation() -> None:
    resolver = _resolver(taxonomy_path=Path("tests/fixtures/taxonomy_snapshot.json"))

    result = resolver.resolve_skill("geospatial database", ["PostGIS"])

    assert result.level == "TAXONOMY_RELATED"
    assert result.matched_skill == "PostGIS"
    assert result.multiplier == 0.70
    assert result.taxonomy_source == "fixture-v1"
