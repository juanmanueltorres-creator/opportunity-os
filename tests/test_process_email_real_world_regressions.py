from app.process_email.deterministic import DeterministicProcessClassifier


def _signals(text: str):
    result = DeterministicProcessClassifier().classify(text)
    return result, [
        (signal.kind, signal.confidence, signal.reason_code)
        for signal in result.signals
    ]


def test_passive_application_receipt_is_acknowledged() -> None:
    result, signals = _signals("Your application to Example has been received.")

    assert result.disposition == "CLASSIFIED"
    assert signals == [
        ("APPLICATION_ACKNOWLEDGED", "HIGH", "APPLICATION_RECEIPT_EXPLICIT")
    ]


def test_passive_application_receipt_without_company_is_acknowledged() -> None:
    result, signals = _signals("Your application has been received.")

    assert result.disposition == "CLASSIFIED"
    assert signals == [
        ("APPLICATION_ACKNOWLEDGED", "HIGH", "APPLICATION_RECEIPT_EXPLICIT")
    ]


def test_decided_not_to_move_forward_is_rejection() -> None:
    result, signals = _signals(
        "We have decided not to move forward with your application at this time."
    )

    assert result.disposition == "CLASSIFIED"
    assert signals == [("REJECTED", "HIGH", "REJECTION_EXPLICIT")]


def test_no_decision_language_is_not_rejection() -> None:
    _, signals = _signals(
        "We have not decided whether to move forward with your application."
    )

    assert all(kind != "REJECTED" for kind, _, _ in signals)


def test_generic_receipt_description_is_not_application_ack() -> None:
    _, signals = _signals("Applications are received through our careers portal.")

    assert all(kind != "APPLICATION_ACKNOWLEDGED" for kind, _, _ in signals)
