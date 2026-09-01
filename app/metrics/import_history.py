from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from app.metrics.history import HistoricalImportManifest, SQLiteHistoricalRepository


@dataclass(frozen=True)
class HistoricalImportResult:
    batch_id: str
    batch_inserted: bool
    observations_inserted: int
    observations_existing: int


def import_manifest_file(
    *,
    manifest_path: str | Path,
    history_db: str | Path,
) -> HistoricalImportResult:
    manifest_path = Path(manifest_path)
    history_db = Path(history_db)

    manifest = HistoricalImportManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )

    repository = SQLiteHistoricalRepository(history_db)
    repository.initialize()

    _, batch_inserted = repository.save_batch(manifest.batch)
    inserted = 0
    existing = 0
    for observation in manifest.observations:
        _, was_inserted = repository.save_observation(observation)
        if was_inserted:
            inserted += 1
        else:
            existing += 1

    return HistoricalImportResult(
        batch_id=manifest.batch.batch_id,
        batch_inserted=batch_inserted,
        observations_inserted=inserted,
        observations_existing=existing,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import normalized historical observations into the private Search Health store."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--history-db",
        type=Path,
        default=Path("state/history.local.sqlite3"),
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    result = import_manifest_file(
        manifest_path=args.manifest,
        history_db=args.history_db,
    )
    print(f"batch_id={result.batch_id}")
    print(f"batch_inserted={str(result.batch_inserted).lower()}")
    print(f"observations_inserted={result.observations_inserted}")
    print(f"observations_existing={result.observations_existing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
