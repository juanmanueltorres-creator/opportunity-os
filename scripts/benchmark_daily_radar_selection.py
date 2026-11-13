#!/usr/bin/env python3
"""R08/P3/UC01: opt-in, synthetic-only daily radar ranking benchmark.

Run from repository root after installing project dependencies:
    python -m scripts.benchmark_daily_radar_selection
    python -m scripts.benchmark_daily_radar_selection --sizes 600 1800 --repeats 1

No network calls, candidate data, environment secrets or persistent writes.
Timing/memory are measurements for the executing machine, not production SLOs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from statistics import median
from time import perf_counter
import tracemalloc

from app.models.domain import Opportunity
from app.radar.cordoba_filters import partition_cordoba_matches
from app.radar.daily_search import rank
from scripts.daily_job_radar import select_daily_candidate_pool

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def synthetic_jobs(size: int) -> list[Opportunity]:
    """Distinct companies avoid dedupe hiding the truncation effect."""
    if size < 2:
        raise ValueError("size must be at least 2")
    jobs = [
        Opportunity(
            id=f"synthetic:local:{i}", source="remotive", source_id=f"local:{i}",
            source_url=f"https://example.com/jobs/local-{i}",
            company=f"Synthetic Local {i}", title="Coordinador de operaciones",
            description="Gestión de operaciones", location="Córdoba, Argentina",
            remote_policy="onsite", discovered_at=NOW, published_at=NOW,
        )
        for i in range(size - 1)
    ]
    jobs.append(Opportunity(
        id="synthetic:remote", source="remotive", source_id="remote",
        source_url="https://example.com/jobs/remote",
        company="Synthetic Remote", title="Desarrollador Python",
        description="Desarrollo Python", location="Argentina",
        remote_policy="remote", discovered_at=NOW, published_at=NOW,
    ))
    return jobs


def _measure(jobs: list[Opportunity], *, full_pool: bool, repeats: int) -> dict:
    samples_ms: list[float] = []
    peaks_kib: list[float] = []
    remote_in_pool = False
    remote_in_shortlist = False
    pool_size = 0
    for _ in range(repeats):
        tracemalloc.start()
        start = perf_counter()
        try:
            pool = (select_daily_candidate_pool(jobs, now=NOW) if full_pool
                    else rank(jobs, now=NOW, limit=600))
            confirmed, _review = partition_cordoba_matches(pool)
            elapsed_ms = (perf_counter() - start) * 1000
            _current, peak_bytes = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        pool_size = len(pool)
        remote_in_pool = any(item.job.id == "synthetic:remote" for item in pool)
        remote_in_shortlist = any(
            item.job.id == "synthetic:remote" for item in confirmed[:35]
        )
        samples_ms.append(round(elapsed_ms, 3))
        peaks_kib.append(round(peak_bytes / 1024, 1))
    return {
        "median_ms": round(median(samples_ms), 3),
        "peak_traced_kib_max": max(peaks_kib),
        "pool_size": pool_size,
        "remote_in_pool": remote_in_pool,
        "remote_in_top_35": remote_in_shortlist,
        "repeats": repeats,
    }


def run_case(size: int, *, repeats: int = 3) -> dict:
    if repeats < 1:
        raise ValueError("repeats must be at least 1")
    jobs = synthetic_jobs(size)
    legacy = _measure(jobs, full_pool=False, repeats=repeats)
    proposed = _measure(jobs, full_pool=True, repeats=repeats)
    return {"size": size, "legacy_limit_600": legacy, "full_pool": proposed,
            "median_runtime_ratio_full_to_legacy": (
                round(proposed["median_ms"] / legacy["median_ms"], 3)
                if legacy["median_ms"] else None
            )}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[600, 1800, 10000])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    results = [run_case(size, repeats=args.repeats) for size in args.sizes]
    print(json.dumps({
        "kind": "synthetic_r08_p3_uc01_ranking_benchmark",
        "scope": "ranking_and_partition_only; excludes discovery, network and persistence",
        "memory": "tracemalloc Python allocations; not process RSS",
        "note": "synthetic results are not real job coverage or production latency",
        "results": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
