from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def test_browser_rank_uses_profile_first_priority_without_new_ui():
    html = (ROOT / "site/index.html").read_text(encoding="utf-8")
    assert "CompanyDirectory.immediatePriority(b)-CompanyDirectory.immediatePriority(a)" in html
    node = shutil.which("node")
    if node:
        result = subprocess.run(
            [node, "--test", str(ROOT / "tests/test_company_directory.mjs")],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0, result.stderr + result.stdout
