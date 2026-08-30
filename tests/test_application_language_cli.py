from app.application.prepare import _cv_policy, _parser


def _required_args() -> list[str]:
    return [
        "--opportunity",
        "radar.json",
        "--master-facts",
        "master_facts.local.yaml",
        "--evidence-catalog",
        "evidence_catalog.local.yaml",
        "--recruiter-policy",
        "config/recruiter_policy.yaml",
        "--output-root",
        "applications",
    ]


def test_cli_accepts_explicit_spanish_language() -> None:
    args = _parser().parse_args([*_required_args(), "--language", "es"])

    assert args.language == "es"
    assert _cv_policy(args.language).language == "es"


def test_cli_defaults_to_english_for_backward_compatibility() -> None:
    args = _parser().parse_args(_required_args())

    assert args.language == "en"
    assert _cv_policy(args.language).language == "en"
