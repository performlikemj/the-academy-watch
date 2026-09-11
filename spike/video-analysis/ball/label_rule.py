"""Version-2 labels and explicit, persistent rule-A review state."""

import json
from pathlib import Path

BASE_REVIEW_KEYS = frozenset(
    (key.rsplit("|", 1)[0], float(key.rsplit("|", 1)[1]))
    for key in json.loads(
        (Path(__file__).parent / "fixtures/any_ball_review_keys.json").read_text()
    )
)
REVIEW_TOTAL = len(BASE_REVIEW_KEYS)
N21 = "m04-n21-t3011-390297-390800"
RULES = ("as_labelled", "any_ball")
V2_FIELDS = {
    "schema_version",
    "updated_at",
    "match_ball",
    "review_frame",
    "review_confirmed",
    "needs_any_ball_review",
    "needs_confirmation",
}


def migrate_row(row, frame):
    row = dict(row)
    version = row.get("schema_version", 2 if "match_ball" in row else 1)
    if type(version) is not int or version not in (1, 2):
        raise ValueError("unsupported label schema_version")
    if version == 2 and "match_ball" not in row:
        raise ValueError("v2 requires match_ball")
    if version == 1:
        row.update(schema_version=2, match_ball=True if row["visible"] else None)
        if not row["visible"]:
            row.update(
                review_frame=True, review_confirmed=False, needs_any_ball_review=True
            )
        if row["visible"] and row["clip"] == N21 and frame.get("sample_index", 99) < 6:
            row.update(
                match_ball=False,
                needs_confirmation=True,
                review_frame=True,
                review_confirmed=False,
            )
    row["schema_version"] = 2
    row.setdefault("updated_at", 0)
    if (
        type(row["updated_at"]) is not int
        or not 0 <= row["updated_at"] <= 9007199254740991
    ):
        raise ValueError("updated_at must be nonnegative integer milliseconds")
    if row["match_ball"] is not None and type(row["match_ball"]) is not bool:
        raise ValueError("match_ball must be true, false or null")
    if not row["visible"] and row["match_ball"] is not None:
        raise ValueError("no-ball match_ball must be null")
    for field in V2_FIELDS - {"schema_version", "match_ball", "updated_at"}:
        if field in row and type(row[field]) is not bool:
            raise ValueError(f"{field} must be boolean")
    if row.get("review_confirmed") and (
        not row.get("review_frame")
        or row.get("needs_any_ball_review")
        or row.get("needs_confirmation")
    ):
        raise ValueError("confirmed review cannot remain pending")
    return row


def pending(row):
    return bool(row.get("needs_any_ball_review") or row.get("needs_confirmation"))


def confirmed(row):
    return bool(row and row.get("review_confirmed") and not pending(row))


def review_keys(labels, base_keys=BASE_REVIEW_KEYS):
    return set(base_keys) | {key for key, row in labels.items() if pending(row)}


def rule_metadata(labels, rule, base_keys=BASE_REVIEW_KEYS):
    if rule not in RULES:
        raise ValueError(f"unknown label rule: {rule}")
    keys = review_keys(labels, base_keys)
    count = sum(confirmed(labels.get(key)) for key in keys)
    pending_count = sum(pending(row) for row in labels.values())
    return {
        "label_rule": rule,
        "match_ball_note": "match_ball is carried through labels but unused by detector metrics; all visible labels are positives, visible:false is no-ball. as_labelled preserves supplied visibility; any_ball declares rule A without inferring missing balls.",
        "review_confirmed": count,
        "review_total": len(keys),
        "pending_rows": pending_count,
        "provisional": f"PROVISIONAL: {count} of {len(keys)} review frames confirmed"
        if rule == "any_ball" and (pending_count or count < len(keys))
        else None,
    }


def banner_tables(text, metadata):
    """Badge every Markdown table's first header cell, including appended tables."""
    banner = metadata.get("provisional")
    lines = text.splitlines()
    if banner:
        for i in range(len(lines) - 1):
            if lines[i].startswith("|") and lines[i + 1].startswith("|---"):
                lines[i] = lines[i].replace("| ", f"| {banner} · ", 1)
    return "\n".join(lines) + "\n"
