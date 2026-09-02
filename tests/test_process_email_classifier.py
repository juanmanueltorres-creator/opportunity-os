import pytest

from app.process_email.deterministic import (
    CLASSIFIER_VERSION,
    RULESET_VERSION,
    DeterministicProcessClassifier,
)


@pytest.fixture
def classifier() -> DeterministicProcessClassifier:
    return DeterministicProcessClassifier()


@pytest.mark.parametrize(
    ("text", "kind", "reason_code"),
    [
        (
            "We received your application.",
            "APPLICATION_ACKNOWLEDGED",
            "APPLICATION_RECEIPT_EXPLICIT",
        ),
        (
            "Hemos recibido tu candidatura.",
            "APPLICATION_ACKNOWLEDGED",
            "APPLICATION_RECEIPT_EXPLICIT",
        ),
        (
            "We would like to invite you to an interview.",
            "INTERVIEW_PROPOSED",
            "INTERVIEW_INVITATION_EXPLICIT",
        ),
        (
            "Queremos invitarte a una entrevista.",
            "INTERVIEW_PROPOSED",
            "INTERVIEW_INVITATION_EXPLICIT",
        ),
        (
            "You have advanced to the next stage of our hiring process.",
            "STAGE_ADVANCED",
            "STAGE_ADVANCEMENT_EXPLICIT",
        ),
        (
            "Avanzaste a la siguiente etapa del proceso.",
            "STAGE_ADVANCED",
            "STAGE_ADVANCEMENT_EXPLICIT",
        ),
        (
            "We need to reschedule your interview to Thursday.",
            "PROCESS_UPDATED",
            "PROCESS_RESCHEDULE_EXPLICIT",
        ),
        (
            "Necesitamos reprogramar tu entrevista para el jueves.",
            "PROCESS_UPDATED",
            "PROCESS_RESCHEDULE_EXPLICIT",
        ),
        (
            "We are pleased to offer you the position.",
            "OFFER_RECEIVED",
            "OFFER_EXPLICIT",
        ),
        (
            "Nos complace ofrecerte el puesto.",
            "OFFER_RECEIVED",
            "OFFER_EXPLICIT",
        ),
        (
            "We will not be moving forward with your application.",
            "REJECTED",
            "REJECTION_EXPLICIT",
        ),
        (
            "No continuaremos con tu candidatura.",
            "REJECTED",
            "REJECTION_EXPLICIT",
        ),
    ],
)
def test_explicit_bilingual_lifecycle_facts_are_high_confidence(
    classifier: DeterministicProcessClassifier,
    text: str,
    kind: str,
    reason_code: str,
) -> None:
    result = classifier.classify(text)

    assert result.disposition == "CLASSIFIED"
    matching = [signal for signal in result.signals if signal.kind == kind]
    assert len(matching) == 1
    signal = matching[0]
    assert signal.confidence == "HIGH"
    assert signal.reason_code == reason_code
    assert signal.evidence_spans
    for span in signal.evidence_spans:
        assert text[span.start : span.end] == span.text


@pytest.mark.parametrize(
    "text",
    [
        "Our interview process normally takes two weeks.",
        "If selected, you may be invited to interview.",
        "We are not yet scheduling interviews.",
        "Nuestro proceso de entrevistas normalmente tarda dos semanas.",
        "Si eres seleccionado, podrías ser invitado a una entrevista.",
        "Aún no estamos coordinando entrevistas.",
    ],
)
def test_generic_hypothetical_or_negated_interview_language_does_not_invite(
    classifier: DeterministicProcessClassifier,
    text: str,
) -> None:
    result = classifier.classify(text)
    assert all(signal.kind != "INTERVIEW_PROPOSED" for signal in result.signals)


@pytest.mark.parametrize(
    "text",
    [
        "The compensation range for this role is USD 80k-100k.",
        "El rango salarial para este puesto es de USD 80k a 100k.",
    ],
)
def test_compensation_discussion_is_not_an_offer(
    classifier: DeterministicProcessClassifier,
    text: str,
) -> None:
    result = classifier.classify(text)
    assert all(signal.kind != "OFFER_RECEIVED" for signal in result.signals)


@pytest.mark.parametrize(
    "text",
    [
        "We are still reviewing applications.",
        "Aún estamos revisando las candidaturas.",
        "We have not made a decision yet.",
        "Aún no tomamos una decisión.",
    ],
)
def test_review_or_no_decision_is_not_rejection(
    classifier: DeterministicProcessClassifier,
    text: str,
) -> None:
    result = classifier.classify(text)
    assert all(signal.kind != "REJECTED" for signal in result.signals)


@pytest.mark.parametrize(
    "text",
    [
        "We will share next steps soon.",
        "Tenemos novedades sobre tu perfil.",
    ],
)
def test_weak_process_language_is_low_only_and_non_authoritative(
    classifier: DeterministicProcessClassifier,
    text: str,
) -> None:
    result = classifier.classify(text)

    assert result.disposition == "CLASSIFIED"
    assert len(result.signals) == 1
    assert result.signals[0].kind == "PROCESS_UPDATED"
    assert result.signals[0].confidence == "LOW"
    assert result.signals[0].reason_code == "GENERIC_PROCESS_SIGNAL"
    assert result.warnings == ["low_confidence_only"]


@pytest.mark.parametrize(
    "text",
    [
        "Automatic reply: I am out of the office until Monday.",
        "Respuesta automática: estoy fuera de la oficina hasta el lunes.",
    ],
)
def test_explicit_out_of_office_is_not_process(
    classifier: DeterministicProcessClassifier,
    text: str,
) -> None:
    result = classifier.classify(text)

    assert result.disposition == "NOT_PROCESS"
    assert result.signals == []
    assert result.warnings == []


def test_unknown_generic_message_is_ambiguous_not_not_process(
    classifier: DeterministicProcessClassifier,
) -> None:
    result = classifier.classify("Hello, thanks for your message.")

    assert result.disposition == "AMBIGUOUS"
    assert result.signals == []


def test_conversation_with_hiring_manager_can_be_medium_interview_signal(
    classifier: DeterministicProcessClassifier,
) -> None:
    text = "Would Tuesday at 3 PM work for a conversation with the hiring manager?"
    result = classifier.classify(text)

    assert result.disposition == "CLASSIFIED"
    assert len(result.signals) == 1
    signal = result.signals[0]
    assert signal.kind == "INTERVIEW_PROPOSED"
    assert signal.confidence == "MEDIUM"
    assert signal.reason_code == "INTERVIEW_SCHEDULING_CONTEXT"


def test_compatible_application_ack_and_interview_are_both_retained(
    classifier: DeterministicProcessClassifier,
) -> None:
    result = classifier.classify(
        "We received your application and would like to invite you to an interview."
    )

    assert result.disposition == "CLASSIFIED"
    assert [signal.kind for signal in result.signals] == [
        "APPLICATION_ACKNOWLEDGED",
        "INTERVIEW_PROPOSED",
    ]
    assert result.warnings == []


def test_rejection_plus_ack_is_compatible_and_retained(
    classifier: DeterministicProcessClassifier,
) -> None:
    result = classifier.classify(
        "We received your application, but we will not be moving forward with your application."
    )

    assert result.disposition == "CLASSIFIED"
    assert [signal.kind for signal in result.signals] == [
        "APPLICATION_ACKNOWLEDGED",
        "REJECTED",
    ]


def test_rejection_plus_new_interview_is_ambiguous_conflict(
    classifier: DeterministicProcessClassifier,
) -> None:
    result = classifier.classify(
        "This position has been filled, but we would like to invite you to an interview for another opportunity."
    )

    assert result.disposition == "AMBIGUOUS"
    kinds = [signal.kind for signal in result.signals]
    assert "REJECTED" in kinds
    assert "INTERVIEW_PROPOSED" in kinds
    assert result.warnings == ["conflicting_process_signals"]


def test_classifier_versions_are_exact_and_result_is_deterministic(
    classifier: DeterministicProcessClassifier,
) -> None:
    text = "We received your application and would like to invite you to an interview."

    first = classifier.classify(text)
    second = classifier.classify(text)

    assert CLASSIFIER_VERSION == "deterministic-process-email-v1"
    assert RULESET_VERSION == "es-en-2026-09-v3"
    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_empty_or_whitespace_text_fails_closed_as_ambiguous(
    classifier: DeterministicProcessClassifier,
) -> None:
    assert classifier.classify("   ").disposition == "AMBIGUOUS"
