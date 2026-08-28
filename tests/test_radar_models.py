from datetime import datetime, timezone
from importlib import import_module

import pytest
from pydantic import ValidationError


def _models():
    return import_module("app.radar.models")


def test_free_text_derived_value_requires_supporting_source_text() -> None:
    models = _models()

    with pytest.raises(ValidationError):
        models.DerivedValue[str](
            value="Python",
            source_field="description",
            extraction_method="explicit_rule",
            confidence=0.9,
        )


def test_structured_derived_value_can_omit_source_text() -> None:
    models = _models()

    value = models.DerivedValue[str](
        value="Python",
        source_field="required_skills",
        extraction_method="source_structured",
        confidence=1.0,
    )

    assert value.source_text is None
    assert value.value == "Python"


def test_requirement_provenance_must_support_the_same_value() -> None:
    models = _models()
    provenance = models.DerivedValue[str](
        value="SQL",
        source_text="Required: SQL",
        source_field="description",
        extraction_method="explicit_rule",
        confidence=0.95,
    )

    with pytest.raises(ValidationError):
        models.Requirement(
            kind="skill",
            value="Python",
            importance="mandatory",
            exactness="conceptual",
            provenance=provenance,
        )


def test_radar_contracts_forbid_unknown_fields() -> None:
    models = _models()

    with pytest.raises(ValidationError):
        models.EligibilityResult(eligible=True, surprise="nope")


def test_opportunity_enrichment_rejects_naive_created_at() -> None:
    models = _models()

    with pytest.raises(ValidationError):
        models.OpportunityEnrichment(
            opportunity_id="job-1",
            extractor_version="rules-v1",
            taxonomy_versions={},
            created_at=datetime(2026, 8, 28, 15, 0, 0),
        )


def test_opportunity_enrichment_defaults_are_safe_and_explicit() -> None:
    models = _models()

    enrichment = models.OpportunityEnrichment(
        opportunity_id="job-1",
        extractor_version="rules-v1",
        taxonomy_versions={},
        created_at=datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc),
    )

    assert enrichment.requirements == []
    assert enrichment.application_mode == "UNKNOWN"
    assert enrichment.source_reliability == "UNKNOWN"
    assert enrichment.source_freshness_quality == "UNKNOWN"
    assert enrichment.channel_tags == []
