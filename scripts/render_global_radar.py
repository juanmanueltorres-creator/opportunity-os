"""One self-contained public-only HTML radar: no API, secrets or build step.

The output is an offline snapshot of *job listings*, not private candidate data.
"""
from __future__ import annotations

import json


def render_global_radar(payload: dict) -> str:
    """Render the full public radar as one portable HTML file."""
    safe_data = json.dumps(
        {
            "generated_at": payload.get("generated_at"),
            "sources": payload.get("sources", {}),
            "raw_jobs_seen": payload.get("raw_jobs_seen", 0),
            "atlas": payload.get("atlas", []),
            "matches": payload.get("matches", []),
            "needs_review": payload.get("needs_review", []),
            "persistence": payload.get("persistence", {}),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    # JSON never crosses the HTML parser boundary, even with malicious job titles.
    safe_data = (
        safe_data.replace("<", r"\u003c").replace(">", r"\u003e")
        .replace("&", r"\u0026").replace("\u2028", r"\u2028")
        .replace("\u2029", r"\u2029")
    )
    page = """<!doctype html>
<html lang="es-AR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Opportunity OS / Radar Global</title>
<style>
:root{font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif;color:#f1f1eb;background:#0a0d0d}
*{box-sizing:border-box}body{margin:0}a{color:inherit}
header,main{max-width:1440px;padding:0 32px;margin:auto}
header{display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid #303534;padding-top:18px;padding-bottom:18px}
.brand{letter-spacing:-.025em;font-weight:850;font-size:17px}.brand i{color:#cbfc87;font-style:normal}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:11px;letter-spacing:.08em;color:#929e9a}
.hero{padding:53px 0 33px;display:flex;align-items:end;justify-content:space-between;gap:30px}
h1{font-size:clamp(44px,6.4vw,85px);line-height:.96;letter-spacing:-.075em;margin:14px 0 20px;max-width:780px}
h1 em{font-style:normal;color:#cbfc87}
.lead{font-size:15px;color:#a2aaa6;max-width:630px;line-height:1.6}
.cta{padding:12px 16px;border-radius:5px;border:1px solid #435348;text-decoration:none;white-space:nowrap;font-size:12px;color:#cbfc87}
.stats{display:grid;grid-template-columns:repeat(4,1fr);border:1px solid #363b39;margin:0 0 25px}
.stat{padding:21px 23px}.stat+.stat{border-left:1px solid #363b39}.stat strong{font-size:30px;display:block;line-height:1.5;letter-spacing:-.04em}
.stat span{font-family:ui-monospace,Consolas,monospace;color:#a7afab;font-size:10px;letter-spacing:.04em}
.grid{display:grid;grid-template-columns:235px 1fr;gap:24px;padding-bottom:65px}
aside{background:#141818;border:1px solid #303734;border-radius:10px;padding:18px;position:sticky;top:14px;height:fit-content}
aside h2{font-size:12px;text-transform:uppercase;letter-spacing:.08em;margin:0 0 20px}
label{display:block;color:#aab2ae;font-size:11px;margin:0 0 15px}
input,select{width:100%;padding:11px 10px;background:#0b0f0f;border:1px solid #36423b;border-radius:5px;color:#f3f6ef;font:13px system-ui,sans-serif;margin-top:7px;outline-offset:2px}
input:focus,select:focus{outline:1px solid #c3ed91}
.note{font-size:11px;color:#8d9993;line-height:1.6}
.feed-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:0 0 15px}
.feed-head h2{margin:0;font-size:18px;letter-spacing:-.04em}
.chips{display:flex;gap:7px;flex-wrap:wrap;margin:0 0 16px}
.chips button{border:1px solid #3b453e;border-radius:99px;background:#131918;color:#abb7af;padding:7px 12px;font:11px system-ui,sans-serif;cursor:pointer}
.chips button.active{background:#c8f18e;color:#11180c;border-color:#c8f18e;font-weight:750}
.card{border:1px solid #303938;background:#141918;border-radius:9px;margin-bottom:10px;padding:19px 21px}
.row{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.company{font-weight:750;color:#c8f18e;font-size:12px}
h3{margin:8px 0 13px;font-size:19px;letter-spacing:-.04em;line-height:1.3}
.tags{display:flex;gap:6px;flex-wrap:wrap}
.tag{font-size:10px;border:1px solid #3b4442;border-radius:3px;color:#b5c1b9;padding:4px 8px}
.tag.yes{border-color:#759f62;color:#c7f18c}.tag.no{border-color:#a36a4c;color:#e5ac81}
.bottom{border-top:1px solid #303938;margin-top:15px;padding-top:12px;display:flex;align-items:center;justify-content:space-between;gap:10px}
.bottom a{color:#c8f18e;font-weight:750;font-size:12px;text-decoration:none}
.bottom a:hover{text-decoration:underline}
.empty{border:1px dashed #424d45;border-radius:9px;padding:45px 25px;text-align:center;color:#b6c0b9}
.footer{font:11px/1.7 ui-monospace,monospace;color:#9fa9a1;border-top:1px solid #323b37;padding:22px 0 45px}
[hidden]{display:none!important}
@media(max-width:780px){header,main{padding-left:16px;padding-right:16px}.hero{display:block;padding-top:38px}.cta{display:inline-block;margin-bottom:12px}.stats{grid-template-columns:1fr 1fr}.stat:nth-child(3){border-left:0;border-top:1px solid #363b39}.stat:nth-child(4){border-top:1px solid #363b39}.grid{display:block}aside{position:static;margin-bottom:22px}.feed-head{align-items:start}h1{font-size:48px}}
</style>
</head>
<body>
<header><div class="brand">◈ OPPORTUNITY <i>/ OS</i></div><div class="mono">RADAR GLOBAL · VISTA OFFLINE</div></header>
<main>
<section class="hero"><div><div class="mono">FUENTES REALES · SIN POSTULACIONES AUTOMÁTICAS</div>
<h1>¿Dónde están<br>tus próximas <em>oportunidades?</em></h1>
<p class="lead">Explorá empresas de Argentina, LATAM, Estados Unidos y Europa. Separá los puestos para postularte desde Argentina de los que requieren verificar condiciones.</p>
</div><a class="cta" href="https://github.com/juanmanueltorres-creator/opportunity-os/actions/workflows/daily-opportunity-radar.yml" target="_blank" rel="noopener noreferrer">Abrir actualización diaria ↗</a></section>
<div class="stats" aria-label="Resumen">
<div class="stat"><strong id="total">—</strong><span>VACANTES DE INTERÉS</span></div>
<div class="stat"><strong id="applicable">—</strong><span>FILTRO ARGENTINA / CÓRDOBA</span></div>
<div class="stat"><strong id="review">—</strong><span>REQUIEREN VERIFICACIÓN</span></div>
<div class="stat"><strong id="sources">—</strong><span>FUENTES CONSULTADAS</span></div>
</div>
<div class="grid">
<aside><h2>Filtrar / 01</h2>
<label>Buscar empresa o puesto<input id="q" type="search" placeholder="GIS, Python, minería..." autocomplete="off"></label>
<label>Sector<select id="track">
<option value="">Todos</option>
<option value="software_ai">Software / Datos / IA</option><option value="gis_geoscience">GIS / Minería</option><option value="environment_agro">Agro / Ambiente / ESG</option>
<option value="management_operations">Gestión / Operaciones</option><option value="design_web">Diseño interactivo</option>
<option value="income_operations">Gastronomía / Abastecimiento</option></select></label>
<label>Modalidad<select id="mode"><option value="">Todas</option><option value="REMOTE">Remoto</option><option value="ONSITE">Presencial</option><option value="HYBRID">Híbrido</option><option value="UNKNOWN">No informada</option></select></label>
<label>Elegibilidad desde Argentina<select id="eligible"><option value="">Todas</option><option value="YES">Indicada por la fuente</option><option value="UNKNOWN">Sin confirmar</option><option value="NO">Restringida</option></select></label>
<label>Idioma explícito<select id="language"><option value="">Todos</option><option value="ES">Español</option><option value="EN">Inglés avanzado requerido</option><option value="UNKNOWN">No informado</option></select></label>
<label>Ubicación declarada<input id="location" type="search" placeholder="LATAM, Europe, USA..." autocomplete="off"></label>
<p class="note">Los filtros operan sobre esta captura del radar. La sede de una empresa no demuestra desde dónde contrata. Todas las vacantes requieren verificar vigencia y condiciones en el aviso original.</p>
</aside>
<section aria-label="Vacantes detectadas">
<div class="feed-head"><h2>Explorar oportunidades</h2><span class="mono" id="count">CARGANDO</span></div>
<div class="chips" id="chips">
<button type="button" data-lane="ALL">Todas</button>
<button type="button" data-lane="APPLICABLE">Para postular</button>
<button type="button" data-lane="REVIEW">A verificar</button>
<button type="button" data-lane="EXPLORE">Explorar empresas</button>
</div>
<div id="cards"></div><p class="note" id="limited"></p>
</section>
</div>
<div class="footer" id="footer">Cargando fuente...</div>
</main>
<script id="radar-data" type="application/json">__RADAR_JSON__</script>
<script>
(function(){
"use strict";
const data=JSON.parse(document.getElementById('radar-data').textContent);
const $=id=>document.getElementById(id);
const jobs=Array.isArray(data.atlas)?data.atlas:[];
const lanes={REMOTE_ARGENTINA:'APPLICABLE',CORDOBA_LOCAL:'APPLICABLE',REVIEW:'REVIEW',EXCLUDED:'EXPLORE'};
let currentLane='ALL';
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=String(text??'');if(cls)n.className=cls;return n;};
const label=(text,cls)=>el('span',text,'tag '+(cls||''));
const date=s=>{const d=s?new Date(s):null;return d&&!isNaN(d.getTime())?new Intl.DateTimeFormat('es-AR',{day:'2-digit',month:'short',year:'numeric'}).format(d):'Fecha no informada';};
const url=s=>{try{const u=new URL(s);return u.protocol==='https:'?u.href:null;}catch{return null;}};
const row=j=>{
 const card=el('article',undefined,'card'), top=el('div',undefined,'row'), head=el('div'), tags=el('div',undefined,'tags'),bottom=el('div',undefined,'bottom');
 top.append(el('span',j.company,'company'),el('span',date(j.published_at||j.discovered_at),'mono'));
 head.append(el('h3',j.title));
 const lane=lanes[j.search_lane]||'EXPLORE';
 const status=lane==='APPLICABLE'?'ELEGIBILIDAD INDICADA':lane==='REVIEW'?'VERIFICAR PAÍS / MODALIDAD':'EXPLORACIÓN / NO APLICABLE';
 tags.append(label(status,lane==='APPLICABLE'?'yes':lane==='EXPLORE'?'no':''),label(j.location||'Ubicación sin informar'),
    label(j.remote_mode||'UNKNOWN'),label(j.track.replaceAll('_',' ')),label('Afinidad '+j.score+'/100'));
 const note=el('span',(j.source||'Fuente pública')+' · Vigencia pendiente de verificación','mono');
 bottom.append(note);
 const target=url(j.source_url);
 if(target){const link=el('a','Ver aviso original ↗');link.href=target;link.target='_blank';link.rel='noopener noreferrer';bottom.append(link);}
 card.append(top,head,tags,bottom);return card;
};
function render(){
 const q=$('q').value.trim().toLowerCase(),location=$('location').value.trim().toLowerCase();
 const track=$('track').value,mode=$('mode').value,eligible=$('eligible').value,language=$('language').value;
 const found=jobs.filter(j=>{
 if(currentLane!=='ALL'&&(lanes[j.search_lane]||'EXPLORE')!==currentLane)return false;
 if(q&&!((j.company||'')+' '+(j.title||'')).toLowerCase().includes(q))return false;
 if(location&&!(j.location||'').toLowerCase().includes(location))return false;
 if(track&&j.track!==track)return false;
 if(mode&&j.remote_mode!==mode)return false;
 if(eligible&&j.argentina_eligible!==eligible)return false;
 if(language&&j.work_language!==language)return false;
 return true;
 });
 $('count').textContent=found.length+' resultados';
 const parent=$('cards');parent.replaceChildren();
 if(!found.length)parent.append(el('div','Sin coincidencias. Probá cambiar los filtros o elegí «Todas».','empty'));
 found.sort((a,b)=>({APPLICABLE:0,REVIEW:1,EXPLORE:2}[lanes[a.search_lane]||'EXPLORE']-({APPLICABLE:0,REVIEW:1,EXPLORE:2}[lanes[b.search_lane]||'EXPLORE'])) || b.score-a.score);
 found.slice(0,100).forEach(j=>parent.append(row(j)));
 $('limited').textContent=found.length>100?'Mostrando los primeros 100 resultados de esta selección. Afiná los filtros para explorar el resto.':'';
 document.querySelectorAll('[data-lane]').forEach(b=>{b.classList.toggle('active',b.dataset.lane===currentLane);b.setAttribute('aria-pressed',b.dataset.lane===currentLane?'true':'false');});
}
$('total').textContent=jobs.length;
$('applicable').textContent=jobs.filter(j=>lanes[j.search_lane]==='APPLICABLE').length;
$('review').textContent=jobs.filter(j=>lanes[j.search_lane]==='REVIEW').length;
$('sources').textContent=Object.keys(data.sources||{}).length;
const generated=data.generated_at?date(data.generated_at):'sin fecha';
$('footer').textContent='Actualizado: '+generated+' · Captura pública, no representa la totalidad del mercado · Sin datos personales ni CV · Persistencia en Supabase: '+(data.persistence?.status||'desconocida')+'.';
['q','location','track','mode','eligible','language'].forEach(id=>$(id).addEventListener('input',render));
document.querySelectorAll('[data-lane]').forEach(b=>b.addEventListener('click',()=>{currentLane=b.dataset.lane;render();}));
render();
})();
</script>
</body>
</html>
"""
    return page.replace("__RADAR_JSON__", safe_data)
