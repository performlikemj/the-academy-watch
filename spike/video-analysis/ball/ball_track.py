"""Constant-velocity Kalman tracking; pixel jump is an uncalibrated proxy."""

from __future__ import annotations
import math
import numpy as np


def track(
    rows,
    duration_s,
    sample_fps=2.0,
    max_gap_s=1.0,
    pixels_per_metre=20.0,
    max_speed_m_s=30.0,
):
    """One hypothesis, nearest observation under 30 m/s * elapsed seconds * px/m.

    Short gaps are bridged only when a later observation joins the same track.
    Trailing predictions do not extend continuity. Abrupt jumps start fragments.
    No homography is implied by the configurable 20 source-px/metre convention.
    """
    state = covariance = None
    previous_t = last_seen = None
    last_xy = None
    fragments = []
    points = []
    h = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    for row in rows:
        t = row["t"]
        if previous_t is not None and t <= previous_t:
            raise ValueError("timestamps must increase")
        if last_seen is not None and t - last_seen > max_gap_s + 1e-6:
            state = None
        dt = t - previous_t if previous_t is not None else 1 / sample_fps
        previous_t = t
        if state is not None:
            f = np.eye(4)
            f[0, 2] = f[1, 3] = dt
            g = np.array([[dt * dt / 2, 0], [0, dt * dt / 2], [dt, 0], [0, dt]])
            state = f @ state
            covariance = f @ covariance @ f.T + g @ g.T * 100
        detections = row["detections"]
        selected = None
        if state is not None and detections:
            assert last_xy is not None and last_seen is not None
            predicted_xy = state[:2]
            jump = max_speed_m_s * pixels_per_metre * (t - last_seen)
            eligible = [d for d in detections if math.dist(d["xy"], last_xy) <= jump]
            if eligible:
                selected = min(
                    eligible,
                    key=lambda d: (math.dist(d["xy"], predicted_xy), -d["confidence"]),
                )
            else:
                state = None
        if state is None and detections:
            selected = max(detections, key=lambda d: d["confidence"])
            state = np.array([*selected["xy"], 0.0, 0.0])
            covariance = np.diag([25.0, 25.0, 400.0, 400.0])
            fragments.append([t, t])
        elif selected is not None:
            innovation = np.array(selected["xy"]) - h @ state
            gain = (
                covariance @ h.T @ np.linalg.inv(h @ covariance @ h.T + np.eye(2) * 9)
            )
            state += gain @ innovation
            covariance = (np.eye(4) - gain @ h) @ covariance
            fragments[-1][1] = t
        if selected is not None:
            assert state is not None
            last_seen, last_xy = t, selected["xy"]
            points.append(
                {
                    "t": t,
                    "xy": state[:2].tolist(),
                    "observed_xy": selected["xy"],
                    "fragment": len(fragments) - 1,
                }
            )
    longest = max((b - a + 1 / sample_fps for a, b in fragments), default=0.0)
    return {
        "continuity": min(1.0, longest / duration_s),
        "fragments": len(fragments),
        "longest_track_s": min(duration_s, longest),
        "fragment_intervals": fragments,
        "points": points,
    }
