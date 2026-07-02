"""Learn from human corrections (Film Room feedback → model improvement).

This is the "learn from its mistakes" loop. It is RLHF-STYLE, not literal
policy-gradient RL: the identity pipeline has no sequential reward to optimise —
the right mechanics for *this* problem are (1) MEASURE where the model was wrong
against human truth, (2) RECALIBRATE the vote/merge thresholds from those errors,
(3) build a supervised FINE-TUNE manifest from the corrected crops so the jersey
reader / a consented ReID embedder retrain. Each reviewed match feeds the next.

The human review verdict lives on each tracklet as `review_action`:
  confirmed  — model's auto suggestion was right (human agreed)
  reassigned — model put the wrong number/identity (human corrected it)
  dismissed  — model tracked a non-player (false positive)
  split      — model OVER-MERGED two players into one chain (contamination)
and `suggested_number` is the model's original guess (stable across binding), so
model-vs-human is directly measurable. Pure functions over ORM rows / dicts.
"""

from collections import Counter


def match_accuracy(tracklets, roster_by_id, our_cluster=None) -> dict:
    """Per-match model accuracy from human review decisions on chains."""
    chains = [t for t in tracklets if t.kind == "chain"]
    # a human split writes ONE tombstone (the operation) + two review_action='split'
    # chain segments (machine-made rows, not verdicts on a model suggestion). Count
    # the operation from the tombstone; exclude the segments from the review tallies
    # so two rows can't inflate `decided` / deflate precision. Un-re-tagged segments
    # fall into `unreviewed` (they still await a human number/dismiss decision).
    splits = sum(1 for t in tracklets if t.kind == "tombstone" and t.review_action == "split")
    reviewed = [t for t in chains if t.review_action and t.review_action != "split"]
    by_action = Counter(t.review_action for t in reviewed)
    # number-read accuracy: on reviewed+bound chains, did the model's number match
    # the human's chosen roster number?
    bound = [t for t in reviewed if t.roster_entry_id and roster_by_id.get(t.roster_entry_id)]
    correct = sum(1 for t in bound if t.suggested_number == roster_by_id[t.roster_entry_id].jersey_number)
    # auto-tag precision: of decisions, how many endorsed the model (confirmed) vs
    # corrected it (reassigned/dismissed/split)?
    decided = by_action["confirmed"] + by_action["reassigned"] + by_action["dismissed"] + splits
    return {
        "chains_total": len(chains),
        "reviewed": len(reviewed),
        "unreviewed": len(chains) - len(reviewed),
        "confirmed": by_action["confirmed"],
        "reassigned": by_action["reassigned"],
        "dismissed": by_action["dismissed"],
        "splits": splits,
        "number_read_accuracy": round(correct / len(bound), 3) if bound else None,
        "auto_tag_precision": round(by_action["confirmed"] / decided, 3) if decided else None,
    }


def recalibration_signals(tracklets) -> dict:
    """Threshold-tuning signals from corrections — the 'reward' that adjusts the
    gate/vote heuristics for the next match."""
    chains = [t for t in tracklets if t.kind == "chain"]
    # a split's signal lives on the tombstone (the original chain, which keeps its
    # confidence); the two 'split' segments are low-confidence machine rows and must
    # not be counted as splits or as high-confidence errors.
    split_ops = [t for t in tracklets if t.kind == "tombstone" and t.review_action == "split"]
    high_confirmed = sum(1 for t in chains if t.review_action == "confirmed" and t.confidence == "high")
    high_wrong = sum(1 for t in chains if t.review_action in ("reassigned", "dismissed") and t.confidence == "high")
    high_wrong += sum(1 for t in split_ops if t.confidence == "high")
    splits = len(split_ops)
    dismissed = sum(1 for t in chains if t.review_action == "dismissed")
    suggestions = []
    denom = high_confirmed + high_wrong
    if denom and high_wrong / denom > 0.3:
        suggestions.append(
            f"High-confidence chains were wrong {high_wrong}/{denom} times — raise MIN_VOTES "
            "or require a human confirm before auto-binding."
        )
    if splits:
        suggestions.append(f"{splits} chain(s) split (over-merge) — tighten merge overlap / the shirt gate.")
    if dismissed:
        suggestions.append(f"{dismissed} chain(s) dismissed (non-players) — strengthen the role/not-a-player gate.")
    if not suggestions:
        suggestions.append("No systematic error signal yet — review more chains to accumulate signal.")
    return {
        "high_conf_confirmed": high_confirmed,
        "high_conf_wrong": high_wrong,
        "splits": splits,
        "dismissed": dismissed,
        "suggestions": suggestions,
    }


def training_manifest(feedback_rows) -> dict:
    """Group per-crop feedback into a supervised fine-tune manifest:
      reader_examples: crop -> confirmed jersey number (PARSeq/VLM reader);
      reid_groups: (match, side, number) -> [crops] (contrastive ReID positives).
    Consent-gated to club-owned crops; dismissed/contaminated excluded from positives."""
    reader, reid = [], {}
    negatives = 0
    for r in feedback_rows:
        if r.get("label") == "not_a_player":
            negatives += 1
            continue
        if r.get("confirmed_number") is None or r.get("contaminated"):
            continue
        if r.get("consent") != "club_owned":  # consent gate — only our consented players train the model
            continue
        reader.append({"crop": r["file"], "label": int(r["confirmed_number"]), "match_id": r["match_id"]})
        key = f"{r['match_id']}:{r.get('side')}:{r['confirmed_number']}"
        reid.setdefault(key, []).append(r["file"])
    return {
        "reader_examples": reader,
        "reid_groups": reid,
        "n_reader_examples": len(reader),
        "n_reid_identities": len(reid),
        "n_negatives": negatives,
    }
