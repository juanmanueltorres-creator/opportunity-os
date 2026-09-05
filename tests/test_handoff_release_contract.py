from pathlib import Path


HANDOFF_ROOT = Path("app/handoffs")
README = Path("README.md")

FORBIDDEN_PRODUCTION_REFERENCES = (
    "app.targets",
    "app.outreach",
    "app.application",
    "app.relationships",
    "SQLiteContributionRepository",
    "ContributionObservationBridge.import_preview",
    "GitHubPublicContributionProvider",
    "httpx.Client",
)

REQUIRED_README_BOUNDARIES = (
    "handoff preview != import",
    "IMPORT_PUBLIC_CONTRIBUTION != automatic import",
    "PUBLIC_CONTRIBUTION_CANDIDATE != JOB_OPENING",
)


def _handoff_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(HANDOFF_ROOT.rglob("*.py"))
    )


def test_handoff_package_has_no_forbidden_authority_or_io_references() -> None:
    source = _handoff_source()

    for forbidden in FORBIDDEN_PRODUCTION_REFERENCES:
        assert forbidden not in source


def test_readme_freezes_handoff_authority_boundary() -> None:
    readme = README.read_text(encoding="utf-8")

    for statement in REQUIRED_README_BOUNDARIES:
        assert statement in readme
