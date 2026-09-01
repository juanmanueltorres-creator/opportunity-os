from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from app.metrics.history import HistoricalImportBatch
from app.metrics.models import (
    CountMetric,
    Coverage,
    CoverageSummary,
    RatioMetric,
    ReportWindow,
    SearchHealthCounts,
    SearchHealthRatios,
    SearchHealthReport,
    SourceSummary,
)
from app.metrics.sources import (
    MetricFact,
    OpportunityFact,
    QualificationFact,
    SourceRead,
)

_EVIDENCE_RANK = {"NATIVE": 3, "IMPORTED_PROVIDER": 2, "MANUAL": 1}
_TIER_RANK = {"HIGH": 4, "MEDIUM": 3, "STRETCH": 2, "DISCARD": 1}


@dataclass(frozen=True)
class ReconciliationResult:
    facts: tuple[MetricFact, ...]
    linkage_excluded_fact_ids: frozenset[str] = frozenset()
    ambiguity_groups: tuple[tuple[str, ...], ...] = ()

    @property
    def has_ambiguity(self) -> bool:
        return bool(self.ambiguity_groups)

    @property
    def linkage_eligible_facts(self) -> tuple[MetricFact, ...]:
        return tuple(
            fact
            for fact in self.facts
            if fact.fact_id not in self.linkage_excluded_fact_ids
            and fact.link_confidence == 1.0
        )


@dataclass(frozen=True)
class MetricsInput:
    opportunities: SourceRead[OpportunityFact]
    qualifications: SourceRead[QualificationFact]
    packets: SourceRead[MetricFact]
    outreach: SourceRead[MetricFact]
    relationships: SourceRead[MetricFact]
    history: SourceRead[MetricFact]
    history_batches: tuple[HistoricalImportBatch, ...] = ()


def _fact_order(fact: MetricFact) -> tuple[object, ...]:
    return (fact.occurred_at, fact.kind, fact.fact_id)


def _preferred_exact_fact(facts: list[MetricFact]) -> MetricFact:
    strongest_rank = max(_EVIDENCE_RANK[fact.evidence_class] for fact in facts)
    strongest = [
        fact
        for fact in facts
        if _EVIDENCE_RANK[fact.evidence_class] == strongest_rank
    ]
    return min(strongest, key=lambda fact: (fact.occurred_at, fact.fact_id))


def _collapse_exact_facts(facts: tuple[MetricFact, ...]) -> tuple[MetricFact, ...]:
    exact_groups: dict[tuple[str, str], list[MetricFact]] = defaultdict(list)
    without_exact_anchor: list[MetricFact] = []

    for fact in facts:
        if fact.exact_anchor is None:
            without_exact_anchor.append(fact)
            continue
        exact_groups[(fact.kind, fact.exact_anchor)].append(fact)

    selected = list(without_exact_anchor)
    for group in exact_groups.values():
        selected.append(_preferred_exact_fact(group))
    return tuple(sorted(selected, key=_fact_order))


def _lineage_key(fact: MetricFact) -> tuple[str, str, str] | None:
    if fact.opportunity_id is not None:
        return (fact.kind, "opportunity", fact.opportunity_id)
    if fact.account_id is not None:
        return (fact.kind, "account", fact.account_id)
    return None


def _is_exactly_distinct(group: list[MetricFact]) -> bool:
    anchors = [fact.exact_anchor for fact in group]
    return all(anchor is not None for anchor in anchors) and len(set(anchors)) == len(anchors)


def _strongest_for_linkage(group: list[MetricFact]) -> MetricFact:
    return min(
        group,
        key=lambda fact: (
            -_EVIDENCE_RANK[fact.evidence_class],
            -fact.link_confidence,
            fact.occurred_at,
            fact.fact_id,
        ),
    )


def _ambiguity_exclusions(
    facts: tuple[MetricFact, ...],
) -> tuple[frozenset[str], tuple[tuple[str, ...], ...]]:
    excluded = {fact.fact_id for fact in facts if fact.link_confidence < 1.0}
    lineage_groups: dict[tuple[str, str, str], list[MetricFact]] = defaultdict(list)
    for fact in facts:
        key = _lineage_key(fact)
        if key is not None:
            lineage_groups[key].append(fact)

    ambiguity_groups: list[tuple[str, ...]] = []
    for group in lineage_groups.values():
        if len(group) < 2 or _is_exactly_distinct(group):
            continue

        strongest = _strongest_for_linkage(group)
        ordered_ids = tuple(sorted(fact.fact_id for fact in group))
        ambiguity_groups.append(ordered_ids)
        for fact in group:
            if fact.fact_id != strongest.fact_id:
                excluded.add(fact.fact_id)

    ambiguity_groups.sort()
    return frozenset(excluded), tuple(ambiguity_groups)


def reconcile_facts(
    native: tuple[MetricFact, ...],
    historical: tuple[MetricFact, ...],
) -> ReconciliationResult:
    """Reconcile only facts that share an explicit exact anchor and kind.

    Provider/message identifiers are valid exact anchors. Similar company text,
    timestamps, or shared opportunity/account lineage are never used to collapse
    facts. Shared lineage without exact anchors is preserved as ambiguity instead.
    """

    collapsed = _collapse_exact_facts(tuple(native) + tuple(historical))
    excluded, ambiguity_groups = _ambiguity_exclusions(collapsed)
    return ReconciliationResult(
        facts=collapsed,
        linkage_excluded_fact_ids=excluded,
        ambiguity_groups=ambiguity_groups,
    )


def _metric_count(
    name: str,
    value: int,
    coverage: Coverage,
    *,
    basis: tuple[str, ...],
    warnings: tuple[str, ...] = (),
) -> CountMetric:
    return CountMetric(
        name=name,
        value=None if coverage == "UNKNOWN" else value,
        coverage=coverage,
        basis=list(basis),
        warnings=list(warnings),
    )


def _metric_ratio(
    name: str,
    numerator: int,
    denominator: int,
    coverage: Coverage,
    *,
    basis: tuple[str, ...],
    can_compute: bool,
    warnings: tuple[str, ...] = (),
) -> RatioMetric:
    value = None
    if can_compute and denominator > 0:
        value = numerator / denominator
    return RatioMetric(
        name=name,
        value=value,
        numerator=numerator,
        denominator=denominator,
        coverage=coverage,
        basis=list(basis),
        warnings=list(warnings),
    )


def _dedupe_opportunities(facts: tuple[OpportunityFact, ...]) -> tuple[OpportunityFact, ...]:
    by_id: dict[str, OpportunityFact] = {}
    for fact in sorted(facts, key=lambda item: (item.discovered_at, item.opportunity_id)):
        by_id.setdefault(fact.opportunity_id, fact)
    return tuple(by_id.values())


def _strongest_qualifications(
    facts: tuple[QualificationFact, ...],
) -> tuple[dict[str, QualificationFact], tuple[str, ...]]:
    strongest: dict[str, QualificationFact] = {}
    versions: set[str] = set()
    for fact in facts:
        versions.add(fact.scoring_version)
        current = strongest.get(fact.opportunity_id)
        if current is None:
            strongest[fact.opportunity_id] = fact
            continue
        if _TIER_RANK[fact.tier] > _TIER_RANK[current.tier]:
            strongest[fact.opportunity_id] = fact
            continue
        if (
            _TIER_RANK[fact.tier] == _TIER_RANK[current.tier]
            and (fact.observed_at, fact.scoring_version)
            < (current.observed_at, current.scoring_version)
        ):
            strongest[fact.opportunity_id] = fact

    warnings: list[str] = []
    if len(versions) > 1:
        warnings.append("multiple scoring versions present in recorded qualification history")
    return strongest, tuple(warnings)


def _has_complete_history_scope(
    batches: tuple[HistoricalImportBatch, ...],
    window: ReportWindow,
) -> bool:
    return any(
        batch.selection_scope == "ALL_DECLARED_OUTREACH_THREADS"
        and batch.complete_for_declared_scope
        and batch.window_start <= window.start
        and batch.window_end >= window.end
        for batch in batches
    )


def _execution_coverage(
    primary: SourceRead[MetricFact],
    history: SourceRead[MetricFact],
    *,
    historical_kind: str,
) -> Coverage:
    has_historical_kind = any(fact.kind == historical_kind for fact in history.items)
    if not has_historical_kind:
        return primary.coverage
    if primary.coverage == "UNKNOWN" and history.coverage == "UNKNOWN":
        return "UNKNOWN"
    if primary.coverage == "COMPLETE" and history.coverage == "COMPLETE":
        return "COMPLETE"
    return "PARTIAL"


def _outcome_coverage(
    relationships: SourceRead[MetricFact],
    history: SourceRead[MetricFact],
    *,
    facts: tuple[MetricFact, ...],
    complete_history_scope: bool,
) -> Coverage:
    if (
        complete_history_scope
        and history.coverage == "COMPLETE"
        and relationships.coverage == "COMPLETE"
    ):
        return "COMPLETE"
    if facts or history.coverage != "UNKNOWN" or relationships.coverage != "UNKNOWN":
        return "PARTIAL"
    return "UNKNOWN"


def _same_exact_lineage(left: MetricFact, right: MetricFact) -> bool:
    if left.thread_anchor is not None and left.thread_anchor == right.thread_anchor:
        return True
    if (
        left.opportunity_id is not None
        and left.opportunity_id == right.opportunity_id
    ):
        return True
    if left.account_id is not None and left.account_id == right.account_id:
        return True
    return False


def _sanitized_source_summary(name: str, source: SourceRead[object]) -> SourceSummary:
    warnings = []
    if source.warnings:
        warnings.append(f"source reported {len(source.warnings)} warning(s)")
    return SourceSummary(name=name, coverage=source.coverage, warnings=warnings)


def project_search_health(
    inputs: MetricsInput,
    window: ReportWindow,
    *,
    generated_at: datetime,
) -> SearchHealthReport:
    opportunities = _dedupe_opportunities(inputs.opportunities.items)
    opportunity_ids = {fact.opportunity_id for fact in opportunities}

    strongest_qualifications, qualification_warnings = _strongest_qualifications(
        inputs.qualifications.items
    )
    high_ids = {
        opportunity_id
        for opportunity_id, fact in strongest_qualifications.items()
        if fact.tier == "HIGH"
    }
    medium_ids = {
        opportunity_id
        for opportunity_id, fact in strongest_qualifications.items()
        if fact.tier == "MEDIUM"
    }

    native_facts = tuple(inputs.outreach.items) + tuple(inputs.relationships.items)
    reconciled = reconcile_facts(native_facts, tuple(inputs.history.items))
    facts_by_kind: dict[str, tuple[MetricFact, ...]] = {
        kind: tuple(fact for fact in reconciled.facts if fact.kind == kind)
        for kind in (
            "DRAFT",
            "SEND",
            "REPLY",
            "PROCESS_OPENED",
            "PROCESS_CLOSED",
        )
    }
    eligible_by_kind: dict[str, tuple[MetricFact, ...]] = {
        kind: tuple(
            fact for fact in reconciled.linkage_eligible_facts if fact.kind == kind
        )
        for kind in (
            "DRAFT",
            "SEND",
            "REPLY",
            "PROCESS_OPENED",
            "PROCESS_CLOSED",
        )
    }

    packet_facts = tuple(
        fact for fact in inputs.packets.items if fact.kind == "PACKET_PREPARED"
    )
    complete_history_scope = _has_complete_history_scope(inputs.history_batches, window)

    draft_coverage = _execution_coverage(
        inputs.outreach, inputs.history, historical_kind="DRAFT"
    )
    send_coverage = _execution_coverage(
        inputs.outreach, inputs.history, historical_kind="SEND"
    )
    reply_coverage = _outcome_coverage(
        inputs.relationships,
        inputs.history,
        facts=facts_by_kind["REPLY"],
        complete_history_scope=complete_history_scope,
    )
    process_coverage = _outcome_coverage(
        inputs.relationships,
        inputs.history,
        facts=facts_by_kind["PROCESS_OPENED"] + facts_by_kind["PROCESS_CLOSED"],
        complete_history_scope=complete_history_scope,
    )

    counts = SearchHealthCounts(
        opportunities_observed=_metric_count(
            "opportunities_observed",
            len(opportunities),
            inputs.opportunities.coverage,
            basis=inputs.opportunities.basis,
        ),
        opportunities_new=_metric_count(
            "opportunities_new",
            len(opportunities),
            inputs.opportunities.coverage,
            basis=inputs.opportunities.basis
            + ("canonical first observation equals new in search-health-v1",),
        ),
        qualified_high=_metric_count(
            "qualified_high",
            len(high_ids),
            inputs.qualifications.coverage,
            basis=inputs.qualifications.basis,
            warnings=qualification_warnings,
        ),
        qualified_medium=_metric_count(
            "qualified_medium",
            len(medium_ids),
            inputs.qualifications.coverage,
            basis=inputs.qualifications.basis,
            warnings=qualification_warnings,
        ),
        packets_prepared=_metric_count(
            "packets_prepared",
            len(packet_facts),
            inputs.packets.coverage,
            basis=inputs.packets.basis,
        ),
        drafts_verified=_metric_count(
            "drafts_verified",
            len(facts_by_kind["DRAFT"]),
            draft_coverage,
            basis=inputs.outreach.basis + inputs.history.basis,
        ),
        confirmed_sends=_metric_count(
            "confirmed_sends",
            len(facts_by_kind["SEND"]),
            send_coverage,
            basis=inputs.outreach.basis + inputs.history.basis,
        ),
        replies_observed=_metric_count(
            "replies_observed",
            len(facts_by_kind["REPLY"]),
            reply_coverage,
            basis=inputs.relationships.basis + inputs.history.basis,
        ),
        processes_opened=_metric_count(
            "processes_opened",
            len(facts_by_kind["PROCESS_OPENED"]),
            process_coverage,
            basis=inputs.relationships.basis + inputs.history.basis,
        ),
        processes_closed=_metric_count(
            "processes_closed",
            len(facts_by_kind["PROCESS_CLOSED"]),
            process_coverage,
            basis=inputs.relationships.basis + inputs.history.basis,
        ),
    )

    qualification_complete = (
        inputs.opportunities.coverage == "COMPLETE"
        and inputs.qualifications.coverage == "COMPLETE"
    )
    qualification_numerator = len((high_ids | medium_ids) & opportunity_ids)
    qualification_denominator = len(opportunity_ids)
    qualification_coverage: Coverage
    if (
        inputs.opportunities.coverage == "UNKNOWN"
        or inputs.qualifications.coverage == "UNKNOWN"
    ):
        qualification_coverage = "UNKNOWN"
    elif qualification_complete:
        qualification_coverage = "COMPLETE"
    else:
        qualification_coverage = "PARTIAL"

    native_drafts = tuple(
        fact
        for fact in eligible_by_kind["DRAFT"]
        if fact.evidence_class == "NATIVE" and fact.draft_sha256 is not None
    )
    linked_send_shas = {
        fact.draft_sha256
        for fact in eligible_by_kind["SEND"]
        if fact.draft_sha256 is not None
    }
    sent_native_draft_ids = {
        draft.fact_id
        for draft in native_drafts
        if draft.draft_sha256 in linked_send_shas
    }
    draft_ratio_complete = inputs.outreach.coverage == "COMPLETE"
    draft_ratio_coverage: Coverage = (
        "COMPLETE"
        if draft_ratio_complete
        else "UNKNOWN"
        if inputs.outreach.coverage == "UNKNOWN"
        else "PARTIAL"
    )

    eligible_sends = eligible_by_kind["SEND"]
    eligible_replies = eligible_by_kind["REPLY"]
    sends_with_reply = {
        send.fact_id
        for send in eligible_sends
        if any(
            reply.occurred_at >= send.occurred_at
            and _same_exact_lineage(send, reply)
            for reply in eligible_replies
        )
    }
    send_reply_complete = (
        complete_history_scope
        and inputs.history.coverage == "COMPLETE"
        and inputs.outreach.coverage != "UNKNOWN"
    )
    send_reply_coverage: Coverage = (
        "COMPLETE"
        if send_reply_complete
        else "PARTIAL"
        if (
            inputs.history.coverage != "UNKNOWN"
            or inputs.outreach.coverage != "UNKNOWN"
            or eligible_sends
            or eligible_replies
        )
        else "UNKNOWN"
    )

    eligible_processes = eligible_by_kind["PROCESS_OPENED"]
    replies_with_process = {
        reply.fact_id
        for reply in eligible_replies
        if any(
            process.occurred_at >= reply.occurred_at
            and _same_exact_lineage(reply, process)
            for process in eligible_processes
        )
    }
    reply_process_complete = (
        complete_history_scope
        and inputs.history.coverage == "COMPLETE"
        and inputs.relationships.coverage == "COMPLETE"
    )
    reply_process_coverage: Coverage = (
        "COMPLETE"
        if reply_process_complete
        else "PARTIAL"
        if (
            inputs.history.coverage != "UNKNOWN"
            or inputs.relationships.coverage != "UNKNOWN"
            or eligible_replies
            or eligible_processes
        )
        else "UNKNOWN"
    )

    ratios = SearchHealthRatios(
        qualification_rate=_metric_ratio(
            "qualification_rate",
            qualification_numerator,
            qualification_denominator,
            qualification_coverage,
            basis=inputs.opportunities.basis + inputs.qualifications.basis,
            can_compute=qualification_complete,
            warnings=qualification_warnings,
        ),
        draft_to_send_rate=_metric_ratio(
            "draft_to_send_rate",
            len(sent_native_draft_ids),
            len(native_drafts),
            draft_ratio_coverage,
            basis=inputs.outreach.basis,
            can_compute=draft_ratio_complete,
        ),
        send_to_reply_rate=_metric_ratio(
            "send_to_reply_rate",
            len(sends_with_reply),
            len(eligible_sends),
            send_reply_coverage,
            basis=inputs.outreach.basis + inputs.history.basis,
            can_compute=send_reply_complete,
        ),
        reply_to_process_rate=_metric_ratio(
            "reply_to_process_rate",
            len(replies_with_process),
            len(eligible_replies),
            reply_process_coverage,
            basis=inputs.relationships.basis + inputs.history.basis,
            can_compute=reply_process_complete,
        ),
    )

    warnings = list(qualification_warnings)
    if reconciled.has_ambiguity:
        warnings.append(
            "some same-lineage observations lacked exact reconciliation anchors and were excluded from linkage ratios"
        )
    if reconciled.linkage_excluded_fact_ids and not reconciled.has_ambiguity:
        warnings.append(
            "some observations were retained as counts but excluded from linkage ratios"
        )

    source_summary = [
        _sanitized_source_summary("opportunities", inputs.opportunities),
        _sanitized_source_summary("qualifications", inputs.qualifications),
        _sanitized_source_summary("applications", inputs.packets),
        _sanitized_source_summary("outreach", inputs.outreach),
        _sanitized_source_summary("relationships", inputs.relationships),
        _sanitized_source_summary("history", inputs.history),
    ]

    return SearchHealthReport(
        generated_at=generated_at,
        window=window,
        counts=counts,
        ratios=ratios,
        coverage=CoverageSummary(
            radar=inputs.qualifications.coverage,
            outreach=send_coverage,
            replies=reply_coverage,
            processes=process_coverage,
        ),
        warnings=warnings,
        source_summary=source_summary,
    )