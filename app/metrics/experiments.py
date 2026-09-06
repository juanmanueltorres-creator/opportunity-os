from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from app.metrics.history import ExperimentCase
from app.metrics.models import ExperimentCohort, ExperimentSummary, OutreachType
from app.metrics.projection import reconcile_facts
from app.metrics.sources import MetricFact, SourceRead


@dataclass(frozen=True)
class ExperimentInputs:
    experiments: SourceRead[ExperimentCase]
    outreach: SourceRead[MetricFact]
    relationships: SourceRead[MetricFact]
    history: SourceRead[MetricFact]


def _same_lineage(experiment: ExperimentCase, fact: MetricFact) -> bool:
    if (
        experiment.opportunity_id is not None
        and fact.opportunity_id is not None
        and experiment.opportunity_id == fact.opportunity_id
    ):
        return True
    if (
        experiment.account_id is not None
        and fact.account_id is not None
        and experiment.account_id == fact.account_id
    ):
        return True
    return False


def _has_later_fact(
    experiment: ExperimentCase,
    facts: tuple[MetricFact, ...],
) -> bool:
    return any(
        fact.occurred_at >= experiment.observed_at
        and _same_lineage(experiment, fact)
        for fact in facts
    )


def project_experiment_cohorts(inputs: ExperimentInputs) -> ExperimentSummary:
    """Aggregate explicitly registered search experiments by outreach strategy.

    Cases are linked to replies/processes only through exact opportunity/account
    lineage already present in Opportunity OS. Fuzzy company/title matching is
    deliberately excluded. Facts that reconciliation marks ambiguous or weakly
    linked cannot increase cohort conversion counts.
    """

    native_facts = tuple(inputs.outreach.items) + tuple(inputs.relationships.items)
    reconciled = reconcile_facts(native_facts, tuple(inputs.history.items))
    eligible_replies = tuple(
        fact for fact in reconciled.linkage_eligible_facts if fact.kind == "REPLY"
    )
    eligible_processes = tuple(
        fact
        for fact in reconciled.linkage_eligible_facts
        if fact.kind == "PROCESS_OPENED"
    )

    grouped: dict[OutreachType, list[ExperimentCase]] = defaultdict(list)
    for experiment in inputs.experiments.items:
        grouped[experiment.outreach_type].append(experiment)

    cohorts: list[ExperimentCohort] = []
    for outreach_type in sorted(grouped):
        cases = grouped[outreach_type]
        outcomes: Counter[str] = Counter()
        evidence_usage: Counter[str] = Counter()
        reply_count = 0
        process_count = 0

        for experiment in cases:
            if _has_later_fact(experiment, eligible_replies):
                reply_count += 1
            if _has_later_fact(experiment, eligible_processes):
                process_count += 1
            if experiment.outcome is not None:
                outcomes[experiment.outcome] += 1
            evidence_usage.update(set(experiment.evidence_used))

        cohorts.append(
            ExperimentCohort(
                outreach_type=outreach_type,
                cases=len(cases),
                replies=reply_count,
                processes=process_count,
                outcomes=dict(sorted(outcomes.items())),
                evidence_usage=dict(sorted(evidence_usage.items())),
            )
        )

    warnings = list(inputs.experiments.warnings)
    if reconciled.has_ambiguity:
        warnings.append(
            "ambiguous same-lineage observations were excluded from experiment conversion counts"
        )
    elif reconciled.linkage_excluded_fact_ids:
        warnings.append(
            "weakly linked observations were excluded from experiment conversion counts"
        )

    return ExperimentSummary(
        coverage=inputs.experiments.coverage,
        cohorts=cohorts,
        warnings=warnings,
    )
