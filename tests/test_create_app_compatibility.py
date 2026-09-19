from inspect import Parameter, signature

from app.main import create_app


def test_create_app_preserves_legacy_positional_prefix() -> None:
    expected = [
        "repository",
        "profile",
        "remotive_connector",
        "radar_service",
        "enable_default_radar",
        "community_digest_preview_service",
        "enable_default_community_digest_preview",
        "target_service",
        "enable_default_targets",
        "relationship_memory",
        "enable_default_relationships",
        "operator_bridge_service",
        "enable_operator_import",
        "gmail_read_service",
        "enable_gmail_read",
        "process_email_service",
        "enable_process_email",
    ]
    parameters = list(signature(create_app).parameters.values())

    assert [item.name for item in parameters[: len(expected)]] == expected
    assert all(
        item.kind is Parameter.POSITIONAL_OR_KEYWORD
        for item in parameters[: len(expected)]
    )


def test_new_curation_dependencies_are_keyword_only() -> None:
    parameters = signature(create_app).parameters
    for name in (
        "availability_repository",
        "availability_verification_service",
        "verification_queue_service",
        "verification_review_session_service",
        "review_evidence_draft_service",
        "daily_curation_service",
        "daily_curation_operator_view_service",
        "source_refresh_service",
        "refresh_curation_operator_service",
        "curation_ledger_repository",
        "curation_ledger_service",
    ):
        assert parameters[name].kind is Parameter.KEYWORD_ONLY
