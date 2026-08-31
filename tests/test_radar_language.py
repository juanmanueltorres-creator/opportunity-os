from types import SimpleNamespace

import pytest

from app.radar.language import detect_text_language, resolve_output_language


def _assessment(
    *,
    title: str,
    description: str,
    location: str | None = None,
    country: str | None = None,
    region: str | None = None,
):
    def derived(value: str | None):
        return None if value is None else SimpleNamespace(value=value)

    return SimpleNamespace(
        opportunity=SimpleNamespace(
            title=title,
            description=description,
            location=location,
        ),
        enrichment=SimpleNamespace(
            country=derived(country),
            region=derived(region),
        ),
    )


def test_canals_like_english_posting_resolves_english_from_posting() -> None:
    assessment = _assessment(
        title="Junior Software Engineer",
        description=(
            "We are looking for a junior engineer to join our team. "
            "You will build software, work with customers, and help improve "
            "our product and engineering workflows."
        ),
        location="Remote - Americas",
    )

    decision = resolve_output_language(assessment)

    assert decision.language == "en"
    assert decision.basis == "posting_language"
    assert decision.confidence == pytest.approx(0.95)


def test_spanish_argentina_posting_resolves_spanish_from_posting() -> None:
    assessment = _assessment(
        title="Desarrollador Backend Junior",
        description=(
            "Buscamos una persona para sumarse al equipo de desarrollo. "
            "El puesto requiere experiencia con Python y trabajo con datos. "
            "Ofrecemos modalidad híbrida y oportunidades de aprendizaje."
        ),
        location="Córdoba, Argentina",
    )

    decision = resolve_output_language(assessment)

    assert decision.language == "es"
    assert decision.basis == "posting_language"


def test_ambiguous_technical_posting_in_argentina_uses_market_location() -> None:
    assessment = _assessment(
        title="Python / SQL Developer",
        description="Python SQL FastAPI PostgreSQL APIs Git",
        country="Argentina",
        location="Córdoba",
    )

    decision = resolve_output_language(assessment)

    assert decision.language == "es"
    assert decision.basis == "market_location"
    assert decision.source_field == "enrichment.country"


def test_ambiguous_international_remote_posting_falls_back_to_english() -> None:
    assessment = _assessment(
        title="Backend Developer",
        description="Python SQL APIs Git",
        location="Remote",
        region="LATAM",
    )

    decision = resolve_output_language(assessment)

    assert decision.language == "en"
    assert decision.basis == "international_remote_fallback"
    assert decision.confidence == pytest.approx(0.60)


def test_explicit_spanish_override_wins_over_english_posting() -> None:
    assessment = _assessment(
        title="Junior Software Engineer",
        description="We are looking for a developer to join our team and build software products.",
    )

    decision = resolve_output_language(assessment, override="es")

    assert decision.language == "es"
    assert decision.basis == "explicit_override"
    assert decision.confidence == 1.0
    assert decision.source_field == "cli.language"


def test_explicit_english_override_wins_over_spanish_posting() -> None:
    assessment = _assessment(
        title="Desarrollador Junior",
        description="Buscamos una persona para sumarse al equipo y desarrollar nuestro producto.",
    )

    decision = resolve_output_language(assessment, override="en")

    assert decision.language == "en"
    assert decision.basis == "explicit_override"


def test_english_required_does_not_flip_otherwise_spanish_posting() -> None:
    assessment = _assessment(
        title="Desarrollador Backend",
        description=(
            "Buscamos una persona para sumarse al equipo de desarrollo. "
            "El puesto ofrece modalidad híbrida y trabajo con clientes locales. "
            "English required."
        ),
        location="Buenos Aires, Argentina",
    )

    decision = resolve_output_language(assessment)

    assert decision.language == "es"
    assert decision.basis == "posting_language"


def test_text_detector_is_conservative_for_technical_copy() -> None:
    assert detect_text_language("Python FastAPI PostgreSQL React Git APIs") is None


def test_text_detector_classifies_clear_spanish_and_english() -> None:
    assert detect_text_language(
        "Hola equipo, vi la búsqueda y me interesa el puesto. Gracias por su tiempo."
    ) == "es"
    assert detect_text_language(
        "Hi team, I saw the opening and I am interested in the role. Thank you for your time."
    ) == "en"
