"""Private player-name policy shared by brief writes and the model boundary."""

import re
import unicodedata

from sqlalchemy import or_
from src.models.follow import PlayerShadow
from src.models.funding import ClubRosterMember
from src.models.league import db
from src.models.showcase import LocalPlayer
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoMatch, VideoRosterEntry

BRIEF_NAME_TOKEN_RE = re.compile(r"[^\W\d_]{2,}")
# These Latin letters do not decompose under NFKD. This is a defined ASCII
# spelling policy, not universal romanization; casefold already handles ß.
LATIN_ASCII = str.maketrans({"ł": "l", "ø": "o", "đ": "d", "æ": "ae", "œ": "oe", "ı": "i", "þ": "th", "ð": "d"})
WITHHELD_EXPECTATION = "Expectation withheld."


def name_tokens(names):
    tokens = {}
    for name in names:
        # Combining marks must be folded before token extraction; otherwise NFD
        # Müller becomes the unrelated fragments "mu" and "ller".
        for token in BRIEF_NAME_TOKEN_RE.findall(fold_brief_name(name or "")):
            tokens.setdefault(token, token)
    return tokens


def stored_name_tokens(program_id):
    """All stored aliases, regardless of suppression, status, squad or key form.

    Walk local/provider bridges and merge links as batches. Seen IDs make cycles
    terminate; both forward survivors and retained source aliases are included.
    Never serialize or publish this inventory.
    """
    members = (
        db.session.query(ClubRosterMember.local_player_id, ClubRosterMember.player_api_id)
        .filter_by(program_id=program_id)
        .all()
    )
    local_ids = {m.local_player_id for m in members if m.local_player_id is not None}
    api_ids = {m.player_api_id for m in members if m.player_api_id is not None}
    seen_local = set()
    seen_api = set()
    names = []
    while local_ids - seen_local or api_ids - seen_api:
        pending_local, pending_api = local_ids - seen_local, api_ids - seen_api
        # Reverse merge edges recover retained aliases when the roster points
        # directly at the survivor. Provider IDs include negative shadow keys.
        locals_ = (
            db.session.query(
                LocalPlayer.id,
                LocalPlayer.api_player_id,
                LocalPlayer.merged_into_local_player_id,
                LocalPlayer.display_name,
            )
            .filter(
                or_(
                    LocalPlayer.id.in_(pending_local),
                    LocalPlayer.api_player_id.in_(pending_api),
                    LocalPlayer.merged_into_local_player_id.in_(pending_local),
                )
            )
            .all()
        )
        seen_local.update(pending_local)
        seen_api.update(pending_api)
        for row in locals_:
            names.append(row.display_name)
            local_ids.add(row.id)
            if row.api_player_id is not None:
                api_ids.add(row.api_player_id)
            if row.merged_into_local_player_id is not None:
                local_ids.add(row.merged_into_local_player_id)
    for model in [TrackedPlayer, PlayerShadow]:
        names.extend(name for (name,) in db.session.query(model.player_name).filter(model.player_api_id.in_(api_ids)))
    names.extend(
        name
        for (name,) in db.session.query(VideoRosterEntry.player_name)
        .join(VideoMatch, VideoRosterEntry.video_match_id == VideoMatch.id)
        .filter(VideoMatch.club_program_id == program_id)
    )
    return name_tokens(names)


def fold_brief_name(value: str) -> str:
    return (
        "".join(character for character in unicodedata.normalize("NFKD", value) if not unicodedata.combining(character))
        .casefold()
        .translate(LATIN_ASCII)
    )


def _is_latin_word_character(character: str) -> bool:
    return character == "_" or character.isdigit() or unicodedata.name(character, "").startswith("LATIN ")


def brief_name_token_matches(token: str, line: str) -> bool:
    folded_token = fold_brief_name(token)
    folded_line = fold_brief_name(line)
    contains_non_latin_letter = any(
        character.isalpha() and not unicodedata.name(character, "").startswith("LATIN ") for character in token
    )
    if contains_non_latin_letter:
        return folded_token in folded_line

    start = 0
    while (match_start := folded_line.find(folded_token, start)) != -1:
        match_end = match_start + len(folded_token)
        left_is_word = match_start > 0 and _is_latin_word_character(folded_line[match_start - 1])
        right_is_word = match_end < len(folded_line) and _is_latin_word_character(folded_line[match_end])
        if not left_is_word and not right_is_word:
            return True
        start = match_start + 1
    return False


def strip_named_lines(body, tokens):
    """Withhold named text while retaining normalized expectation positions."""
    if not isinstance(body, str):
        return body
    return "\n".join(
        WITHHELD_EXPECTATION if any(brief_name_token_matches(token, line) for token in tokens.values()) else line
        for line in body.splitlines()
    )


def scoped_brief_analysis(value):
    """Copy analysis without private checks or their aggregate/presence signals.

    Brief model calls are isolated from ordinary observations. Their verdicts,
    limits and check-only notes must not disclose the hidden inventory, even for
    historical analyses that hashed/renumbered filtered lines.
    """
    if isinstance(value, list):
        return [scoped_brief_analysis(item) for item in value]
    if not isinstance(value, dict):
        return value
    out = {}
    for key, item in value.items():
        if "brief" in key:
            continue
        if key == "honest_limits" and isinstance(item, list):
            item = [limit for limit in item if not isinstance(limit, str) or "brief" not in limit.casefold()]
        if key == "player_notes" and isinstance(item, list):
            item = [note for note in item if not isinstance(note, dict) or note.get("observations")]
        out[key] = scoped_brief_analysis(item)
    return out


def scoped_analysis_payload(value):
    """Find analysis in any club adapter without changing stored coach briefs."""
    if isinstance(value, list):
        return [scoped_analysis_payload(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: scoped_brief_analysis(item) if key == "qwen_analysis" else scoped_analysis_payload(item)
        for key, item in value.items()
    }
