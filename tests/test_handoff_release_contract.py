from pathlib import Path


HANDOFF_ROOT = Path("app/handoffs")
PUBLIC_CONTRACT_DOCS = (Path("README.md"), Path("docs/CROSS_REPO_HANDOFF_V01.md"))

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

REQUIRED_PUBLIC_BOUNDARIES = (
    "handoff preview != import",
    "IMPORT_PUBLIC_CONTRIBUTION != automatic import",
    "PUBLIC_CONTRIBUTION_CANDIDATE != JOB_OPENING",
)


def _handoff_source() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(HANDOFF_ROOT.rglob("*.py"))
    )


def _public_contract_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in PUBLIC_CONTRACT_DOCS)


def test_handoff_package_has_no_forbidden_authority_or_io_references() -> None:
    source = _handoff_source()

    for forbidden in FORBIDDEN_PRODUCTION_REFERENCES:
        assert forbidden not in source


def test_public_docs_freeze_handoff_authority_boundary() -> None:
    public_contract = _public_contract_text()

    for statement in REQUIRED_PUBLIC_BOUNDARIES:
        assert statement in public_contract
