from importlib import import_module

import pytest


def _profiles():
    return import_module("app.profiles")


def test_load_profile_from_valid_yaml(tmp_path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(
        """
name: Example Candidate
roles:
  - GIS Developer
skills:
  - python
  - postgis
domains:
  - gis
locations:
  - Argentina
remote_preferences:
  - remote
evidence:
  - label: GIS project
    type: project
    skills: [python, postgis]
    domains: [gis]
    verified: true
""".strip(),
        encoding="utf-8",
    )

    profile = _profiles().load_profile(path)

    assert profile.name == "Example Candidate"
    assert profile.skills == ["python", "postgis"]
    assert profile.evidence[0].verified is True


def test_invalid_profile_raises_safe_value_error(tmp_path) -> None:
    path = tmp_path / "profile.yaml"
    raw = "name: Example Candidate\nsecret_note: do-not-leak\n"
    path.write_text(raw, encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        _profiles().load_profile(path)

    message = str(exc_info.value)
    assert "Invalid candidate profile" in message
    assert "do-not-leak" not in message


def test_malformed_yaml_does_not_expose_raw_contents(tmp_path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text("name: [private-value", encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        _profiles().load_profile(path)

    assert "private-value" not in str(exc_info.value)
