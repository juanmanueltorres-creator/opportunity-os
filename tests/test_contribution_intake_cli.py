from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.contributions.models import PublicContributionEntry
from app.contributions.observations import (
    PREVIEW_VERSION,
    ContributionImportReceipt,
    ContributionImportResult,
    ContributionObservation,
    ContributionPreview,
    observation_sha256,
)
from app.contributions.projector import ContributionProjector

NOW = datetime(2026, 9, 4, 14, 0, tzinfo=timezone.utc)
ISSUE = "https://github.com/trixocom/odoo-argentina-trx-ce/issues/1"
ENTRY_ID = "contrib-cli-test"


def importable_preview() -> ContributionPreview:
    observation = ContributionObservation(
        observation_id="obs-cli-preview",
        source_ref=ISSUE,
        kind="ISSUE_AVAILABLE",
        entry_id=ENTRY_ID,
        repository_full_name="trixocom/odoo-argentina-trx-ce",
        public_title="Invalid language code: es_419 en l10n_ar_edi_base",
        fact_at=NOW,
        captured_at=NOW,
        task_ref=ISSUE,
        source_fact_identity="issue:1:open::2026-09-04T14:00:00+00:00",
    )
    entry = PublicContributionEntry(
        entry_id=ENTRY_ID,
        repository_full_name="trixocom/odoo-argentina-trx-ce",
        repository_url="https://github.com/trixocom/odoo-argentina-trx-ce",
        origin="PUBLIC_ISSUE",
        need_basis="OBSERVED",
        need_statement="Invalid language code: es_419 en l10n_ar_edi_base",
        evidence_refs=[ISSUE],
        task_ref=ISSUE,
        bounded_task="Invalid language code: es_419 en l10n_ar_edi_base",
        task_claim_state="AVAILABLE",
        expected_effort="UNKNOWN",
        risk_level="UNKNOWN",
        discovered_at=NOW,
    )
    context = ContributionProjector().project(entry=entry, events=[])
    return ContributionPreview(
        preview_version=PREVIEW_VERSION,
        status="IMPORTABLE",
        observation=observation,
        observation_sha256=observation_sha256(observation),
        preview_sha256="c" * 64,
        entry_id=ENTRY_ID,
        source_ref=ISSUE,
        proposed_entry=entry,
        candidate_event=None,
        context_before=None,
        context_after=context,
        errors=[],
        external_actions=[],
    )


def no_change_preview() -> ContributionPreview:
    source = importable_preview()
    return source.model_copy(
        update={
            "status": "NO_CHANGE",
            "proposed_entry": None,
            "context_after": None,
        }
    )


class DummyClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakePreviewBridge:
    def __init__(self, preview: ContributionPreview) -> None:
        self.value = preview
        self.preview_calls = 0
        self.import_calls = 0

    def preview(self, selection):
        self.preview_calls += 1
        assert selection.source_url == ISSUE
        return self.value

    def import_preview(self, request):
        self.import_calls += 1
        raise AssertionError("preview command must not import")


class FakeImportBridge:
    def __init__(self, result: ContributionImportResult) -> None:
        self.result = result
        self.calls = 0

    def import_preview(self, request):
        self.calls += 1
        assert request.preview.status == "IMPORTABLE"
        assert request.confirmed_by == "juan"
        return self.result


def imported_result(preview: ContributionPreview) -> ContributionImportResult:
    receipt = ContributionImportReceipt(
        receipt_id="receipt-cli",
        observation_id=preview.observation.observation_id,
        observation_sha256=preview.observation_sha256,
        preview_sha256=preview.preview_sha256,
        entry_id=preview.entry_id,
        contribution_event_id=None,
        source_ref=preview.source_ref,
        confirmed_by="juan",
        confirmed_at=NOW + timedelta(minutes=1),
        processed_at=NOW + timedelta(minutes=2),
        status="IMPORTED",
    )
    return ContributionImportResult(status="IMPORTED", receipt=receipt, errors=[])


def test_preview_writes_exact_typed_json_without_creating_db(tmp_path, monkeypatch, capsys):
    from app.contributions import intake_cli

    preview = importable_preview()
    bridge = FakePreviewBridge(preview)
    client = DummyClient()
    monkeypatch.setattr(intake_cli, "_build_preview_bridge", lambda repository: (bridge, client))
    monkeypatch.setattr(intake_cli, "_clock", lambda: NOW)

    db = tmp_path / "state" / "contributions.local.sqlite3"
    out = tmp_path / "preview.json"
    code = intake_cli.main([
        "preview",
        "--url", ISSUE,
        "--operator-login", "juanmanueltorres-creator",
        "--db", str(db),
        "--out", str(out),
    ])

    assert code == 0
    assert bridge.preview_calls == 1
    assert bridge.import_calls == 0
    assert out.read_text(encoding="utf-8") == preview.model_dump_json(indent=2)
    assert not db.exists()
    assert client.closed is True
    printed = capsys.readouterr().out
    assert "IMPORTABLE" in printed
    assert ENTRY_ID in printed
    assert "raw_body" not in printed


def test_preview_missing_default_db_has_no_write_side_effect(tmp_path, monkeypatch):
    from app.contributions import intake_cli

    monkeypatch.chdir(tmp_path)
    bridge = FakePreviewBridge(importable_preview())
    client = DummyClient()
    monkeypatch.setattr(intake_cli, "_build_preview_bridge", lambda repository: (bridge, client))
    out = tmp_path / "preview.json"

    assert intake_cli.main([
        "preview", "--url", ISSUE,
        "--operator-login", "juanmanueltorres-creator",
        "--out", str(out),
    ]) == 0
    assert not Path("state/contributions.local.sqlite3").exists()


def test_import_initializes_only_after_valid_importable_preview(tmp_path, monkeypatch, capsys):
    from app.contributions import intake_cli

    preview = importable_preview()
    preview_file = tmp_path / "preview.json"
    preview_file.write_text(preview.model_dump_json(indent=2), encoding="utf-8")
    db = tmp_path / "state" / "contributions.local.sqlite3"
    bridge = FakeImportBridge(imported_result(preview))
    monkeypatch.setattr(intake_cli, "_build_import_bridge", lambda repository: bridge)
    monkeypatch.setattr(intake_cli, "_clock", lambda: NOW + timedelta(minutes=1))

    code = intake_cli.main([
        "import",
        "--preview-file", str(preview_file),
        "--confirmed-by", "juan",
        "--db", str(db),
    ])

    assert code == 0
    assert db.exists()
    assert bridge.calls == 1
    printed = capsys.readouterr().out
    assert "receipt-cli" in printed


def test_non_importable_preview_is_rejected_before_repository_initialization(tmp_path, monkeypatch):
    from app.contributions import intake_cli

    preview_file = tmp_path / "preview.json"
    preview_file.write_text(no_change_preview().model_dump_json(indent=2), encoding="utf-8")
    db = tmp_path / "state" / "contributions.local.sqlite3"
    called = False

    def should_not_build(repository):
        nonlocal called
        called = True
        raise AssertionError("bridge must not be built for non-importable preview")

    monkeypatch.setattr(intake_cli, "_build_import_bridge", should_not_build)
    assert intake_cli.main([
        "import",
        "--preview-file", str(preview_file),
        "--confirmed-by", "juan",
        "--db", str(db),
    ]) != 0
    assert called is False
    assert not db.exists()


def test_import_requires_explicit_confirmed_by(tmp_path):
    from app.contributions import intake_cli

    preview_file = tmp_path / "preview.json"
    preview_file.write_text(importable_preview().model_dump_json(), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        intake_cli.main(["import", "--preview-file", str(preview_file)])
    assert exc.value.code == 2


def test_parser_exposes_no_auto_confirm_option():
    from app.contributions import intake_cli

    parser = intake_cli._build_parser()
    options = {
        option
        for action in parser._actions
        for option in action.option_strings
    }
    subparsers = next(action for action in parser._actions if action.dest == "command")
    for subparser in subparsers.choices.values():
        options.update(
            option
            for action in subparser._actions
            for option in action.option_strings
        )
    assert "--yes" not in options
    assert "--auto-confirm" not in options
    assert "--confirm" not in options
