from datetime import datetime, timezone

from app.models.domain import Opportunity
from app.radar.extractor import RuleBasedRequirementExtractor

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _opportunity(description: str) -> Opportunity:
    return Opportunity(
        id="opp-email-1",
        source="manual",
        source_id="fixture-email-1",
        source_url="https://example.test/jobs/1",
        company="Example Labs",
        title="GIS Developer",
        description=description,
        discovered_at=NOW,
        published_at=NOW,
    )


def test_published_email_is_extracted_with_provenance() -> None:
    enrichment = RuleBasedRequirementExtractor().extract(
        _opportunity("Apply by sending your CV to Careers@Example.Test.")
    )

    assert enrichment.application_mode == "DIRECT_EMAIL"
    assert len(enrichment.application_contact_hints) == 1
    hint = enrichment.application_contact_hints[0]
    assert hint.kind == "PUBLISHED_EMAIL"
    assert hint.value == "careers@example.test"
    assert hint.source_field == "description"
    assert hint.source_text == "Apply by sending your CV to Careers@Example.Test."
    assert hint.extraction_method == "explicit_rule"
    assert hint.confidence == 1.0


def test_no_email_never_generates_conventional_address() -> None:
    enrichment = RuleBasedRequirementExtractor().extract(
        _opportunity("Apply through our careers page. Example Labs is hiring.")
    )

    assert enrichment.application_contact_hints == []
    assert enrichment.application_mode != "DIRECT_EMAIL"


def test_duplicate_same_email_is_deduplicated_case_insensitively() -> None:
    enrichment = RuleBasedRequirementExtractor().extract(
        _opportunity(
            "Send CV to careers@example.test. Questions: Careers@Example.Test."
        )
    )

    assert [hint.value for hint in enrichment.application_contact_hints] == [
        "careers@example.test"
    ]
