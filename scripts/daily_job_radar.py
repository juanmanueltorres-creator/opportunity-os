#!/usr/bin/env python3
"""Daily public job discovery; report works without PostgreSQL secrets."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from app.radar.daily_search import discover, rank
from app.radar.cordoba_filters import candidate_lane, partition_cordoba_matches
try:
    from scripts.render_global_radar import render_global_radar
except ModuleNotFoundError:
    # `python scripts/daily_job_radar.py` sets sys.path[0] to scripts/.
    from render_global_radar import render_global_radar
from app.radar.daily_persistence import persist


async def main() -> int:
    output = Path("artifacts/daily-radar")
    output.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    jobs, diagnostics = await discover()
    candidate_pool = rank(jobs, now=now, limit=200)
    global_pool = rank(jobs, now=now, limit=250, include_worldwide_onsite=True,
                       include_ineligible=True)
    confirmed, review = partition_cordoba_matches(candidate_pool)
    matches = confirmed[:35]
    review = review[:20]
    state = {"status": "NOT_CONFIGURED", "created": 0, "existing": 0,
             "history_checked": False}
    error = False
    try:
        state = persist(matches)
    except Exception as exc:
        # Do not expose connection strings, driver error messages or private data.
        state = {"status": "ERROR", "kind": type(exc).__name__}
        error = True
    excluded = set(state.pop("_excluded_ids", []))
    visible_matches = [item for item in matches if item.job.id not in excluded]
    public = {
        "generated_at": now.isoformat(),
        "atlas": [dict(item.as_public_dict(), search_lane=candidate_lane(item))
                  for item in global_pool],
        "atlas_scope": "GLOBAL_DISCOVERY_NOT_VERIFIED",
        "sources": diagnostics,
        "raw_jobs_seen": len(jobs),
        "matches": [dict(item.as_public_dict(), search_lane=candidate_lane(item)) for item in visible_matches],
        "needs_review": [dict(item.as_public_dict(), search_lane="REVIEW") for item in review],
        "geographic_filter": "CORDOBA_LOCAL_OR_CONFIRMED_REMOTE_ARGENTINA",
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
    (output / "radar.html").write_text(render_global_radar(public), encoding="utf-8")
    lines = ["# Opportunity OS — radar diario", "",
             f"Fecha UTC: {now.strftime('%Y-%m-%d %H:%M')}",
             f"Fuente(s): {', '.join(f'{k}={v}' for k,v in diagnostics.items())}",
             f"Vacantes fuente: {len(jobs)} | confirmadas: {len(visible_matches)} | por revisar: {len(review)}",
             f"Persistencia Supabase: {state['status']} (creadas={state.get('created',0)})",
             "", "## Vacantes sugeridas", "",
             "| Afinidad | Empresa y puesto | Fuente | Argentina | Idioma | CV sugerido |",
             "|---:|---|---|---|---|---|"]
    def clean(x: object) -> str:
        return str(x or "").replace("|", "/").replace("\n", " ").replace("\r", " ")[:180]
    for match in visible_matches[:25]:
        row = match.as_public_dict()
        lines.append(f"| {row['score']} | [{clean(row['company'])} — {clean(row['title'])}]({row['source_url']}) | {row['source']} | {row['argentina_eligible']} | {row['work_language']} | {row['cv_track_sugerido']} |")
    lines.extend(["", "## Revisar elegibilidad (NO confirmadas)", "",
                  "| Afinidad | Empresa y puesto | Ubicación | Razón |",
                  "|---:|---|---|---|"])
    for match in review[:15]:
        row = match.as_public_dict()
        lines.append(f"| {row['score']} | [{clean(row['company'])} — {clean(row['title'])}]({row['source_url']}) | {clean(row['location'])} | Remoto sin prueba de elegibilidad AR o modalidad Córdoba sin confirmar |")
    lines.extend(["", "## Observaciones", "",
                  "- Las vacantes son señales de búsqueda y deben revisarse en su página oficial.",
                  "- Confirmadas: remoto explícitamente elegible desde Argentina, o presencial/híbrido explícitamente en Córdoba.",
                  "- Por revisar: remoto con país elegible desconocido o modalidad no declarada en Córdoba.",
                  "- Presencial/híbrido fuera de Córdoba e inglés laboral avanzado obligatorio quedan fuera del shortlist.",
                  "- El historial de Gmail/Drive permanece privado en Supabase; no se publica en este archivo.",
                  "- Los PDF del CV no se generan ni se publican desde GitHub Actions.",
                  ""])
    report = "\n".join(lines)
    (output / "jobs.md").write_text(report, encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write(report)
    print(f"Sources={len(diagnostics)} jobs={len(jobs)} atlas={len(global_pool)} shortlist={len(visible_matches)} db={state['status']}")
    if error:
        return 1
    if not jobs and not any(str(v).startswith("OK") for v in diagnostics.values()):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
