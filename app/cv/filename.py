from __future__ import annotations

import re
import unicodedata

_DEFAULT_MAX_LENGTH = 120
_EXTENSION = ".pdf"


def build_cv_filename(
    candidate_name: str,
    role: str,
    company: str,
    *,
    max_length: int = _DEFAULT_MAX_LENGTH,
) -> str:
    if max_length <= len(_EXTENSION):
        raise ValueError("max_length must leave room for the PDF extension")

    tokens = [_sanitize(part) for part in (candidate_name, role, company)]
    stem = "_".join(token for token in tokens if token)
    stem = re.sub(r"_+", "_", stem).strip("_") or "CV"

    max_stem_length = max_length - len(_EXTENSION)
    stem = stem[:max_stem_length].rstrip("_") or "CV"
    return f"{stem}{_EXTENSION}"


def _sanitize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    safe = re.sub(r"[^A-Za-z0-9]+", "_", ascii_value)
    return safe.strip("_")
