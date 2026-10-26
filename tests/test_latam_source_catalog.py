from pathlib import Path

from app.radar.source_catalog import load_source_catalog


CATALOG = Path(__file__).resolve().parents[1] / "config" / "source_catalog.yaml"


def test_latam_source_catalog_expansion_has_valid_entries() -> None:
    catalog = load_source_catalog(CATALOG)
    expected = {
        "startupjobs_ar",
        "startupjobs_cl",
        "startupjobs_mx",
        "derecruiters",
        "remotos_latam",
        "alerta_empleo_remoto",
        "cordoba_startup_monitor",
        "innovab_cordoba",
        "cordoba_cluster",
        "unc_geologia",
        "geodojo",
        "geoinquietos_ar",
        "frontendcafe",
        "devschile",
        "cuti_uruguay",
        "uruguay_xxi",
        "ycombinator_jobs",
    }
    actual = {entry.key for entry in catalog.sources}
    assert expected <= actual
    assert catalog.resolve("startupjobs.ar").key == "startupjobs_ar"
    assert catalog.resolve("unknown", "https://www.startupjobs.mx/empleos").key == "startupjobs_mx"


def test_discovery_only_sources_cannot_be_published_as_verified_jobs() -> None:
    catalog = load_source_catalog(CATALOG)
    discovery = {
        "startupjobs_ar",
        "startupjobs_cl",
        "startupjobs_mx",
        "remotos_latam",
        "alerta_empleo_remoto",
        "cordoba_startup_monitor",
        "innovab_cordoba",
        "cordoba_cluster",
        "geodojo",
        "geoinquietos_ar",
        "frontendcafe",
        "devschile",
        "cuti_uruguay",
        "uruguay_xxi",
    }
    for key in discovery:
        item = catalog.resolve(key)
        assert item is not None
        assert item.authority == "DISCOVERY_ONLY"
        assert item.publishable is False
        assert item.verification_required is True


def test_official_university_listing_still_requires_freshness_check() -> None:
    item = load_source_catalog(CATALOG).resolve("unc_geologia")
    assert item is not None
    assert item.authority == "DIRECT_OFFICIAL"
    assert item.verification_required is True
