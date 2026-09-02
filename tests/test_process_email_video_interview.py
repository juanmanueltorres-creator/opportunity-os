import pytest

from app.process_email.deterministic import DeterministicProcessClassifier


def test_one_way_video_interview_action_is_explicit_interview_signal() -> None:
    classifier = DeterministicProcessClassifier()
    text = (
        "This is a friendly reminder that the last day to submit your one-way "
        "video interview for the AI Product Engineer role is Thursday. "
        "Visit the welcome page to access the questions and record videos of "
        "your responses."
    )

    result = classifier.classify(text)

    assert result.disposition == "CLASSIFIED"
    assert len(result.signals) == 1
    signal = result.signals[0]
    assert signal.kind == "INTERVIEW_PROPOSED"
    assert signal.confidence == "HIGH"
    assert signal.reason_code == "INTERVIEW_INVITATION_EXPLICIT"
    assert signal.evidence_spans
    for span in signal.evidence_spans:
        assert text[span.start : span.end] == span.text


@pytest.mark.parametrize(
    "text",
    [
        "5 tips to prepare for your video interview.",
        "Our guide explains how to record video responses for interviews.",
        "Candidates may be asked to complete a one-way video interview.",
        "If selected, you may receive a video interview invitation.",
    ],
)
def test_video_interview_educational_or_hypothetical_language_does_not_invite(
    text: str,
) -> None:
    classifier = DeterministicProcessClassifier()

    result = classifier.classify(text)

    assert all(signal.kind != "INTERVIEW_PROPOSED" for signal in result.signals)
