"""Strict parsing for the Film Room grounded-claim contract."""

from __future__ import annotations

import json
import math
from typing import Any

CONFIDENCE_VALUES = frozenset({"low", "medium", "high"})
VISIBILITY_VALUES = frozenset({"clear", "partial", "unclear"})
CLAIM_FIELDS = frozenset(
    {"claim", "t0", "t1", "box_t", "box", "confidence", "visibility"}
)
# box_t is required by the current prompt contract, but deliberately omitted
# here so pre-box_t runs fall back to t0 instead of becoming unscorable.
REQUIRED_CLAIM_FIELDS = CLAIM_FIELDS - {"box_t"}
BOX_T_SPAN_TOLERANCE_S = 0.5


def _number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _malformed_claim(value: object, fields: list[str]) -> dict:
    if isinstance(value, dict):
        text = value.get("claim")
        raw_box = value.get("box")
        box = list(raw_box) if isinstance(raw_box, (list, tuple)) else None
        t0 = value.get("t0") if _number(value.get("t0")) else None
        t1 = value.get("t1") if _number(value.get("t1")) else None
        if "box_t" in value:
            box_t = value.get("box_t") if _number(value.get("box_t")) else None
            box_t_source = "provided"
        else:
            box_t = t0
            box_t_source = "fallback_t0"
        confidence = (
            value.get("confidence")
            if value.get("confidence") in CONFIDENCE_VALUES
            else None
        )
        visibility = (
            value.get("visibility")
            if value.get("visibility") in VISIBILITY_VALUES
            else None
        )
    else:
        text = (
            value
            if isinstance(value, str)
            else json.dumps(value, ensure_ascii=False, default=str)
        )
        box = None
        t0 = None
        t1 = None
        box_t = None
        box_t_source = "fallback_t0"
        confidence = None
        visibility = None
    return {
        "claim": text if isinstance(text, str) else str(text or ""),
        "t0": t0,
        "t1": t1,
        "box_t": float(box_t) if box_t is not None else None,
        "box_t_source": box_t_source,
        "box": box,
        "confidence": confidence,
        "visibility": visibility,
        "malformed": True,
        "malformed_fields": sorted(set(fields)),
    }


def normalize_claim(value: object) -> dict:
    """Keep one claim while strictly flagging every contract violation."""
    if not isinstance(value, dict):
        return _malformed_claim(value, ["claim_object"])

    problems = [
        f"missing:{field}" for field in sorted(REQUIRED_CLAIM_FIELDS - value.keys())
    ]
    problems.extend(
        f"unexpected:{field}" for field in sorted(value.keys() - CLAIM_FIELDS)
    )

    claim = value.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        problems.append("claim")

    t0 = value.get("t0")
    t1 = value.get("t1")
    if not _number(t0):
        problems.append("t0")
        t0 = None
    else:
        t0 = float(t0)
    if not _number(t1):
        problems.append("t1")
        t1 = None
    else:
        t1 = float(t1)
    if t0 is not None and t1 is not None and t1 < t0:
        problems.append("time_order")

    if "box_t" in value:
        box_t_source = "provided"
        box_t = value.get("box_t")
        if not _number(box_t):
            problems.append("box_t")
            box_t = None
        else:
            box_t = float(box_t)
    else:
        box_t_source = "fallback_t0"
        box_t = t0
    if (
        box_t is not None
        and t0 is not None
        and t1 is not None
        and (box_t < t0 - BOX_T_SPAN_TOLERANCE_S or box_t > t1 + BOX_T_SPAN_TOLERANCE_S)
    ):
        problems.append("box_t outside claim span")

    raw_box = value.get("box")
    box = None
    if raw_box is not None:
        if (
            not isinstance(raw_box, (list, tuple))
            or len(raw_box) != 4
            or not all(_number(item) for item in raw_box)
        ):
            problems.append("box")
        else:
            box = [float(item) for item in raw_box]
            if box[2] <= box[0] or box[3] <= box[1]:
                problems.append("box_order")

    confidence = value.get("confidence")
    if confidence not in CONFIDENCE_VALUES:
        problems.append("confidence")
        confidence = None
    visibility = value.get("visibility")
    if visibility not in VISIBILITY_VALUES:
        problems.append("visibility")
        visibility = None

    return {
        "claim": claim if isinstance(claim, str) else str(claim or ""),
        "t0": t0,
        "t1": t1,
        "box_t": box_t,
        "box_t_source": box_t_source,
        "box": box,
        "confidence": confidence,
        "visibility": visibility,
        "malformed": bool(problems),
        "malformed_fields": sorted(set(problems)),
    }


def parse_claims(raw: str | bytes | dict[str, Any] | list[Any]) -> list[dict]:
    """Parse a response without dropping bad claims.

    A response that is not JSON, or whose top level violates the contract, is
    represented by one malformed claim. This makes schema failure measurable
    instead of silently turning it into an empty response.
    """
    parsed: object = raw
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return [_malformed_claim(raw, ["response_json"])]

    if not isinstance(parsed, dict):
        return [_malformed_claim(parsed, ["response_object"])]
    top_level_problems = [f"missing:{field}" for field in ({"claims"} - set(parsed))]
    top_level_problems.extend(
        f"unexpected:{field}" for field in (set(parsed) - {"claims"})
    )
    claims = parsed.get("claims")
    if not isinstance(claims, list):
        return [_malformed_claim(claims, top_level_problems + ["claims_list"])]
    normalized = [normalize_claim(claim) for claim in claims]
    if top_level_problems:
        if not normalized:
            return [_malformed_claim(parsed, top_level_problems)]
        for claim in normalized:
            claim["malformed"] = True
            claim["malformed_fields"] = sorted(
                set(claim["malformed_fields"] + top_level_problems)
            )
    return normalized
