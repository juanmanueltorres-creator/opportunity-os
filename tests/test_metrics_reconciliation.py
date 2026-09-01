from datetime import datetime, timedelta, timezone

from app.metrics.projection import reconcile_facts
from app.metrics.sources import MetricFact

UTC = timezone.utc
NOW = datetime(2026, 8, 20, tzinfo=UTC)


def _fact(
    fact_id: str,
    *,
    kind: str = "SEND",
    evidence_class: str = "NATIVE",
    exact_anchor: str | None = None,
    opportunity_id: str | None = "opp-1",
    account_id: str | None = None,
    occurred_at: datetime = NOW,
    link_confidence: float = 1.0,
    draft_sha256: str | None = None,
    thread_anchor: str | None = None,
) -> MetricFact:
    return MetricFact(
        fact_id=fact_id,
        kind=kind,
        opportunity_id=opportunity_id,
        account_id=account_id,
        occurred_at=occurred_at,
        evidence_class=evidence_class,
        exact_anchor=exact_anchor,
        link_confidence=link_confidence,
        draft_sha256=draft_sha256,
        thread_anchor=thread_anchor,
    )


def test_native_send_wins_over_exact_same_imported_provider_message():
    native = _fact(
        "native-send-1",
        exact_anchor="gmail-message:m-1",
        evidence_class="NATIVE",
        draft_sha256="a" * 64,
        thread_anchor="gmail-thread:t-1",
    )
    imported = _fact(
        "hist-send-1",
        exact_anchor="gmail-message:m-1",
        evidence_class="IMPORTED_PROVIDER",
        thread_anchor="gmail-thread:t-1",
    )

    result = reconcile_facts((native,), (imported,))

    assert result.facts == (native,)
    assert result.has_ambiguity is False
    assert result.linkage_excluded_fact_ids == frozenset()


def test_imported_provider_wins_over_manual_for_same_exact_fact():
    provider = _fact(
        "provider-send",
        evidence_class="IMPORTED_PROVIDER",
        exact_anchor="gmail-message:m-2",
    )
    manual = _fact(
        "manual-send",
        evidence_class="MANUAL",
        exact_anchor="gmail-message:m-2",
    )

    result = reconcile_facts((), (manual, provider))

    assert result.facts == (provider,)


def test_same_exact_anchor_but_different_kind_is_not_collapsed():
    send = _fact(
        "send-1",
        kind="SEND",
        exact_anchor="source:provider-object-1",
    )
    reply = _fact(
        "reply-1",
        kind="REPLY",
        exact_anchor="source:provider-object-1",
    )

    result = reconcile_facts((send, reply), ())

    assert {fact.fact_id for fact in result.facts} == {"send-1", "reply-1"}


def test_different_provider_message_ids_are_not_collapsed():
    first = _fact(
        "send-1",
        exact_anchor="gmail-message:m-1",
        evidence_class="NATIVE",
    )
    second = _fact(
        "send-2",
        exact_anchor="gmail-message:m-2",
        evidence_class="IMPORTED_PROVIDER",
    )

    result = reconcile_facts((first,), (second,))

    assert len(result.facts) == 2
    assert result.has_ambiguity is False


def test_same_opportunity_without_exact_anchor_is_not_collapsed_and_weaker_fact_is_excluded_from_linkage():
    native = _fact(
        "native-reply",
        kind="REPLY",
        exact_anchor=None,
        evidence_class="NATIVE",
    )
    imported = _fact(
        "hist-reply",
        kind="REPLY",
        exact_anchor=None,
        evidence_class="IMPORTED_PROVIDER",
    )

    result = reconcile_facts((native,), (imported,))

    assert len(result.facts) == 2
    assert result.has_ambiguity is True
    assert result.linkage_excluded_fact_ids == frozenset({"hist-reply"})
    assert [fact.fact_id for fact in result.linkage_eligible_facts] == ["native-reply"]


def test_same_account_without_exact_anchor_marks_lower_rank_fact_ambiguous():
    native = _fact(
        "native-process",
        kind="PROCESS_OPENED",
        opportunity_id=None,
        account_id="account-1",
        exact_anchor=None,
        evidence_class="NATIVE",
    )
    manual = _fact(
        "manual-process",
        kind="PROCESS_OPENED",
        opportunity_id=None,
        account_id="account-1",
        exact_anchor=None,
        evidence_class="MANUAL",
    )

    result = reconcile_facts((native,), (manual,))

    assert result.has_ambiguity is True
    assert result.linkage_excluded_fact_ids == frozenset({"manual-process"})


def test_low_link_confidence_remains_observable_but_is_never_linkage_eligible():
    imported = _fact(
        "uncertain-reply",
        kind="REPLY",
        evidence_class="IMPORTED_PROVIDER",
        exact_anchor="gmail-message:r-1",
        link_confidence=0.7,
    )

    result = reconcile_facts((), (imported,))

    assert result.facts == (imported,)
    assert result.has_ambiguity is False
    assert result.linkage_excluded_fact_ids == frozenset({"uncertain-reply"})
    assert result.linkage_eligible_facts == ()


def test_same_rank_exact_duplicate_uses_deterministic_time_then_id_tiebreak():
    earlier = _fact(
        "provider-a",
        evidence_class="IMPORTED_PROVIDER",
        exact_anchor="gmail-message:m-3",
        occurred_at=NOW,
    )
    later = _fact(
        "provider-b",
        evidence_class="IMPORTED_PROVIDER",
        exact_anchor="gmail-message:m-3",
        occurred_at=NOW + timedelta(seconds=1),
    )

    first_result = reconcile_facts((), (later, earlier))
    second_result = reconcile_facts((), (earlier, later))

    assert first_result.facts == second_result.facts == (earlier,)
