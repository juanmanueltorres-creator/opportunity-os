"""Protect the no-password public opportunity triage experience."""
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "site/index.html"


def test_browser_uses_private_server_endpoint_without_exposing_api_key():
    """Public workspace and clipboard briefing remain secret-free after UI changes."""
    html = HTML.read_text(encoding="utf-8")
    assert "function relevance(j)" in html
    assert "function renderCompanyDirectory()" in html
    assert "data-workspace-mode" in html
    assert "function preparePrompt(selected)" in html
    assert "function launchGemini(selected)" in html
    assert "navigator.clipboard.writeText" in html
    assert "https://gemini.google.com/app" in html
    assert 'id="briefText" readonly' in html

    # No browser-side API credentials, private review endpoint, or storage.
    assert "GEMINI_API_KEY" not in html
    assert "OPPORTUNITY_REVIEW_TOKEN" not in html
    assert "fetch('/api/review'" in html
    assert "credentials:'omit'" in html
    assert "ownerReviewToken" in html
    assert "geminiToken" not in html
    assert "sessionStorage.setItem" not in html
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
 work_language:'ES',listing_language:'ES',
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
if(rank(job('Data Developer',{company:'Muttdata',work_language:'UNKNOWN',listing_language:'EN'}))!==-Infinity)throw Error('English unknown listing should not be daily priority');
if(rank(job('Junior GIS Analyst',{work_language:'EN',listing_language:'ES'}))!==-Infinity)throw Error('English-required role leaked');
if(rank(job('Python Engineer',{work_language:'BILINGUAL',listing_language:'ES'}))!==-Infinity)throw Error('Bilingual role leaked');
if(!Number.isFinite(rank(job('Junior GIS Analyst',{work_language:'UNKNOWN',listing_language:'ES'}))))throw Error('Spanish provisional job excluded');
if(!Number.isFinite(rank(job('Data Developer',{company:'Muttdata'}))))throw Error('Muttdata excluded');
if(!Number.isFinite(rank(job('GIS Analyst',{company:'Local GIS'}))))throw Error('GIS excluded');
if(!Number.isFinite(rank(job('Junior Geologist',{company:'Local Geo'}))))throw Error('Geologist excluded');
if(!Number.isFinite(rank(job('Junior GIS Analyst',{argentina_eligible:'UNKNOWN',location:'Remote'}))))throw Error('junior GIS review wrongly excluded');
if(rank(job('GIS Analyst',{argentina_eligible:'UNKNOWN',location:'Remote'}))!==-Infinity)throw Error('unverified non-junior GIS leads should stay in atlas');
if(rank(job('Data Engineer',{company:'DSAC Chile',argentina_eligible:'UNKNOWN',location:'Remote'}))!==-Infinity)throw Error('Unverified generic role should stay out of shortlist');
if(!Number.isFinite(rank(job('Junior Software Engineer',{company:'Canals',argentina_eligible:'YES'}))))throw Error('Canals excluded');
console.log('shortlist semantic gates OK');
'''
    result = subprocess.run([node, "-e", program, str(HTML)], text=True,
                            capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_public_card_and_curated_lead_have_in_site_gemini_review_without_external_window():
    html = HTML.read_text(encoding="utf-8")
    assert "btnGemini.addEventListener('click',()=>openGeminiReview(j))" in html
    assert "id=\"reviewDialog\"" in html
    assert "payload.manual_job" in html
    assert "if(manual)payload.manual_job" in html
    assert "localStorage.setItem('ownerReviewToken'" not in html
    assert "Abrir postulación original" in html
