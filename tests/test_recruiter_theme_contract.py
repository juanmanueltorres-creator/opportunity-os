from pathlib import Path

import yaml


def test_recruiter_theme_keeps_debug_notes_and_footer_disabled():
    design = yaml.safe_load(
        Path("config/rendercv_one_page.yaml").read_text(encoding="utf-8")
    )["design"]

    assert design["page"]["show_footer"] is False
    assert design["page"]["show_top_note"] is False
