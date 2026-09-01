from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.metrics.sources import MetricFact

_EVIDENCE_RANK = {"NATIVE": 3, "IMPORTED_PROVIDER": 2, "MANUAL": 1}


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
    excluded = {
        fact.fact_id for fact in facts if fact.link_confidence < 1.0
    }
    lineage_groups: dict[tuple[str, str, str], list[MetricFact]] = defaultdict(list)
    for fact in facts:
        key = _lineage_key(fact)
        if key is not None:
            lineage_groups[key].append(fact)

    ambiguity_groups: list[tuple[str, ...]] = []
    for group in lineage_groups.values():
        if len(group) < 2 or _is_exactly_distinct(group):
            continue

        # Exact reconciliation is unavailable for at least one member. Keep every
        # observation visible, but permit only the strongest defensible lineage
        # claim to participate in linkage-dependent ratios.
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
