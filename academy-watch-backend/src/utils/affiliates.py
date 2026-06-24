"""Resolve a club's reserve / youth / B side to its senior parent organisation.

Used by the player-status classifier so a player at their parent academy's OWN
B / reserve / youth team (e.g. Jong Ajax for Ajax, Atalanta U20 for Atalanta,
Birmingham City U21 for Birmingham) is treated as STILL at the parent — not as
having "left". Without this guard, those players have no departure transfer and
fall through to the "left" default (the configuration the model otherwise gets
right).

Two layers, by design (the user chose data-driven + hardcoded fallback):
  1. DATA-DRIVEN name normalisation — strip a leading "Jong " and trailing
     reserve / youth suffixes (incl. any U-number, III, C, Castilla), then
     compare base names. Works whenever the club name is available, and (unlike
     academy_classifier.strip_youth_suffix) catches U20/U16/Jong/III.
  2. HARDCODED api_id -> senior api_id fallback for ids whose name is not
     loaded (the teams row is absent so the name is NULL) or does not normalise
     to the parent's name (e.g. "RSC Anderlecht II" vs parent "Anderlecht").

This module is intentionally dependency-free (no import from academy_classifier)
to avoid a circular import — academy_classifier imports THIS module.
"""

import re

# ── data-driven name normalisation ─────────────────────────────────────
_JONG_PREFIX = re.compile(r"^jong\s+", re.IGNORECASE)
_RESERVE_SUFFIX = re.compile(
    r"\s+(?:U\d{1,2}|Under[\s-]?\d+|Sub[\s-]?\d+|II|III|IV|B|C|Castilla|Youth|Academy|Reserves?|Development|Bis)\b\.?$",
    re.IGNORECASE,
)


def senior_base_name(name: str | None) -> str:
    """Strip a 'Jong ' prefix and any trailing reserve/youth suffixes to get
    the senior club's base name.

    >>> senior_base_name('Jong Ajax')
    'Ajax'
    >>> senior_base_name('Atalanta U20')
    'Atalanta'
    >>> senior_base_name('Real Madrid Castilla')
    'Real Madrid'
    >>> senior_base_name('Manchester United U18')
    'Manchester United'
    """
    if not name:
        return ""
    n = _JONG_PREFIX.sub("", name.strip())
    prev = None
    # Loop so multi-token tails (rare) fully strip; idempotent for clean names.
    while prev != n:
        prev = n
        n = _RESERVE_SUFFIX.sub("", n).strip()
    return n


# ── hardcoded fallback: reserve/youth api_id -> senior api_id ───────────
# Seeded with pairs verified during the status-model audit (2026-06). The
# data-driven layer covers the common case; this catches ids whose team name
# is unavailable or does not normalise to the parent name. Expand as the
# `left`-log surfaces unmapped affiliates (see classifier logging).
B_TEAM_TO_SENIOR: dict[int, int] = {
    425: 194,  # Jong Ajax -> Ajax
    427: 194,  # (Ajax youth alt) -> Ajax
    9260: 81,  # Olympique Marseille II -> Marseille
    24725: 499,  # Atalanta U20 -> Atalanta
    20078: 54,  # Birmingham City U21 -> Birmingham
    19046: 554,  # RSC Anderlecht II -> Anderlecht
    17426: 65,  # Nottingham Forest U18 -> Nottingham Forest
    19746: 65,  # Nottingham Forest U21 -> Nottingham Forest
    9594: 532,  # Valencia Mestalla / II -> Valencia
    9575: 541,  # Real Madrid Castilla / II -> Real Madrid
    726: 541,  # Real Madrid C -> Real Madrid
    9783: 798,  # Mallorca II -> Mallorca
    9367: 165,  # Borussia Dortmund II -> Borussia Dortmund
    7890: 165,  # Borussia Dortmund U19 -> Borussia Dortmund
}


def resolve_senior_id(club_api_id: int | None, club_name: str | None = None) -> int | None:
    """Best-effort senior org api_id for a club id (hardcoded map only — the
    data-driven layer needs a name->id lookup we don't have here). Returns the
    id unchanged when no mapping is known."""
    if club_api_id is None:
        return None
    return B_TEAM_TO_SENIOR.get(club_api_id, club_api_id)


def is_affiliate(
    club_api_id: int | None,
    club_name: str | None,
    parent_api_id: int | None,
    parent_club_name: str | None,
) -> bool:
    """Return True if *club* is *parent*'s own reserve / youth / B side.

    Hardcoded id map first (covers NULL-name ids), then data-driven base-name
    equality (covers Jong/U-number/III that the youth-suffix stripper misses).
    """
    if club_api_id is None or parent_api_id is None:
        return False
    if club_api_id == parent_api_id:
        return True
    if B_TEAM_TO_SENIOR.get(club_api_id) == parent_api_id:
        return True
    if club_name and parent_club_name:
        base = senior_base_name(club_name).lower()
        pbase = senior_base_name(parent_club_name).lower()
        if base and base == pbase:
            return True
    return False
