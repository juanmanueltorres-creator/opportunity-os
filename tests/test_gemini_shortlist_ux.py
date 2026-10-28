"""Protect the no-password public opportunity triage experience."""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "site/index.html"


def test_public_gemini_briefing_has_no_private_password_or_api_call():
    html = HTML.read_text(encoding="utf-8")
    assert 'id="todayJobs"' in html
    assert "Preparar selección para Gemini" in html
    assert "function relevance(j)" in html
    assert "function renderToday()" in html
    assert "function preparePrompt(selected)" in html
    assert "status(j)==='applied'" in html
    assert "status(j)==='ignored'" in html
    assert "j.argentina_eligible==='NO'" in html
    assert "source_check==='LISTED_ON_PUBLIC_ATS'" in html
    assert "sort((a,b)=>b.rank-a.rank" in html
    assert "if(candidates.length===5)break" in html
    assert "if((byCompany.get(company)||0)>=2)continue" in html
    assert "const advanced=" not in html
    assert "function relevance(j)" in html
    assert "const junior=" in html
    assert "talent pool" in html
    assert "liferay|snowflake" in html
    assert "senior|senior-level" in html
    assert "Sin ofertas con ubicación y requisitos suficientes" not in html

    assert "https://gemini.google.com/app" in html
    assert "navigator.clipboard.writeText" in html
    assert "function launchGemini(selected)" in html
    assert "window.open('https://gemini.google.com/app'" in html
    assert 'id="briefText" readonly' in html
    assert "geminiToken" not in html
    assert "geminiDialog" not in html
    assert "OPPORTUNITY_REVIEW_TOKEN" not in html
    assert "/api/review" not in html
    assert not (ROOT / "site/api/review.py").exists()


def test_browser_script_and_csp_remain_valid():
    html = HTML.read_text(encoding="utf-8")
    cfg = json.loads((ROOT / "site/vercel.json").read_text(encoding="utf-8"))
    csp = next(h["value"] for h in cfg["headers"][0]["headers"]
               if h["key"] == "Content-Security-Policy")
    assert "connect-src https://raw.githubusercontent.com;" in csp
    assert "connect-src 'self'" not in csp
    node = shutil.which("node")
    if node:
        script = html.split("<script>", 1)[1].split("</script>", 1)[0]
        result = subprocess.run([node, "--check", "-"], input=script,
                                text=True, capture_output=True)
        assert result.returncode == 0, result.stderr


def test_shortlist_rejects_pool_senior_irrelevant_and_ranks_junior_first():
    """Execute real JS relevance policy rather than merely matching strings."""
    node = shutil.which("node")
    if not node:
        return
    program = r'''
const fs=require('fs');
const vm=require('vm');
const html=fs.readFileSync(process.argv[1],'utf8');
const start=html.indexOf('function relevance(j){');
const end=html.indexOf('function preparePrompt(selected){',start);
if(start===-1 || end<=start)throw Error('policy function missing');
const code=html.slice(start,end);
const context={
  status:()=> 'new',
  safeUrl:(u)=>{try{const x=new URL(u);return x.protocol==='https:'?u:null}catch{return null}},
  group:(j)=>j.argentina_eligible==='YES'?'APPLICABLE':'REVIEW',
  norm:(t)=>String(t||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase(),
  Date:Date, Math:Math, Number:Number
};
vm.createContext(context);vm.runInContext(code,context);
const job=(title,extra={})=>({
 id:'ashby:test',title,company:'Example',
 source_url:'https://jobs.ashbyhq.com/test/123',
 argentina_eligible:'YES',search_lane:'REMOTE_ARGENTINA',
 score:65,location:'Argentina',remote_mode:'REMOTE',
 source_check:'LISTED_ON_PUBLIC_ATS',
 published_at:'2026-10-26T12:00:00Z',...extra
});
const rank=context.relevance;
const junior=rank(job('Junior Software Engineer'));
const data=rank(job('Data Engineer'));
if(!(junior>data))throw Error('Junior should outrank generic data engineer');
for(const title of ['Backend Developer - G2i Talent Pool','Senior Geospatial Software Engineer',
'Full-Stack Liferay Developer','Snowflake Data Engineer','Billing & Refunds Coordinator',
'Principal Python Engineer','Senior GIS Analyst']){
 if(rank(job(title))!==-Infinity)throw Error('Bad role leaked: '+title);
}
if(rank(job('Python Developer', {location:'Washington, DC',argentina_eligible:'UNKNOWN'}))!==-Infinity)throw Error('US unknown allowed');
if(!Number.isFinite(rank(job('Data Developer',{company:'Muttdata'}))))throw Error('Muttdata excluded');
if(!Number.isFinite(rank(job('GIS Analyst',{company:'Local GIS'}))))throw Error('GIS excluded');
if(!Number.isFinite(rank(job('Junior GIS Analyst',{argentina_eligible:'UNKNOWN',location:'Remote'}))))throw Error('junior GIS review wrongly excluded');
if(rank(job('GIS Analyst',{argentina_eligible:'UNKNOWN',location:'Remote'}))!==-Infinity)throw Error('unverified non-junior GIS leads should stay in atlas');
if(rank(job('Data Engineer',{company:'DSAC Chile',argentina_eligible:'UNKNOWN',location:'Remote'}))!==-Infinity)throw Error('Unverified generic role should stay out of shortlist');
if(!Number.isFinite(rank(job('Junior Software Engineer',{company:'Canals',argentina_eligible:'YES'}))))throw Error('Canals excluded');
console.log('shortlist semantic gates OK');
'''
    result = subprocess.run([node, "-e", program, str(HTML)], text=True,
                            capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
