"""Reject contaminated holdouts; preserve whole source windows and continuation splits."""

import copy
import json
from pathlib import Path

import pytest
from compare_ball import load_measurements
from human_loop import frame_catalog
from round2_protocol import choose_split, validate_split


def inputs():
    m = load_measurements()
    prior = json.loads(
        (Path(__file__).parent / "fixtures/human_execution.json").read_text()
    )["split"]
    labels = {(f["clip"], f["t"]): {} for f in frame_catalog(m)}
    return m, prior, labels


def test_existing_data_cannot_supply_an_untouched_holdout():
    m, prior, labels = inputs()
    split = choose_split(m, prior)
    assert len(split["train"]) == 14 and len(split["held_out"]) == 6
    assert len(split["prior_tuning_exposed_holdout"]) == 6
    assert split["previously_untouched_holdout"] is False
    with pytest.raises(ValueError, match="hyperparameter-selection exposure"):
        validate_split(split, m, labels, prior)
    scrubbed = {**split, "prior_tuning_exposed_holdout": []}
    with pytest.raises(ValueError, match="hyperparameter-selection exposure"):
        validate_split(scrubbed, m, labels, prior)
    validate_split(split, m, labels, prior, allow_prior_tuning=True)
    reversed_m = {**m, "clips": list(reversed(m["clips"]))}
    assert choose_split(reversed_m, prior)["held_out"] == split["held_out"]


def test_native_frame_overlap_and_continuation_leakage_rejected():
    m, prior, labels = inputs()
    split = choose_split(m, prior)
    bad = copy.deepcopy(split)
    # Swap overlapping companion window into training: the native source leaks.
    a = "m04-n24-t3013-679939-681217"
    b = "m04-n10-t711-186553-188161"
    bad["held_out"].remove(a)
    bad["held_out"].append(b)
    bad["train"].remove(b)
    bad["train"].append(a)
    with pytest.raises(ValueError, match="overlapping source footage"):
        validate_split(bad, m, labels, prior, allow_prior_tuning=True)
    contaminated_init = {"train": [split["held_out"][0]]}
    with pytest.raises(ValueError, match="already trained"):
        validate_split(split, m, labels, contaminated_init, allow_prior_tuning=True)
