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
    assert "Preparar estas 5 para Gemini" in html
    assert "function relevance(j)" in html
    assert "function renderToday()" in html
    assert "function preparePrompt(selected)" in html
    assert "status(j)==='applied'" in html
    assert "status(j)==='ignored'" in html
    assert "j.argentina_eligible==='NO'" in html
    assert "source_check==='LISTED_ON_PUBLIC_ATS'" in html
    assert "sort((a,b)=>b.rank-a.rank" in html
    assert ".slice(0,5)" in html
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
