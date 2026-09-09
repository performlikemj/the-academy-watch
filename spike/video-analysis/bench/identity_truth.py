"""Keep disputed jersey bindings separate from corrected or uncertain kit truth."""


def kit_truth(truth: dict) -> dict:
    uncertain = bool(truth.get("kit_color_uncertain"))
    override = truth.get("kit_color_truth_override")
    eligible = uncertain or bool(override) or not truth.get("truth_label_disputed")
    color = None if uncertain or not eligible else override or truth.get("kit_color")
    return {"eligible": bool(eligible), "uncertain": uncertain, "color": color}
