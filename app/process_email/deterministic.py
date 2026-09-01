from __future__ import annotations

import re
from collections.abc import Iterable

from app.process_email.models import (
    CLASSIFIER_VERSION,
    RULESET_VERSION,
    EvidenceSpan,
    ProcessClassification,
    ProcessConfidence,
    ProcessSignal,
    ProcessSignalKind,
)

_HYPOTHETICAL = (
    re.compile(r"\bif selected\b", re.I),
    re.compile(r"\bmay be invited\b", re.I),
    re.compile(r"\bsi (?:sos|eres|resultas) seleccionad[oa]\b", re.I),
    re.compile(r"\bpodr[ií]as? ser invitad[oa]\b", re.I),
)
_NEGATED_INTERVIEW = (
    re.compile(r"\bnot yet scheduling interviews\b", re.I),
    re.compile(r"\ba[uú]n no (?:estamos )?coordinando entrevistas\b", re.I),
)
_GENERIC_DESCRIPTION = (
    re.compile(r"\bour interview process normally\b", re.I),
    re.compile(r"\bnuestro proceso de entrevistas normalmente\b", re.I),
)

_APPLICATION_ACK = (
    re.compile(r"\bwe (?:have )?received your application\b", re.I),
    re.compile(r"\bthank you for applying\b", re.I),
    re.compile(r"\bhemos recibido tu (?:candidatura|postulaci[oó]n)\b", re.I),
    re.compile(r"\brecibimos tu (?:candidatura|postulaci[oó]n)\b", re.I),
)
_INTERVIEW_EXPLICIT = (
    re.compile(
        r"\b(?:we )?(?:would like|want) to invite you to (?:an? )?interview\b",
        re.I,
    ),
    re.compile(r"\bwe['’]d like to invite you to (?:an? )?interview\b", re.I),
    re.compile(r"\binvite you to (?:an? )?interview\b", re.I),
    re.compile(r"\bqueremos invitarte a una entrevista\b", re.I),
    re.compile(r"\bte invitamos a una entrevista\b", re.I),
)
_INTERVIEW_CONTEXT = (
    re.compile(
        r"\bwould .{0,80}? work for (?:a )?conversation with (?:the )?hiring manager\b",
        re.I,
    ),
    re.compile(
        r"\b(?:podemos|podr[ií]amos) coordinar .{0,60}?(?:conversaci[oó]n|charla) con (?:el|la) (?:hiring manager|responsable de contrataci[oó]n)\b",
        re.I,
    ),
)
_STAGE_ADVANCED = (
    re.compile(
        r"\byou (?:have |['’]ve )?advanced to the next stage(?: of our hiring process)?\b",
        re.I,
    ),
    re.compile(r"\byou are moving to the next stage\b", re.I),
    re.compile(r"\bavanzaste a la siguiente etapa(?: del proceso)?\b", re.I),
    re.compile(r"\bpasaste a la siguiente etapa(?: del proceso)?\b", re.I),
)
_PROCESS_RESCHEDULE = (
    re.compile(r"\b(?:we need to )?reschedule your interview(?: to [^.]+)?", re.I),
    re.compile(r"\b(?:necesitamos )?reprogramar tu entrevista(?: para [^.]+)?", re.I),
)
_PROCESS_DELAY = (
    re.compile(r"\bthe (?:hiring )?process is taking longer than expected\b", re.I),
    re.compile(r"\bel proceso est[aá] demorando m[aá]s de lo esperado\b", re.I),
)
_OFFER = (
    re.compile(r"\bwe are pleased to offer you the position\b", re.I),
    re.compile(r"\bwe['’]d like to extend (?:you )?an offer\b", re.I),
    re.compile(r"\bwe would like to extend (?:you )?an offer\b", re.I),
    re.compile(r"\bnos complace ofrecerte el puesto\b", re.I),
    re.compile(r"\bqueremos hacerte una oferta laboral\b", re.I),
)
_REJECTION = (
    re.compile(r"\bwe will not be moving forward with your application\b", re.I),
    re.compile(r"\bwe have decided to move forward with other candidates\b", re.I),
    re.compile(r"\bthis position has been filled\b", re.I),
    re.compile(r"\bno continuaremos con tu candidatura\b", re.I),
    re.compile(r"\bhemos decidido avanzar con otros (?:perfiles|candidatos)\b", re.I),
    re.compile(r"\bel puesto (?:ya )?ha sido cubierto\b", re.I),
)
_GENERIC_PROCESS = (
    re.compile(r"\bwe will share next steps soon\b", re.I),
    re.compile(r"\btenemos novedades sobre tu perfil\b", re.I),
)
_OUT_OF_OFFICE = (
    re.compile(r"\bautomatic reply:.{0,120}\bout of the office\b", re.I),
    re.compile(r"\b(?:automatic reply|out of office)\b", re.I),
    re.compile(r"\brespuesta autom[aá]tica:.{0,120}\bfuera de la oficina\b", re.I),
    re.compile(r"\bfuera de la oficina\b", re.I),
)

_INTERVIEW_GUARDS = (*_HYPOTHETICAL, *_NEGATED_INTERVIEW, *_GENERIC_DESCRIPTION)


def _earliest_match(
    patterns: Iterable[re.Pattern[str]],
    text: str,
) -> re.Match[str] | None:
    matches = [match for pattern in patterns if (match := pattern.search(text)) is not None]
    if not matches:
        return None
    return min(matches, key=lambda match: (match.start(), match.end()))


def _has_match(patterns: Iterable[re.Pattern[str]], text: str) -> bool:
    return any(pattern.search(text) is not None for pattern in patterns)


def _signal(
    *,
    kind: ProcessSignalKind,
    confidence: ProcessConfidence,
    reason_code: str,
    match: re.Match[str],
) -> ProcessSignal:
    return ProcessSignal(
        kind=kind,
        confidence=confidence,
        reason_code=reason_code,
        evidence_spans=[
            EvidenceSpan(
                start=match.start(),
                end=match.end(),
                text=match.group(0),
            )
        ],
    )


class DeterministicProcessClassifier:
    def classify(self, text: str) -> ProcessClassification:
        signals: list[ProcessSignal] = []

        ack = _earliest_match(_APPLICATION_ACK, text)
        if ack is not None:
            signals.append(
                _signal(
                    kind="APPLICATION_ACKNOWLEDGED",
                    confidence="HIGH",
                    reason_code="APPLICATION_RECEIPT_EXPLICIT",
                    match=ack,
                )
            )

        interview_blocked = _has_match(_INTERVIEW_GUARDS, text)
        if not interview_blocked:
            interview = _earliest_match(_INTERVIEW_EXPLICIT, text)
            if interview is not None:
                signals.append(
                    _signal(
                        kind="INTERVIEW_PROPOSED",
                        confidence="HIGH",
                        reason_code="INTERVIEW_INVITATION_EXPLICIT",
                        match=interview,
                    )
                )
            else:
                interview_context = _earliest_match(_INTERVIEW_CONTEXT, text)
                if interview_context is not None:
                    signals.append(
                        _signal(
                            kind="INTERVIEW_PROPOSED",
                            confidence="MEDIUM",
                            reason_code="INTERVIEW_SCHEDULING_CONTEXT",
                            match=interview_context,
                        )
                    )

        stage = _earliest_match(_STAGE_ADVANCED, text)
        if stage is not None:
            signals.append(
                _signal(
                    kind="STAGE_ADVANCED",
                    confidence="HIGH",
                    reason_code="STAGE_ADVANCEMENT_EXPLICIT",
                    match=stage,
                )
            )

        reschedule = _earliest_match(_PROCESS_RESCHEDULE, text)
        if reschedule is not None:
            signals.append(
                _signal(
                    kind="PROCESS_UPDATED",
                    confidence="HIGH",
                    reason_code="PROCESS_RESCHEDULE_EXPLICIT",
                    match=reschedule,
                )
            )
        else:
            delay = _earliest_match(_PROCESS_DELAY, text)
            if delay is not None:
                signals.append(
                    _signal(
                        kind="PROCESS_UPDATED",
                        confidence="MEDIUM",
                        reason_code="PROCESS_DELAY_EXPLICIT",
                        match=delay,
                    )
                )

        offer = _earliest_match(_OFFER, text)
        if offer is not None:
            signals.append(
                _signal(
                    kind="OFFER_RECEIVED",
                    confidence="HIGH",
                    reason_code="OFFER_EXPLICIT",
                    match=offer,
                )
            )

        rejected = _earliest_match(_REJECTION, text)
        if rejected is not None:
            signals.append(
                _signal(
                    kind="REJECTED",
                    confidence="HIGH",
                    reason_code="REJECTION_EXPLICIT",
                    match=rejected,
                )
            )

        if not signals:
            generic = _earliest_match(_GENERIC_PROCESS, text)
            if generic is not None:
                return ProcessClassification(
                    disposition="CLASSIFIED",
                    classifier_version=CLASSIFIER_VERSION,
                    ruleset_version=RULESET_VERSION,
                    signals=[
                        _signal(
                            kind="PROCESS_UPDATED",
                            confidence="LOW",
                            reason_code="GENERIC_PROCESS_SIGNAL",
                            match=generic,
                        )
                    ],
                    warnings=["low_confidence_only"],
                )

            if _earliest_match(_OUT_OF_OFFICE, text) is not None:
                return ProcessClassification(
                    disposition="NOT_PROCESS",
                    classifier_version=CLASSIFIER_VERSION,
                    ruleset_version=RULESET_VERSION,
                    signals=[],
                    warnings=[],
                )

            return ProcessClassification(
                disposition="AMBIGUOUS",
                classifier_version=CLASSIFIER_VERSION,
                ruleset_version=RULESET_VERSION,
                signals=[],
                warnings=[],
            )

        kinds = {signal.kind for signal in signals}
        conflict_kinds = {
            "INTERVIEW_PROPOSED",
            "STAGE_ADVANCED",
            "PROCESS_UPDATED",
            "OFFER_RECEIVED",
        }
        if "REJECTED" in kinds and kinds.intersection(conflict_kinds):
            return ProcessClassification(
                disposition="AMBIGUOUS",
                classifier_version=CLASSIFIER_VERSION,
                ruleset_version=RULESET_VERSION,
                signals=signals,
                warnings=["conflicting_process_signals"],
            )

        warnings = (
            ["low_confidence_only"]
            if signals and all(signal.confidence == "LOW" for signal in signals)
            else []
        )
        return ProcessClassification(
            disposition="CLASSIFIED",
            classifier_version=CLASSIFIER_VERSION,
            ruleset_version=RULESET_VERSION,
            signals=signals,
            warnings=warnings,
        )
