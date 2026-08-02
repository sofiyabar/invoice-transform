"""DeepEval GEval judge for Layer 1 free-text field semantic match
(company, address, line_items).

TODO: implement using deepeval.metrics.GEval with an Anthropic model.
"""


def judge_field_match(field_name: str, ground_truth: str, prediction: str) -> float:
    raise NotImplementedError("TODO: DeepEval GEval semantic match, returns 0-1 score")
