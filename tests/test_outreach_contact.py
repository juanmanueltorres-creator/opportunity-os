from datetime import datetime, timezone

from app.models.domain import Opportunity
from app.outreach.contact import ContactResolutionService
from app.outreach.models import ContactCandidate, ContactPolicy, SendReceipt
from app.outreach.repository import SQLiteOutreachRepository
from app.radar.extractor import RuleBasedRequirementExtractor

NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _opportunity(description: str = "Apply through our careers page.") -> Opportunity:
    return Opportunity(
        id="opp-1",
        source="manual",
        source_id="fixture-1",
        source_url="https://example.test/jobs/1",
        company="Example Labs",
        title="GIS Developer",
        description=description,
        discovered_at=NOW,
        published_at=NOW,
    )


def _candidate(
    candidate_id: str,
    *,
    channel: str,
    email: str | None,
    verification_status: str,
    confidence: float = 0.9,
    requires_paid_enrichment: bool = False,
) -> ContactCandidate:
    return ContactCandidate(
        candidate_id=candidate_id,
        opportunity_id="opp-1",
        channel=channel,
        email=email,
        contact_name="Taylor Recruiter" if channel == "VERIFIED_RECRUITER" else None,
        contact_role="Talent Acquisition" if channel == "VERIFIED_RECRUITER" else None,
        organization="Example Labs",
        source_kind=(
            "APOLLO"
            if channel == "VERIFIED_RECRUITER"
            else "OFFICIAL_SITE"
            if channel == "OFFICIAL_HR_EMAIL"
            else "MANUAL"
        ),
        source_ref="https://example.test/contact",
        confidence=confidence,
        verification_status=verification_status,
        requires_paid_enrichment=requires_paid_enrichment,
        discovered_at=NOW,
    )


def _repo(tmp_path) -> SQLiteOutreachRepository:
    repo = SQLiteOutreachRepository(tmp_path / "outreach.sqlite3")
    repo.initialize()
    return repo


def _resolve(tmp_path, opportunity, candidates):
    enrichment = RuleBasedRequirementExtractor().extract(opportunity)
    return ContactResolutionService(id_factory=lambda: "published-1").resolve(
        opportunity=opportunity,
        enrichment=enrichment,
        candidates=candidates,
        policy=ContactPolicy(),
        ledger=_repo(tmp_path),
        now=NOW,
    )


def test_published_email_beats_official_hr_and_recruiter(tmp_path) -> None:
    opportunity = _opportunity("Send your CV to apply@example.test.")
    result = _resolve(
        tmp_path,
        opportunity,
        [
            _candidate(
                "official",
                channel="OFFICIAL_HR_EMAIL",
                email="careers@example.test",
                verification_status="VERIFIED_OFFICIAL",
            ),
            _candidate(
                "recruiter",
                channel="VERIFIED_RECRUITER",
                email="recruiter@example.test",
                verification_status="VERIFIED_ENRICHED",
            ),
        ],
    )
    assert result.status == "RESOLVED"
    assert result.resolution is not None
    assert result.resolution.channel == "PUBLISHED_VACANCY_EMAIL"
    assert result.resolution.email == "apply@example.test"


def test_official_hr_beats_verified_recruiter(tmp_path) -> None:
    result = _resolve(
        tmp_path,
        _opportunity(),
        [
            _candidate(
                "official",
                channel="OFFICIAL_HR_EMAIL",
                email="careers@example.test",
                verification_status="VERIFIED_OFFICIAL",
                confidence=0.7,
            ),
            _candidate(
                "recruiter",
                channel="VERIFIED_RECRUITER",
                email="recruiter@example.test",
                verification_status="VERIFIED_ENRICHED",
                confidence=1.0,
            ),
        ],
    )
    assert result.status == "RESOLVED"
    assert result.resolution is not None
    assert result.resolution.channel == "OFFICIAL_HR_EMAIL"


def test_verified_recruiter_with_unknown_email_requires_enrichment(tmp_path) -> None:
    result = _resolve(
        tmp_path,
        _opportunity(),
        [
            _candidate(
                "recruiter",
                channel="VERIFIED_RECRUITER",
                email=None,
                verification_status="IDENTITY_VERIFIED_EMAIL_UNKNOWN",
                requires_paid_enrichment=True,
            )
        ],
    )
    assert result.status == "REQUIRES_ENRICHMENT"
    assert result.resolution is None


def test_unverified_email_candidate_is_never_actionable(tmp_path) -> None:
    result = _resolve(
        tmp_path,
        _opportunity(),
        [
            _candidate(
                "bad",
                channel="OFFICIAL_HR_EMAIL",
                email="maybe@example.test",
                verification_status="UNVERIFIED",
            )
        ],
    )
    assert result.status == "BLOCKED_NO_CONTACT"
    assert result.resolution is None


def test_manual_form_is_returned_only_after_email_channels_fail(tmp_path) -> None:
    result = _resolve(
        tmp_path,
        _opportunity(),
        [
            _candidate(
                "manual",
                channel="MANUAL_FORM",
                email=None,
                verification_status="MANUAL_ONLY",
            )
        ],
    )
    assert result.status == "MANUAL_ONLY"
    assert result.resolution is not None
    assert result.resolution.channel == "MANUAL_FORM"
    assert result.resolution.email is None


def test_no_contact_fails_closed_without_guessing(tmp_path) -> None:
    result = _resolve(tmp_path, _opportunity(), [])
    dumped = result.model_dump_json().casefold()
    assert result.status == "BLOCKED_NO_CONTACT"
    assert "jobs@example.test" not in dumped
    assert "careers@example.test" not in dumped


def test_existing_successful_send_blocks_new_initial_resolution(tmp_path) -> None:
    repo = _repo(tmp_path)
    repo.save_send_receipt(
        SendReceipt(
            receipt_id="receipt-1",
            opportunity_id="opp-1",
            approval_id="approval-1",
            send_request_id="request-1",
            draft_sha256="d" * 64,
            application_packet_sha256="p" * 64,
            idempotency_key="k" * 64,
            provider_message_id="message-1",
            recipient="careers@example.test",
            sent_at=NOW,
        )
    )
    opportunity = _opportunity("Send CV to apply@example.test.")
    enrichment = RuleBasedRequirementExtractor().extract(opportunity)
    result = ContactResolutionService().resolve(
        opportunity=opportunity,
        enrichment=enrichment,
        candidates=[],
        policy=ContactPolicy(),
        ledger=repo,
        now=NOW,
    )
    assert result.status == "BLOCKED_POLICY"
    assert "already_sent" in result.errors


def test_recruiter_daily_company_cap_blocks_third_recruiter_contact(tmp_path) -> None:
    repo = _repo(tmp_path)
    for index in range(2):
        repo.save_contact_resolution(
            ContactResolutionService()._resolution_from_candidate(
                _candidate(
                    f"prior-{index}",
                    channel="VERIFIED_RECRUITER",
                    email=f"prior{index}@example.test",
                    verification_status="VERIFIED_ENRICHED",
                ),
                policy=ContactPolicy(),
                now=NOW,
            )
        )
    opportunity = _opportunity()
    enrichment = RuleBasedRequirementExtractor().extract(opportunity)
    result = ContactResolutionService().resolve(
        opportunity=opportunity,
        enrichment=enrichment,
        candidates=[
            _candidate(
                "third",
                channel="VERIFIED_RECRUITER",
                email="third@example.test",
                verification_status="VERIFIED_ENRICHED",
            )
        ],
        policy=ContactPolicy(),
        ledger=repo,
        now=NOW,
    )
    assert result.status == "BLOCKED_POLICY"
    assert "recruiter_daily_cap" in result.errors
