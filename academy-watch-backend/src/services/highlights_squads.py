"""Publication classification shared by review contexts and source-change guards."""

import re
import unicodedata

YOUTH_WORDS = r"\b(?:youth\w*|academ\w*|junior\w*|juven\w*|cadet\w*|minor\w*|teen\w*|mini\w*|colt\w*|boy\w*|girl\w*|child\w*|kid\w*|school\w*|scholar\w*|infantil\w*|varsity|development|underage|under age|jugend\w*|freshm[ae]n|sophomore\w*|primary|secondary|jv|(?:eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen)s?)\b"
AGE_PREFIX = r"\b(?:u|under|sub|o|jo|mo|age|aged|yr|year|grade|j|p|f)\s*(\d{1,2})(?!\d)"
AGE_SUFFIX = r"(?<!\d)(\d{1,2})\s*(?:u\b|s\b|(?:and\s+)?under\b)"
SENIOR_NAMES = frozenset(
    {
        "first team",
        "reserves",
        "seniors",
        "senior",
        "men",
        "women",
        "ladies",
        "vets",
        "veterans",
        "a team",
        "b team",
        "1st xi",
        "2nd xi",
    }
)


def squad_classification(squad):
    if squad is None:
        return "unknown"
    if squad.age_limit is not None and squad.age_limit <= 18:
        return "youth"
    label = (
        re.sub(
            r"[\W_]+",
            " ",
            "".join(
                str(unicodedata.decimal(char)) if char.isdecimal() else char
                for char in unicodedata.normalize("NFKC", squad.name or "")
            ),
            flags=re.UNICODE,
        )
        .strip()
        .lower()
    )
    if re.search(YOUTH_WORDS, label) or re.search(r"\bunder\s+[a-z]+", label):
        return "youth"
    limits = [int(m[1]) for pattern in (AGE_PREFIX, AGE_SUFFIX) for m in re.finditer(pattern, label)]
    if any(age <= 18 for age in limits):
        return "youth"
    # Labels, including founding/season/cohort years, never prove adulthood.
    # A verified whole-recording senior attestation can resolve unknown evidence.
    if squad.kind == "age_group" or squad.age_limit is not None or limits:
        return "unknown"
    return "adult" if squad.kind in {"first_team", "reserves"} and label in SENIOR_NAMES else "unknown"
