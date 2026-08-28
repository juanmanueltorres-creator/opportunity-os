from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path

import pytest
import yaml

from app.models.domain import Opportunity

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=timezone.utc)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "radar_requirement_cases.yaml"


def _extractor_module():
    return import_module("app.radar.extractor")


def _opportunity(
    *,
    title: str = "Example Role",
    description: str = "Example description",
    source: str = "example",
    required_skills: list[str] | None = None,
    preferred_skills: list[str] | None = None,
    location: str | None = None,
    remote_policy: str | None = None,
    published_at: datetime | None = None,
) -> Opportunity:
    return Opportunity(
        id=f"{source}:1",
        source=source,
        source_id="1",
        source_url=f"https://example.com/{source}/1",
        company="Example Co",
        title=title,
        description=description,
        discovered_at=NOW,
        required_skills=required_skills or [],
        preferred_skills=preferred_skills or [],
        location=location,
        remote_policy=remote_policy,
        published_at=published_at,
    )


def _fixture_cases() -> list[dict]:
    return yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _fixture_cases(), ids=lambda case: case["id"])
def test_bilingual_requirement_extraction_preserves_supporting_span(case) -> None:
    extractor = _extractor_module().RuleBasedRequirementExtractor()
    enrichment = extractor.extract(
        _opportunity(title=case["title"], description=case["description"])
    )

    actual = [
        {
            "kind": item.kind,
            "value": item.value,
            "importance": item.importance,
            "source_text": item.provenance.source_text,
        }
        for item in enrichment.requirements
    ]

    for expected in case["expected"]:
        assert expected in actual


def test_structured_skills_have_stronger_structured_provenance() -> None:
    extractor = _extractor_module().RuleBasedRequirementExtractor()
    enrichment = extractor.extract(
        _opportunity(
            required_skills=["python", "sql"],
            preferred_skills=["docker"],
            description="General engineering work.",
        )
    )

    by_value = {item.value: item for item in enrichment.requirements}
    assert by_value["python"].importance == "mandatory"
    assert by_value["python"].provenance.source_field == "required_skills"
    assert by_value["python"].provenance.extraction_method == "source_structured"
    assert by_value["python"].provenance.confidence == 1.0
    assert by_value["python"].provenance.source_text is None
    assert by_value["docker"].importance == "preferred"
    assert by_value["docker"].provenance.source_field == "preferred_skills"


def test_ambiguous_skill_sentence_is_not_promoted_to_mandatory() -> None:
    extractor = _extractor_module().RuleBasedRequirementExtractor()
    enrichment = extractor.extract(
        _opportunity(description="Experience with Kubernetes would help the team.")
    )

    assert all(item.value.casefold() != "kubernetes" for item in enrichment.requirements)


def test_must_have_does_not_include_helper_verb_in_skill_name() -> None:
    enrichment = _extractor_module().RuleBasedRequirementExtractor().extract(
        _opportunity(description="Must have Python.")
    )

    assert any(
        item.value == "Python" and item.importance == "mandatory"
        for item in enrichment.requirements
    )
    assert all(item.value != "have Python" for item in enrichment.requirements)


def test_explicit_application_email_is_direct_email() -> None:
    enrichment = _extractor_module().RuleBasedRequirementExtractor().extract(
        _opportunity(description="Send your CV to jobs@example.com to apply.")
    )
    assert enrichment.application_mode == "DIRECT_EMAIL"


def test_known_hosted_ats_without_applicant_api_is_hosted_manual() -> None:
    enrichment = _extractor_module().RuleBasedRequirementExtractor().extract(
        _opportunity(source="greenhouse", description="Apply through this job page.")
    )
    assert enrichment.application_mode == "HOSTED_MANUAL"


def test_unknown_application_channel_remains_unknown() -> None:
    enrichment = _extractor_module().RuleBasedRequirementExtractor().extract(
        _opportunity(description="We are growing our team.")
    )
    assert enrichment.application_mode == "UNKNOWN"


def test_source_and_freshness_quality_are_explicit() -> None:
    extractor = _extractor_module().RuleBasedRequirementExtractor()

    direct = extractor.extract(
        _opportunity(source="greenhouse", published_at=NOW)
    )
    aggregate = extractor.extract(
        _opportunity(source="remotive", published_at=NOW)
    )
    discovered_only = extractor.extract(_opportunity(source="example"))

    assert direct.source_reliability == "DIRECT_ATS"
    assert direct.source_freshness_quality == "DIRECT_TIMESTAMP"
    assert aggregate.source_reliability == "AGGREGATOR"
    assert aggregate.source_freshness_quality == "DELAYED_TIMESTAMP"
    assert discovered_only.source_reliability == "UNKNOWN"
    assert discovered_only.source_freshness_quality == "DISCOVERED_AT_ONLY"


def test_parseable_salary_and_deadline_keep_provenance() -> None:
    enrichment = _extractor_module().RuleBasedRequirementExtractor().extract(
        _opportunity(
            title="  Data   Operator  ",
            description="Compensation: USD 2000 - 3000. Apply by 2026-09-15.",
        )
    )

    assert enrichment.normalized_title is not None
    assert enrichment.normalized_title.value == "Data Operator"
    assert enrichment.salary_min is not None
    assert enrichment.salary_min.value == 2000.0
    assert enrichment.salary_max is not None
    assert enrichment.salary_max.value == 3000.0
    assert enrichment.salary_currency is not None
    assert enrichment.salary_currency.value == "USD"
    assert enrichment.salary_min.source_text == "Compensation: USD 2000 - 3000."
    assert enrichment.application_deadline is not None
    assert enrichment.application_deadline.value == datetime(
        2026, 9, 15, tzinfo=timezone.utc
    )
    assert enrichment.application_deadline.source_text == "Apply by 2026-09-15."
