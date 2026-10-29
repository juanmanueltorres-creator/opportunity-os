"""Offline safety tests for the owner-only Vercel Gemini review endpoint."""
from __future__ import annotations

import base64
import importlib.util
import io
import json
from email.message import Message
from pathlib import Path
import subprocess
import shutil

import pytest

MODULE = Path(__file__).resolve().parents[1] / "site/api/review.py"
spec = importlib.util.spec_from_file_location("private_gemini_review", MODULE)
assert spec and spec.loader
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def test_private_review_is_disabled_without_config_and_wrong_token(monkeypatch):
    for name in ("OPPORTUNITY_GEMINI_ENABLED", "GEMINI_FREE_TIER_CONFIRMED",
                 "GEMINI_API_KEY", "OPPORTUNITY_REVIEW_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    assert review.configured() is False
    assert review.authorized(None) is False
    monkeypatch.setenv("OPPORTUNITY_GEMINI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-model-key-please-do-not-use")
    monkeypatch.setenv("OPPORTUNITY_REVIEW_TOKEN", "random-example-private-owner-token-" + "x"*25)
    assert review.configured() is True
    assert review.authorized("Bearer wrong") is False
    assert review.authorized("Bearer random-example-private-owner-token-" + "x"*25) is True
    assert review.authorized("Basic random-example-private-owner-token-" + "x"*25) is False


def test_payload_validation_and_no_mass_review():
    assert review.decode_request(b'{"opportunity_id":"ashby:123"}')["opportunity_id"] == "ashby:123"
    with pytest.raises(ValueError):
        review.decode_request(b'{"opportunity_id":"x","job_title":"fabricated"}')
    with pytest.raises(ValueError):
        review.decode_request(b'{"opportunity_id":"ashby:123","candidate_context":' +
                              json.dumps("a"*1501).encode() + b'}')
    with pytest.raises(ValueError):
        review.decode_request(b'{"opportunity_id":"ashby:123","posting_text":' +
                              json.dumps("x"*6001).encode() + b'}')
    with pytest.raises(ValueError):
        review.decode_request(b"not-json")
    with pytest.raises(ValueError):
        review.decode_request(b'{"opportunity_id":"ashby:1"}' + b" " * 9000)


def test_review_forces_unknown_fit_without_profile():
    answer = {"fit": "alto", "recommendation": "postular",
              "summary": "Parece bueno", "strengths": ["Python"],
              "gaps": ["Inglés"], "caveat": "Validar"}
    out = review.normalize_review(answer, has_context=False)
    assert out["fit"] == "indeterminado"
    assert out["recommendation"] == "revisar"
    assert out["verification"] == "ORIENTATIVE_ONLY_NOT_LIVE_OPENING_CONFIRMATION"
    assert review.normalize_review(answer, has_context=True)["fit"] == "alto"
    with pytest.raises(ValueError):
        review.normalize_review({**answer, "recommendation": "enviar CV automáticamente"}, has_context=True)


def test_only_job_ids_from_current_public_feed_are_accepted(monkeypatch):
    captured = []
    atlas = {"schema_version": 1, "atlas": [
        {"id": "ashby:job1", "company": "Empresa", "title": "GIS",
         "source_url": "https://jobs.ashbyhq.com/company/job1",
         "private_note": "never export"},
    ]}
    raw = json.dumps(atlas).encode()
    def fake_fetch(url, **kwargs):
        captured.append((url,kwargs))
        return {"path": "jobs.json", "encoding": "base64", "size": len(raw),
                "content": base64.b64encode(raw).decode()}
    monkeypatch.setattr(review, "_read_json", fake_fetch)
    job = review.get_public_job("ashby:job1")
    assert job and job["title"] == "GIS"
    assert "private_note" not in job
    assert review.get_public_job("ashby:does-not-exist") is None
    assert captured[0][0] == review.FEED
    assert "api.github.com" in captured[0][0]
    assert all(c[0] == review.FEED for c in captured)


def test_html_does_not_store_owner_token_and_csp_allows_only_same_origin():
    html = (MODULE.parents[1] / "index.html").read_text()
    config = json.loads((MODULE.parents[1] / "vercel.json").read_text())
    csp = config["headers"][0]["headers"][-1]["value"]
    assert "connect-src 'self' https://raw.githubusercontent.com" in csp
    assert "sessionStorage.setItem" not in html
    assert "ownerReviewToken" in html
    assert "credentials:'omit'" in html
    assert "Gemini" in html
    node = shutil.which("node")
    if node:
        script = html.split("<script>",1)[1].split("</script>",1)[0]
        result = subprocess.run([node,"--check","-"],input=script,capture_output=True,text=True)
        assert result.returncode==0,result.stderr

def test_unknown_work_language_never_recommends_unverified_application(monkeypatch):
    job = {"id": "ashby:job1", "company": "Test", "title": "GIS Jr",
           "work_language": "UNKNOWN", "argentina_eligible": "YES"}
    model = {"candidates": [{"content": {"parts": [{"text": json.dumps({
        "fit": "alto", "recommendation": "postular", "summary": "Se ve bien",
        "strengths": ["Python"], "gaps": [], "caveat": "Confirmar"
    })}]}}]}
    class Fake:
        def __init__(self, raw): self.raw = raw
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, n): return self.raw
    monkeypatch.setenv("GEMINI_API_KEY", "fake-test-key")
    monkeypatch.setattr(review, "urlopen", lambda *a, **kw: Fake(json.dumps(model).encode()))
    result = review.ask_gemini(job, "Requisitos de puesto", "Experiencia verificable")
    assert result["recommendation"] == "revisar"
