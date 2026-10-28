"""Self-contained, no-backend HTML radar from public job records only."""
from __future__ import annotations

from html import escape
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any


def _url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            return None
        return value
    except ValueError:
        return None


def render_job_report(report: dict[str, Any], destination: Path) -> None:
    """Generate an offline-readable report; do not include personal CRM records."""
    sections = [
        ("Aplicables", report.get("matches", []), "Aplicables según filtros geográficos; verificar oferta vigente."),
        ("Revisar", report.get("needs_review", []), "Elegibilidad u otros requisitos todavía sin confirmar."),
        ("Atlas global", report.get("global_watchlist", []), "Exploración de compañías; NO implica elegibilidad desde Argentina."),
    ]
    cards: list[str] = []
    for label, records, caveat in sections:
        for row in records:
            link = _url(row.get("source_url"))
            if not link:
                continue
            company = escape(str(row.get("company") or "Sin empresa"))
            title = escape(str(row.get("title") or "Sin título"))
            loc = escape(str(row.get("location") or "Ubicación no declarada"))
            track = escape(str(row.get("track") or "Sin sector"))
            score = escape(str(row.get("score") or "—"))
            source = escape(str(row.get("source") or "Fuente"))
            region = escape(label)
            item = (
                '<article class="job" data-bucket="' + region + '" data-search="'
                + escape(" ".join([company, title, loc, track]).casefold(), quote=True) + '">'
                + '<div class="line"><span class="company">' + company + '</span><span class="score">' + score + ' / 100</span></div>'
                + '<h3>' + title + '</h3>'
                + '<p class="meta">' + loc + ' · ' + track + ' · ' + source + '</p>'
                + '<div class="line"><span class="chip">' + region + '</span>'
                + '<a href="' + escape(link, quote=True) + '" target="_blank" rel="noopener noreferrer">Abrir aviso ↗</a></div>'
                + '<p class="small">' + escape(caveat) + '</p></article>'
            )
            cards.append(item)
    html = """<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">
<title>Opportunity OS · Radar</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,sans-serif;background:#0b0e10;color:#f1f3f1}
*{box-sizing:border-box}body{margin:0}main{max-width:1240px;margin:0 auto;padding:28px 22px 70px}
header{display:flex;justify-content:space-between;gap:12px;align-items:center;border-bottom:1px solid #303439;padding:15px 22px}
.logo{font-weight:800;letter-spacing:-.03em}.tiny{font-size:11px;color:#a0aaa7}.eyebrow{font:11px ui-monospace,monospace;color:#c7e88a;letter-spacing:.18em}
h1{font-size:clamp(34px,5vw,65px);letter-spacing:-.06em;line-height:1;margin:18px 0 14px}
.lead{color:#aeb9b4;max-width:700px}aside{background:#161d1c;border:1px solid #34413d;border-radius:9px;padding:16px;margin:23px 0}
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:23px 0}
input,select{background:#1b2222;color:#fff;border:1px solid #4c5954;padding:12px 13px;border-radius:7px}
input{min-width:240px;flex:1}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(285px,1fr));gap:12px}
.job{border:1px solid #323d39;background:#141919;border-radius:10px;padding:19px;display:flex;flex-direction:column;gap:10px}
.line{display:flex;justify-content:space-between;gap:10px;align-items:center}
.company{color:#d3f387;font-weight:700;font-size:13px}.score{font:12px ui-monospace,monospace;color:#adc7b8}
h3{font-size:20px;line-height:1.2;letter-spacing:-.025em;margin:2px 0}
.meta{font-size:12px;color:#aeb9b4;margin:0;min-height:35px}
.chip{border:1px solid #526b5e;border-radius:30px;font-size:11px;padding:4px 8px}
a{color:#d3f387;font-weight:700;text-decoration:none;font-size:12px}a:hover{text-decoration:underline}
.small{font-size:11px;color:#879590;margin:0}
a:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid #d3f387;outline-offset:2px}
[hidden]{display:none!important}footer{color:#8a9690;font-size:12px;margin-top:22px}
</style></head><body>
<header><div class="logo">◈ OPPORTUNITY / OS</div><span class="tiny">RADAR PERSONAL · SOLO AVISOS PÚBLICOS</span></header>
<main><div class="eyebrow">BÚSQUEDA + INVESTIGACIÓN GLOBAL</div>
<h1>Posibilidades<br>sin fronteras.</h1>
<p class="lead">Córdoba, remoto desde Argentina y empresas internacionales para investigar. Cada tarjeta conserva el aviso original: confirmá que siga vigente.</p>
<aside><strong id="count">0 oportunidades visibles</strong>
<p class="tiny">Generado: """ + escape(str(report.get("generated_at") or "sin fecha")) + """. Las listas son hallazgos de fuentes públicas, no vacantes verificadas. La categoría «Atlas global» no acredita elegibilidad laboral. No incluye CV, contactos ni historial privado.</p></aside>
<div class="controls"><input id="filter" type="search" placeholder="Empresa, Python, GIS, minería, ciudad..." aria-label="Buscar">
<select id="bucket" aria-label="Tipo de resultado"><option value="">Todas las categorías</option><option>Aplicables</option><option>Revisar</option><option>Atlas global</option></select></div>
<div id="jobs" class="grid">""" + "\n".join(cards) + """</div>
<p id="empty" class="lead" hidden>Sin coincidencias. Revisá filtros o ejecución de las fuentes.</p>
<footer>Opportunity OS · Datos obtenidos del pipeline real · Sin solicitudes a Gemini · Sin backend adicional para abrir este HTML.</footer>
</main><script>
const rows=[...document.querySelectorAll('.job')];
const input=document.getElementById('filter'), bucket=document.getElementById('bucket');
function refresh(){
 const q=input.value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim();
 let n=0;
 for(const row of rows){
  const text=row.dataset.search.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const visible=(!q||text.includes(q))&&(!bucket.value||row.dataset.bucket===bucket.value);
  row.hidden=!visible;if(visible)n++;
 }
 document.getElementById('count').textContent=n+' oportunidades visibles';
 document.getElementById('empty').hidden=n!==0;
}
input.addEventListener('input',refresh);bucket.addEventListener('change',refresh);refresh();
</script></body></html>"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(html, encoding="utf-8")
