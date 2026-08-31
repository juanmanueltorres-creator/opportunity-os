from __future__ import annotations

import re
import unicodedata

_DEFAULT_MAX_LENGTH = 120
_EXTENSION = ".pdf"
_PREFIX = "CV"


def build_cv_filename(
    candidate_name: str,
    role: str,
    company: str,
    *,
    max_length: int = _DEFAULT_MAX_LENGTH,
) -> str:
    if max_length <= len(_EXTENSION):
        raise ValueError("max_length must leave room for the PDF extension")

    tokens = [
        _candidate_name_token(candidate_name),
        _sanitize(role),
        _sanitize(company),
    ]
    payload = "_".join(token for token in tokens if token)
    stem = f"{_PREFIX}_{payload}" if payload else _PREFIX
    stem = re.sub(r"_+", "_", stem).strip("_")

    max_stem_length = max_length - len(_EXTENSION)
    stem = stem[:max_stem_length].rstrip("_") or _PREFIX[:max_stem_length]
    return f"{stem}{_EXTENSION}"


def _candidate_name_token(candidate_name: str) -> str:
    parts = candidate_name.split()
    if len(parts) >= 2:
        candidate_name = " ".join((parts[-1], *parts[:-1]))
    return _sanitize(candidate_name)


def _sanitize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value)
    return safe.strip("_")
