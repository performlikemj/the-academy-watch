"""Human corrections -> assistant training labels (Film Room feedback loop).

A human binding in tag review is ground truth: a tracklet bound to a roster entry
(tag_source 'human' / review_action) = confirmed (team, jersey_number) for every
crop of that tracklet's member fragments; dismissed = a not-a-player negative.
This builder projects a finalized match's human-reviewed tracklets into per-crop
labelled rows that carry the MODEL'S ORIGINAL prediction beside the human truth,
so ONE artifact serves three goals:
  (a) fine-tune the jersey reader / a consented person-ReID embedder,
  (b) recalibrate the vote thresholds (join confirmed_number vs original votes),
  (c) measure auto-tag precision/recall (human truth vs the original auto guess).

CONSENT is a hard gate, not a filter: our-side only by default. Opposition
(often youth) crops feed the numbers-only report but MUST NOT enter the training
corpus (UK GDPR Art.8 / FA safeguarding — see ledgers/CONTINUITY_video-analysis.md).
`side='all'` overrides but still tags consent per row.

Pure: ORM rows + a crops callable in, an iterator of dicts out — unit-testable
without a database or filesystem (pass a stub crops_for_tracklet).
"""

import os

from src.services.video_report import tracklet_number_votes


def build_feedback_labels(*, match, tracklets, roster_by_id, crops_for_tracklet, side="ours"):
    """Yield one labelled row per crop of every human-reviewed tracklet.

    match: VideoMatch (uses .id, .our_team_cluster)
    tracklets: iterable of VideoTracklet
    roster_by_id: {roster_entry_id: VideoRosterEntry}
    crops_for_tracklet: tracklet -> [{file, t, frame, laplacian_var}]
    side: 'ours' (default, consent-safe) | 'all'
    """
    our = match.our_team_cluster
    for t in tracklets:
        # split tombstones (dismissed, review_action='split', thumbnails retained) are
        # bookkeeping rows for a replaced over-merged chain, not a human verdict on a
        # player — never export their crops as not_a_player negatives (corpus poisoning
        # once prod crop persistence ships).
        if t.kind == "tombstone":
            continue
        # only HUMAN-DECIDED rows are ground truth; a raw auto-tag is the model's
        # own guess and must never be exported as if a person confirmed it. Gate on
        # review_action (set ONLY on a real decision), not reviewed_at.
        human_touched = t.tag_source == "human" or t.review_action is not None or bool(t.dismissed)
        if not human_touched:
            continue
        team = t.team_cluster
        is_ours = our is not None and team == our
        if side != "all" and not is_ours:
            continue  # consent gate: opposition stays out of the corpus by default

        entry = roster_by_id.get(t.roster_entry_id) if t.roster_entry_id else None
        is_dismissed = bool(t.dismissed)
        votes = dict(tracklet_number_votes(t.evidence))
        consent = "club_owned" if is_ours else "third_party_no_consent"

        for c in crops_for_tracklet(t):
            yield {
                "match_id": match.id,
                "tracklet_id": t.id,
                "pipeline_key": t.pipeline_key,
                "crop_id": os.path.basename(c["file"]).rsplit(".", 1)[0],
                "file": c["file"],
                "side": "ours" if is_ours else "opposition",
                "consent": consent,
                # --- human ground truth ---
                "label": "not_a_player" if is_dismissed else "player",
                "confirmed_number": None if (is_dismissed or entry is None) else entry.jersey_number,
                "review_action": t.review_action,
                "source": "human",
                # --- model's original prediction (for eval + training weight) ---
                "original_suggested_number": t.suggested_number,
                "original_confidence": t.confidence,
                "original_number_votes": votes,
                "contaminated": bool(t.contaminated),
                # --- crop provenance ---
                "t": c["t"],
                "frame": c["frame"],
                "laplacian_var": c["laplacian_var"],
            }
