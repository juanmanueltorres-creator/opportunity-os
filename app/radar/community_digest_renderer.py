from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.radar.community_digest import CommunityDigest, CommunityDigestItem


DigestRenderFormat = Literal["whatsapp", "markdown"]

_BUCKET_LABELS = {
    "FREELANCE": ("📑", "Freelance"),
    "ENTRY_LEVEL": ("🌱", "Primera experiencia"),
    "GEOSCIENCE_MINING": ("⛏️", "Geociencias / Minería"),
    "GEOAI_DATA": ("🧠", "GeoAI / Data"),
    "GEO_CORE": ("🗺️", "GIS / Geoespacial"),
    "SENIOR": ("🧭", "Senior"),
    "GENERAL": ("🔎", "Oportunidad"),
}


@dataclass(frozen=True)
class CommunityDigestRenderOptions:
    title: str = "Oportunidades y proyectos — Equipo Geoespacial"
    timezone_name: str = "UTC"
    include_intro: bool = True
    include_footer: bool = True
    format: DigestRenderFormat = "whatsapp"

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be blank")
        if self.format not in {"whatsapp", "markdown"}:
            raise ValueError("unsupported digest render format")
        try:
            ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("unknown timezone_name") from exc


def render_community_digest(
    digest: CommunityDigest,
    *,
    options: CommunityDigestRenderOptions | None = None,
) -> str:
    resolved = options or CommunityDigestRenderOptions()
    timezone = ZoneInfo(resolved.timezone_name)
    local_generated_at = digest.generated_at.astimezone(timezone)

    lines: list[str] = [
        f"🚀 *{resolved.title} | {local_generated_at:%d/%m}*"
        if resolved.format == "whatsapp"
        else f"# 🚀 {resolved.title} | {local_generated_at:%d/%m}",
    ]

    if resolved.include_intro:
        lines.extend(
            [
                "",
                (
                    "Ronda verificada con oportunidades de distintas puertas de entrada. "
                    "La selección prioriza frescura, calidad de fuente y datos accionables."
                ),
            ]
        )

    for index, item in enumerate(digest.items, start=1):
        lines.extend(["", *_render_item(index, item, timezone, resolved.format)])

    if not digest.items:
        lines.extend(
            [
                "",
                "No hay oportunidades suficientemente verificadas para publicar en esta ronda.",
            ]
        )

    if resolved.include_footer:
        lines.extend(
            [
                "",
                (
                    "🔎 Si conocen otra plataforma, convocatoria o proyecto concreto, "
                    "compártanlo y lo sumamos al radar."
                ),
            ]
        )

    return "\n".join(lines).strip() + "\n"


def _render_item(
    index: int,
    item: CommunityDigestItem,
    timezone: ZoneInfo,
    render_format: DigestRenderFormat,
) -> list[str]:
    emoji, bucket_label = _BUCKET_LABELS[item.bucket]
    safe_title = _safe_inline_text(item.title)
    heading = f"{_number_marker(index)} {emoji} {bucket_label} — {safe_title}"
    if render_format == "whatsapp":
        heading = f"*{heading}*"
    elif render_format == "markdown":
        heading = f"## {heading}"

    lines = [heading]

    company = _safe_inline_text(item.company)
    if company:
        lines.append(f"🏢 {company}")

    place = _place_line(item)
    if place is not None:
        lines.append(place)

    source = _source_label(item.source_url)
    if source is not None:
        lines.append(f"📍 {source}")

    if item.application_deadline is not None:
        # Extracted application deadlines are calendar-date semantics encoded as
        # aware datetimes. Do not shift the stated date through a display timezone.
        lines.append(f"📅 Cierre: {item.application_deadline:%d/%m/%Y}")

    if (
        item.availability_state == "VERIFIED_OPEN"
        and item.last_verified_at is not None
        and item.verification_source is not None
    ):
        verified_at = item.last_verified_at.astimezone(timezone)
        lines.append(
            "✅ Verificada abierta: "
            f"{_safe_inline_text(item.verification_source)} · "
            f"{verified_at:%d/%m/%Y}"
        )

    lines.append(item.source_url)
    return lines


def _safe_inline_text(value: str) -> str:
    normalized = " ".join(value.split())
    controls = str.maketrans(
        {
            "*": "∗",
            "_": "＿",
            "~": "∼",
            "`": "ˋ",
            "[": "［",
            "]": "］",
        }
    )
    return normalized.translate(controls).strip()


def _place_line(item: CommunityDigestItem) -> str | None:
    location = _safe_inline_text(item.location or "")
    remote_policy = _safe_inline_text(item.remote_policy or "")

    if remote_policy and location:
        return f"🌎 {remote_policy} · {location}"
    if remote_policy:
        return f"🌎 {remote_policy}"
    if location:
        return f"📌 {location}"
    return None


def _source_label(source_url: str) -> str | None:
    try:
        host = (urlsplit(source_url).hostname or "").casefold()
    except ValueError:
        return None
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None

    known = {
        "workana.com": "Workana",
        "freelancer.com": "Freelancer",
        "freelancer.com.ar": "Freelancer",
        "cadcrowd.com": "Cad Crowd",
        "getonbrd.com": "Get on Board",
        "getonbrd.cl": "Get on Board",
        "geo-careers.com": "GEO Careers",
        "spatialnode.net": "Spatialnode",
        "earthworks-jobs.com": "Earthworks",
        "climatebase.org": "Climatebase",
        "terra.do": "Terra.do",
        "linkedin.com": "LinkedIn",
        "indeed.com": "Indeed",
        "indeed.com.ar": "Indeed",
        "computrabajo.com": "Computrabajo",
        "computrabajo.com.ar": "Computrabajo",
    }
    return known.get(host, host)


def _number_marker(index: int) -> str:
    emoji_digits = {
        1: "1️⃣",
        2: "2️⃣",
        3: "3️⃣",
        4: "4️⃣",
        5: "5️⃣",
        6: "6️⃣",
        7: "7️⃣",
        8: "8️⃣",
        9: "9️⃣",
        10: "🔟",
    }
    return emoji_digits.get(index, f"{index}.")
