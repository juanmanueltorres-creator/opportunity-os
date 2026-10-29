"""Contract for browser-only printable CV without server access to private facts."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_cv_editor_is_available_from_jobs_without_external_upload():
    html = (ROOT / "site/index.html").read_text(encoding="utf8")
    code = (ROOT / "site/cv-workspace.js").read_text(encoding="utf8")
    assert "Preparar CV" in html
    assert "Guardar PDF (Imprimir)" in code
    assert "@media print" in html
    assert 'src="./cv-workspace.js"' in html
    assert "root.localStorage.setItem(STORAGE" in code
    assert "root.localStorage.removeItem(STORAGE" in code
    assert "fetch(" not in code
    assert "XMLHttpRequest" not in code


def test_node_cv_workspace():
    node=shutil.which("node")
    if not node:
        return
    script=ROOT / "tests/test_cv_workspace.mjs"
    result=subprocess.run([node,"--test",str(script)],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
