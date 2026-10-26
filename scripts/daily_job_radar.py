#!/usr/bin/env python3
"""Daily public job discovery; report works without PostgreSQL secrets."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from app.radar.daily_search import discover, rank
from app.radar.daily_persistence import persist


async def main() -> int:
    output = Path("artifacts/daily-radar")
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    jobs, diagnostics = await discover()
    matches = rank(jobs, now=now, limit=35)
    state = {"status": "NOT_CONFIGURED", "created": 0, "existing": 0,
             "history_checked": False}
    error = False
    try:
        state = persist(matches)
    except Exception as exc:
        # Do not expose connection strings, driver error messages or private data.
        state = {"status": "ERROR", "kind": type(exc).__name__}
        error = True
    public = {
        "generated_at": now.isoformat(),
        "sources": diagnostics,
        "raw_jobs_seen": len(jobs),
        "matches": [item.as_public_dict() for item in matches],
        "persistence": state,
        "caveats": [
            "Vacantes pendientes de verificación manual (no aplicar automáticamente).",
            "El idioma del aviso no prueba el idioma laboral del equipo.",
            "Remoto no prueba elegibilidad contractual desde Argentina.",
            "CV: se sugiere un perfil; no se genera PDF sin hechos/evidencia aprobados.",
            "Sin secreto PostgreSQL no se consulta historial privado ni se sincroniza Supabase."
        ],
    }
    if state["status"] == "OK":
        for row in public["matches"]:
            row["historial_postulaciones_cruzado"] = True
    (output / "jobs.json").write_text(
        json.dumps(public, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = ["# Opportunity OS — radar diario", "",
             f"Fecha UTC: {now.strftime('%Y-%m-%d %H:%M')}",
             f"Fuente(s): {', '.join(f'{k}={v}' for k,v in diagnostics.items())}",
             f"Vacantes fuente: {len(jobs)} | preselección: {len(matches)}",
             f"Persistencia Supabase: {state['status']} (creadas={state.get('created',0)})",
             "", "## Vacantes sugeridas", "",
             "| Afinidad | Empresa y puesto | Fuente | Argentina | Idioma | CV sugerido |",
             "|---:|---|---|---|---|---|"]
    for match in matches[:25]:
        row = match.as_public_dict()
        def clean(x: object) -> str:
            return str(x or "").replace("|", "/").replace("\n", " ").replace("\r", " ")[:180]
        lines.append(f"| {row['score']} | [{clean(row['company'])} — {clean(row['title'])}]({row['source_url']}) | {row['source']} | {row['argentina_eligible']} | {row['work_language']} | {row['cv_track_sugerido']} |")
    lines.extend(["", "## Observaciones", "",
                  "- Las vacantes son señales de búsqueda y deben revisarse en su página oficial.",
                  "- Las preferencias priorizan Argentina/LATAM y penalizan inglés avanzado exigido.",
                  "- El historial de Gmail/Drive permanece privado en Supabase; no se publica en este archivo.",
                  "- Los PDF del CV no se generan ni se publican desde GitHub Actions.",
                  ""])
    report = "\n".join(lines)
    (output / "jobs.md").write_text(report, encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(report)
    print(f"Sources={len(diagnostics)} jobs={len(jobs)} shortlist={len(matches)} db={state['status']}")
    if error:
        return 1
    if not jobs and not any(str(v).startswith("OK") for v in diagnostics.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
