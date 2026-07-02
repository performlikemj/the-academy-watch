#!/usr/bin/env python3
"""
game_time.py — pure (stdlib-only) translation of operator timeline markers into a single-pass
in-play processing plan, so the GPU pipeline only works the minutes that matter.

No torch / OpenCV / heavy imports here on purpose: run_spike.py imports this, and it is unit-
testable (and importable by the Flask side) WITHOUT CUDA. See the paired cost lever in
docs/film-room.md §15 and run_local.py's per-segment variant.
"""
from __future__ import annotations


def in_play_plan(
    kickoff_s: float | None,
    halftime_s: float | None,
    second_half_kickoff_s: float | None,
    end_s: float | None,
):
    """Translate the four operator markers into a single-pass in-play plan.

    Returns ``(run_start, run_end, gap)``:
      - ``run_start``: second to start processing (``None`` => marker mode OFF; the caller
        should fall back to its own ``--start-seconds`` / ``--max-seconds``).
      - ``run_end``: second to stop (``None`` => run to the end of the video).
      - ``gap``: ``(gap_start, gap_end)`` halftime interval to SKIP, or ``None``.

    Markers are optional except kickoff and degrade SAFELY (a missing/implausible marker is
    ignored rather than producing a wrong cut):
      - kickoff ``None``                              -> ``(None, None, None)``
      - kickoff set                                   -> ``run_start = kickoff`` (skip warm-up)
      - end set                                       -> ``run_end = end`` (skip post-match)
      - halftime AND 2nd-half set, and ordered sanely
        (``kickoff <= halftime < second_half <= end``) -> skip ``(halftime, second_half)``
      - a lone or out-of-order halftime / 2nd-half    -> no gap (bound only)
    """
    if kickoff_s is None:
        return None, None, None
    run_start = float(kickoff_s)
    run_end = float(end_s) if end_s is not None else None
    gap = None
    if halftime_s is not None and second_half_kickoff_s is not None:
        h = float(halftime_s)
        sh = float(second_half_kickoff_s)
        if run_start <= h < sh and (run_end is None or sh <= run_end):
            gap = (h, sh)
    return run_start, run_end, gap


def _selftest() -> None:
    assert in_play_plan(None, 1, 2, 3) == (None, None, None)
    assert in_play_plan(60, None, None, None) == (60.0, None, None)
    assert in_play_plan(60, None, None, 7000) == (60.0, 7000.0, None)
    assert in_play_plan(60, 3000, 3800, 7000) == (60.0, 7000.0, (3000.0, 3800.0))
    # lone halftime (no 2nd-half) -> can't resume -> no gap, just bound
    assert in_play_plan(60, 3000, None, 7000) == (60.0, 7000.0, None)
    # out of order: halftime >= 2nd-half -> ignore
    assert in_play_plan(60, 3800, 3000, 7000) == (60.0, 7000.0, None)
    # halftime before kickoff -> ignore
    assert in_play_plan(60, 30, 3800, 7000) == (60.0, 7000.0, None)
    # 2nd-half beyond end -> implausible -> ignore
    assert in_play_plan(60, 3000, 3800, 3500) == (60.0, 3500.0, None)
    # ints coerced to float
    rs, re, gap = in_play_plan(0, 3000, 3800, 7000)
    assert rs == 0.0 and re == 7000.0 and gap == (3000.0, 3800.0)
    print("game_time selftest: OK")


if __name__ == "__main__":
    _selftest()
