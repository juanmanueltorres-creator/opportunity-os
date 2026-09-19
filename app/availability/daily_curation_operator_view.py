from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from pydantic import Field, field_validator

from app.availability.daily_curation import (
    DailyCurationPolicy,
    DailyCurationRun,
    DailyCurationService,
)
from app.availability.verification_queue import VerificationReason
from app.availability.verification_review_session import VerificationReviewCard
from app.radar.community_digest_renderer import CommunityDigestRenderOptions
from app.radar.models import StrictRadarModel


OperatorViewFormat = Literal["markdown", "plain"]
OPERATOR_VIEW_VERSION = "daily-curation-operator-view-v1"

_REASON_LABELS: dict[VerificationReason, str] = {
    "DISCOVERY_ONLY_NEEDS_OFFICIAL_SOURCE": "buscar fuente oficial",
    "DEADLINE_SOON_UNVERIFIED": "deadline cercano sin verificar",
    "FAST_MARKET_UNVERIFIED": "proyecto rápido sin verificar",
    "SOURCE_REQUIRES_VERIFICATION": "fuente requiere verificación",
    "VERIFICATION_STALE": "verificación vencida",
}

_ACTION_LABELS = {
    "FIND_OFFICIAL_SOURCE": "Buscar fuente oficial",
    "VERIFY_CURRENT_SOURCE": "Verificar fuente actual",
    "REVERIFY_CURRENT_SOURCE": "Reverificar fuente actual",
}

_CHECK_LABELS = {
    "LOCATE_OFFICIAL_SOURCE": "Localizar fuente oficial",
    "MATCH_ROLE_IDENTITY": "Confirmar empresa/proyecto y rol",
    "CONFIRM_LISTING_LOADS": "Confirmar que el listing carga",
    "CONFIRM_APPLICATION_ACTIONABLE": "Confirmar vía de aplicación/acción",
    "CONFIRM_DEADLINE": "Confirmar deadline",
    "CONFIRM_STILL_OPEN": "Confirmar que sigue abierta",
    "CAPTURE_EVIDENCE_URL": "Capturar URL de evidencia",
}


@dataclass(frozen=True)
class DailyCurationOperatorViewOptions:
    title: str = "Opportunity OS — Daily Curation"
    format: OperatorViewFormat = "markdown"
    include_checklists: bool = True
    include_held_details: bool = True

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be blank")
        if self.format not in {"markdown", "plain"}:
            raise ValueError("unsupported operator view format")


class OperatorReviewItem(StrictRadarModel):
    rank: int = Field(ge=1)
    opportunity_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    company: str = Field(min_length=1)
    priority_score: int = Field(ge=0, le=100)
    why: list[str] = Field(min_length=1)
    next_action: str = Field(min_length=1)
    review_url: str = Field(min_length=1)
    checklist: list[str] = Field(default_factory=list)
    next_endpoint: str = "/api/v1/availability/verification/draft"
    card_sha256: str = Field(min_length=64, max_length=64)
    card: VerificationReviewCard


class OperatorPublishableSummary(StrictRadarModel):
    count: int = Field(ge=0)
    opportunity_ids: list[str] = Field(default_factory=list)
    rendered_digest: str
    format: str
    digest_id: str = Field(min_length=1)


class OperatorHeldSummary(StrictRadarModel):
    total_count: int = Field(ge=0)
    shown_count: int = Field(ge=0)
    omitted_count: int = Field(ge=0)
    reason_counts: dict[str, int] = Field(default_factory=dict)
    displayed_ids: list[str] = Field(default_factory=list)


class DailyCurationOperatorView(StrictRadarModel):
    view_version: str = OPERATOR_VIEW_VERSION
    run_id: str = Field(min_length=1)
    generated_at: datetime
    title: str = Field(min_length=1)
    review_count: int = Field(ge=0)
    publishable_count: int = Field(ge=0)
    held_count: int = Field(ge=0)
    review_items: list[OperatorReviewItem] = Field(default_factory=list)
    publishable: OperatorPublishableSummary
    held: OperatorHeldSummary
    rendered_view: str
    format: OperatorViewFormat
    external_actions: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def generated_at_must_be_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("external_actions")
    @classmethod
    def require_no_external_actions(cls, value: list[str]) -> list[str]:
        if value:
            raise ValueError("external_actions must be empty")
        return value


class DailyCurationOperatorViewService:
    def __init__(
        self,
        *,
        daily_curation_service: DailyCurationService,
    ) -> None:
        self.daily_curation_service = daily_curation_service

    def build(
        self,
        *,
        now: datetime,
        policy: DailyCurationPolicy | None = None,
        digest_render_options: CommunityDigestRenderOptions | None = None,
        view_options: DailyCurationOperatorViewOptions | None = None,
    ) -> DailyCurationOperatorView:
        resolved_view = view_options or DailyCurationOperatorViewOptions()
        run = self.daily_curation_service.run(
            now=now,
            policy=policy,
            render_options=digest_render_options,
        )
        return render_daily_curation_operator_view(
            run,
            options=resolved_view,
        )


def render_daily_curation_operator_view(
    run: DailyCurationRun,
    *,
    options: DailyCurationOperatorViewOptions | None = None,
) -> DailyCurationOperatorView:
    resolved = options or DailyCurationOperatorViewOptions()
    review_items = [
        OperatorReviewItem(
            rank=card.rank,
            opportunity_id=card.opportunity_id,
            title=card.title,
            company=card.company,
            priority_score=card.priority_score,
            why=[
                _REASON_LABELS.get(reason, reason)
                for reason in card.reason_codes
            ],
            next_action=_ACTION_LABELS.get(
                card.suggested_action,
                card.suggested_action,
            ),
            review_url=card.review_url,
            checklist=(
                [
                    _CHECK_LABELS.get(check, check)
                    for check in card.checklist
                ]
                if resolved.include_checklists
                else []
            ),
            card_sha256=card.card_sha256,
            card=card,
        )
        for card in run.review.cards
    ]

    held = OperatorHeldSummary(
        total_count=run.held.total_count,
        shown_count=run.held.shown_count,
        omitted_count=run.held.omitted_count,
        reason_counts={
            _REASON_LABELS.get(reason, reason): count
            for reason, count in run.held.reason_counts.items()
        },
        displayed_ids=[item.opportunity_id for item in run.held.items],
    )
    publishable = OperatorPublishableSummary(
        count=run.publishable.digest.count,
        opportunity_ids=[
            item.opportunity_id
            for item in run.publishable.digest.items
        ],
        rendered_digest=run.publishable.rendered_text,
        format=run.publishable.format,
        digest_id=run.publishable.digest.digest_id,
    )
    rendered = _render(
        run=run,
        review_items=review_items,
        publishable=publishable,
        held=held,
        options=resolved,
    )
    return DailyCurationOperatorView(
        run_id=run.run_id,
        generated_at=run.generated_at,
        title=resolved.title.strip(),
        review_count=run.review.count,
        publishable_count=run.publishable.digest.count,
        held_count=run.held.total_count,
        review_items=review_items,
        publishable=publishable,
        held=held,
        rendered_view=rendered,
        format=resolved.format,
        external_actions=[],
    )


def _render(
    *,
    run: DailyCurationRun,
    review_items: list[OperatorReviewItem],
    publishable: OperatorPublishableSummary,
    held: OperatorHeldSummary,
    options: DailyCurationOperatorViewOptions,
) -> str:
    if options.format == "markdown":
        return _render_markdown(
            run=run,
            review_items=review_items,
            publishable=publishable,
            held=held,
            options=options,
        )
    return _render_plain(
        run=run,
        review_items=review_items,
        publishable=publishable,
        held=held,
        options=options,
    )


def _render_markdown(
    *,
    run: DailyCurationRun,
    review_items: list[OperatorReviewItem],
    publishable: OperatorPublishableSummary,
    held: OperatorHeldSummary,
    options: DailyCurationOperatorViewOptions,
) -> str:
    lines = [
        f"# {options.title.strip()}",
        "",
        f"Run: `{run.run_id}`",
        "",
        (
            f"**Review:** {run.review.count} · "
            f"**Publishable:** {run.publishable.digest.count} · "
            f"**Held:** {run.held.total_count}"
        ),
        "",
        "## 🔎 Review ahora",
    ]

    if review_items:
        for item in review_items:
            lines.extend(
                [
                    "",
                    (
                        f"### {item.rank}. {item.title} — "
                        f"{item.company}"
                    ),
                    f"**Prioridad:** {item.priority_score}/100",
                    f"**Por qué:** {', '.join(item.why)}",
                    f"**Siguiente paso:** {item.next_action}",
                    f"**Fuente:** {item.review_url}",
                ]
            )
            if item.checklist:
                lines.append("**Checklist:**")
                lines.extend(f"- [ ] {check}" for check in item.checklist)
            lines.append(
                f"**Draft endpoint:** `{item.next_endpoint}`"
            )
    else:
        lines.extend(["", "No hay items pendientes de revisión inmediata."])

    lines.extend(
        [
            "",
            "## ✅ Publishable",
            "",
            f"Items listos para publicar: **{publishable.count}**",
            "",
        ]
    )
    if publishable.rendered_digest.strip():
        lines.append(publishable.rendered_digest.strip())
    else:
        lines.append("No hay digest publicable en esta corrida.")

    lines.extend(
        [
            "",
            "## ⏸ Held",
            "",
            (
                f"Pendientes de verificación: **{held.total_count}** "
                f"(mostrados {held.shown_count}, omitidos {held.omitted_count})"
            ),
        ]
    )
    if options.include_held_details and held.reason_counts:
        lines.append("")
        lines.append("**Motivos:**")
        lines.extend(
            f"- {reason}: {count}"
            for reason, count in sorted(held.reason_counts.items())
        )
    lines.extend(
        [
            "",
            "---",
            "Vista read-only: no verifica, no publica y no envía.",
        ]
    )
    return "\n".join(lines).strip()


def _render_plain(
    *,
    run: DailyCurationRun,
    review_items: list[OperatorReviewItem],
    publishable: OperatorPublishableSummary,
    held: OperatorHeldSummary,
    options: DailyCurationOperatorViewOptions,
) -> str:
    lines = [
        options.title.strip(),
        f"Run: {run.run_id}",
        (
            f"Review {run.review.count} | "
            f"Publishable {run.publishable.digest.count} | "
            f"Held {run.held.total_count}"
        ),
        "",
        "REVIEW AHORA",
    ]
    if review_items:
        for item in review_items:
            lines.extend(
                [
                    "",
                    f"{item.rank}. {item.title} — {item.company}",
                    f"Prioridad: {item.priority_score}/100",
                    f"Por qué: {', '.join(item.why)}",
                    f"Siguiente paso: {item.next_action}",
                    f"Fuente: {item.review_url}",
                ]
            )
            if item.checklist:
                lines.extend(f"[ ] {check}" for check in item.checklist)
    else:
        lines.append("No hay items pendientes de revisión inmediata.")

    lines.extend(
        [
            "",
            "PUBLISHABLE",
            f"Items listos para publicar: {publishable.count}",
            publishable.rendered_digest.strip()
            or "No hay digest publicable en esta corrida.",
            "",
            "HELD",
            (
                f"Pendientes: {held.total_count} "
                f"(mostrados {held.shown_count}, omitidos {held.omitted_count})"
            ),
        ]
    )
    if options.include_held_details:
        lines.extend(
            f"- {reason}: {count}"
            for reason, count in sorted(held.reason_counts.items())
        )
    lines.extend(
        [
            "",
            "Vista read-only: no verifica, no publica y no envía.",
        ]
    )
    return "\n".join(lines).strip()
