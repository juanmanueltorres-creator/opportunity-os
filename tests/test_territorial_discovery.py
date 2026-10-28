"""Nationwide discovery is intentionally separate from apply-now eligibility."""
from datetime import datetime, timezone
import shutil
import subprocess
from pathlib import Path

import pytest
from app.models.domain import Opportunity
from app.radar.daily_search import classify, rank
from app.radar.territorial_discovery import (
    discovery_lane, geographic_context, thematic_tags,
)

NOW = datetime(2026, 10, 28, 16, tzinfo=timezone.utc)


def vacancy(title="Geólogo de exploración minera", place="Salta, Argentina", mode="onsite"):
    return Opportunity(
        id="test:salta", source="greenhouse", source_id="salta",
        company="Exploración S.A.", title=title,
        source_url="https://example.com/jobs/geo",
        description="Prospección geológica, control de datos y campañas de perforación.",
        location=place, remote_policy=mode,
        discovered_at=NOW, published_at=NOW,
    )


@pytest.mark.parametrize("place,province", [
    ("Salta, Argentina", "Salta"),
    ("San Juan", "San Juan"),
    ("Jujuy", "Jujuy"),
    ("Neuquén, Argentina", "Neuquén"),
    ("Añelo, Vaca Muerta", "Neuquén"),
    ("Comodoro Rivadavia", "Chubut"),
    ("Buenos Aires, Argentina", "Buenos Aires"),
])
def test_national_province_evidence(place, province):
    assert geographic_context(place) == ("ARGENTINA", province)


def test_no_invented_geography_and_foreign_cordoba():
    assert geographic_context("Córdoba, Spain") == ("INTERNATIONAL", None)
    assert geographic_context("Remote LATAM") == ("LATAM", None)
    assert geographic_context("Remote Worldwide") == ("GLOBAL_UNSPECIFIED", None)
    assert geographic_context("Kansas City") == ("UNKNOWN", None)
    assert geographic_context(None) == ("UNKNOWN", None)


def test_relocation_remains_visible_without_claiming_remote_eligibility():
    item = classify(vacancy(), include_worldwide_onsite=True)
    assert item is not None
    assert item.remote_mode == "ONSITE"
    assert discovery_lane(item) == "ARGENTINA_RELOCATION"
    assert item.argentina_eligible == "UNKNOWN" or item.argentina_eligible == "YES"
    # In the CURRENT apply-now policy, relocation does not silently become a
    # remotely eligible job or a privately persisted application.
    assert rank([vacancy()], now=NOW) == []
    assert len(rank([vacancy()], now=NOW, include_worldwide_onsite=True)) == 1


def test_foreign_relocation_not_claimed_eligible():
    item = classify(vacancy(place="Berlin, Germany"), include_worldwide_onsite=True)
    assert item is not None
    assert discovery_lane(item) == "RELOCATION_REVIEW"
    assert item.argentina_eligible == "NO"


def test_keyword_topic_multilabel_no_description_hallucinations():
    assert thematic_tags("GIS Python Developer") == ["gis", "software_data"]
    assert "technical_business" in thematic_tags("Business Development Manager - Mining Tech")
    assert "mining_tech" in thematic_tags("Business Development Manager - Mining Tech")
    assert "geology_mining" in thematic_tags("Business Development Manager - Mining Tech")
    assert thematic_tags("Project Manager", "agtech") == ["agro"]
    assert thematic_tags("Project Manager") == []
    assert thematic_tags("Registered Nurse") == []


def test_static_site_has_non_exclusionary_controls_and_valid_js(tmp_path):
    page = Path(__file__).resolve().parents[1] / "site" / "index.html"
    html = page.read_text(encoding="utf-8")
    assert 'data-lane="ARGENTINA_RELOCATION"' in html
    assert 'data-topic="gis"' in html
    assert 'data-topic="technical_business"' in html
    assert 'id="territoryBars"' in html
    assert 'id="age"' in html
    assert "Computrabajo · Geología" in html
    assert "trabajo-de-geologo-en-cordoba" not in html
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed in test environment")
    script = html.split("<script>", 1)[1].split("</script>", 1)[0]
    jsfile = tmp_path / "dashboard.js"
    jsfile.write_text(script, encoding="utf-8")
    result = subprocess.run([node, "--check", str(jsfile)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
