"""Metadata and deterministic social-card rendering for public players."""

from __future__ import annotations

import io
import os
from pathlib import Path

from flask import request
from PIL import Image, ImageDraw, ImageFont
from src.services.player_subject import PlayerSubject

_DEFAULT_PUBLIC_BASE_URL = "https://theacademywatch.com"
_CARD_SIZE = (1200, 630)
_FONT_DIRECTORIES = (
    Path(__file__).resolve().parents[2] / "fonts",
    Path("/usr/share/fonts/truetype/theacademywatch"),
)


def _find_font_path(*filenames: str) -> str | None:
    """Choose a bundled font, preserving directory precedence over family."""

    for directory in _FONT_DIRECTORIES:
        for filename in filenames:
            candidate = directory / filename
            if candidate.is_file():
                return str(candidate)
    return None


# Public on purpose: tests and deployment diagnostics can prove that a bundled
# font was selected instead of silently falling back to Pillow's default.
SHARE_CARD_FONT_PATH = _find_font_path(
    "Manrope-ExtraBold.ttf",
    "Inter-ExtraBold.ttf",
    "Manrope-Bold.ttf",
    "Inter-Bold.ttf",
    "Inter-Regular.ttf",
)
SHARE_CARD_BODY_FONT_PATH = _find_font_path(
    "Inter-Medium.ttf",
    "Inter-Regular.ttf",
    "Manrope-Bold.ttf",
)


def get_share_card_font_path() -> str | None:
    """Return the headline font path selected by the renderer."""

    return SHARE_CARD_FONT_PATH


def public_api_origin() -> str:
    """Return the configured API origin, or the request origin only in dev/tests."""

    configured = os.getenv("PUBLIC_API_BASE_URL")
    if configured is not None and configured.strip():
        return configured.rstrip("/")
    return request.url_root.rstrip("/")


def public_share_origin() -> str:
    """Return the configured public share origin, falling back to the API origin."""

    configured = os.getenv("PUBLIC_SHARE_BASE_URL")
    if configured is not None and (normalized := configured.strip().rstrip("/")):
        return normalized
    return public_api_origin()


def _public_origin() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or _DEFAULT_PUBLIC_BASE_URL).rstrip("/")


def _text(value) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _club_name(subject: PlayerSubject) -> str | None:
    if subject.local_player is not None and (club := _text(subject.local_player.club_name)):
        return club
    if subject.tracked_player is not None and (club := _text(subject.tracked_player.current_club_name)):
        return club
    if subject.shadow is not None and (club := _text(subject.shadow.current_club_name)):
        return club
    return None


def build_share_meta(subject: PlayerSubject) -> dict:
    """Build share and canonical URLs plus player-safe display metadata."""

    name = _text(subject.display_name) or "Player"
    position = _text(subject.position)
    club = _club_name(subject)
    description = " · ".join(part for part in (position, club) if part)

    if subject.signed_id < 0:
        local_id = subject.local_player_id or -subject.signed_id
        canonical_path = f"/local-players/{local_id}"
    else:
        canonical_path = f"/players/{subject.signed_id}"

    share_url = f"{public_share_origin()}/p/{subject.signed_id}"
    return {
        "title": f"{name} · The Academy Watch",
        "description": description,
        "canonical_url": f"{_public_origin()}{canonical_path}",
        "share_url": share_url,
        "image_url": f"{share_url}/card.png",
    }


def _font(size: int, path: str | None):
    if path:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> float:
    left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
    return right - left


def _fitted_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    path: str | None,
    start_size: int,
    minimum_size: int,
    max_width: int,
):
    for size in range(start_size, minimum_size - 1, -2):
        font = _font(size, path)
        if _text_width(draw, text, font) <= max_width:
            return text, font

    font = _font(minimum_size, path)
    shortened = text
    while shortened and _text_width(draw, f"{shortened}…", font) > max_width:
        shortened = shortened[:-1]
    return (f"{shortened.rstrip()}…" if shortened != text else text), font


def render_share_card(subject: PlayerSubject) -> io.BytesIO:
    """Render a seekable, deterministic 1200x630 PNG entirely in memory."""

    name = _text(subject.display_name) or "Player"
    position = _text(subject.position)
    club = _club_name(subject)
    source_label = "Community player" if subject.signed_id < 0 else "Tracked player"

    canvas = Image.new("RGB", _CARD_SIZE, "#050A1E")
    draw = ImageDraw.Draw(canvas)

    # Tactical Lens palette and layered geometry used by newsletter covers.
    draw.ellipse((-330, -230, 730, 830), fill="#0C1544")
    draw.polygon(((830, 0), (1200, 0), (1200, 630), (1030, 630)), fill="#101942")
    draw.rectangle((0, 574, 1200, 630), fill="#131C4E")
    draw.rounded_rectangle((72, 65, 318, 113), radius=24, fill="#2563EB")

    chip_font = _font(22, SHARE_CARD_BODY_FONT_PATH)
    brand_font = _font(25, SHARE_CARD_BODY_FONT_PATH)
    draw.text((94, 76), source_label, font=chip_font, fill="#FFFFFF")
    draw.text((72, 145), "The Academy Watch", font=brand_font, fill="#93C5FD")

    rendered_name, name_font = _fitted_text(
        draw,
        name,
        path=SHARE_CARD_FONT_PATH,
        start_size=82,
        minimum_size=48,
        max_width=1000,
    )
    draw.text((70, 211), rendered_name, font=name_font, fill="#F8FAFC")

    detail_y = 350
    if position:
        rendered_position, position_font = _fitted_text(
            draw,
            position,
            path=SHARE_CARD_BODY_FONT_PATH,
            start_size=40,
            minimum_size=28,
            max_width=940,
        )
        draw.text((74, detail_y), rendered_position, font=position_font, fill="#BFDBFE")
        detail_y += 70
    if club:
        rendered_club, club_font = _fitted_text(
            draw,
            club,
            path=SHARE_CARD_BODY_FONT_PATH,
            start_size=36,
            minimum_size=26,
            max_width=940,
        )
        draw.text((74, detail_y), rendered_club, font=club_font, fill="#CBD5E1")

    mark_font = _font(26, SHARE_CARD_FONT_PATH)
    draw.text((70, 588), "The Academy Watch", font=mark_font, fill="#FFFFFF")
    draw.ellipse((1083, 586, 1105, 608), fill="#3B82F6")
    draw.ellipse((1113, 586, 1135, 608), outline="#93C5FD", width=3)

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG", optimize=False, compress_level=9)
    buffer.seek(0)
    return buffer


__all__ = [
    "SHARE_CARD_BODY_FONT_PATH",
    "SHARE_CARD_FONT_PATH",
    "build_share_meta",
    "get_share_card_font_path",
    "public_api_origin",
    "public_share_origin",
    "render_share_card",
]
