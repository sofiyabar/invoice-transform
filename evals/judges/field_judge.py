"""DeepEval GEval judge for Field Accuracy's free-text field semantic match
(clientName, address, items[].name).

Uses deepeval.metrics.GEval with deepeval's built-in AnthropicModel wrapper
(reads ANTHROPIC_API_KEY from the environment) — keeps the generator/judge
provider split from CLAUDE.md: generator = Gemini, judges = Anthropic.

Default model is claude-haiku-4-5: this judge runs once per free-text field
per record (hundreds of calls across the dataset), so a fast/cheap model is
the right default; override via judge_model= for spot-checks with a stronger
model.
"""

from functools import lru_cache

from deepeval.metrics import GEval
from deepeval.models import AnthropicModel
from deepeval.test_case import LLMTestCase, SingleTurnParams

DEFAULT_JUDGE_MODEL = "claude-haiku-4-5"

# Criteria are field-specific (a company name and a street address shouldn't
# be judged by the same rubric) but share the same shape: "same real-world
# entity, formatting/paraphrase differences don't count as errors".
_CRITERIA = {
    "clientName": (
        "Determine whether 'actual output' refers to the same person/company "
        "as 'expected output'. Minor formatting differences (casing, "
        "abbreviations like 'Corp.' vs 'Corporation', extra middle names, "
        "punctuation) are NOT errors. A different name, or a materially "
        "incomplete name that could plausibly refer to someone else, IS an "
        "error."
    ),
    "address": (
        "Determine whether 'actual output' refers to the same physical "
        "address as 'expected output'. Formatting differences (abbreviations "
        "like 'St.' vs 'Street', line order, casing, punctuation) are NOT "
        "errors. A different address, or a missing component that makes it "
        "ambiguous/non-deliverable (e.g. missing city or street number "
        "present in expected output), IS an error."
    ),
    "items.name": (
        "Determine whether 'actual output' describes the same line-item "
        "product/service as 'expected output'. Paraphrasing, synonyms, and "
        "formatting differences are NOT errors. A different item, or a "
        "materially vaguer description that loses the identity of the item, "
        "IS an error."
    ),
}


@lru_cache(maxsize=None)
def _get_metric(field_name: str, judge_model: str) -> GEval:
    return GEval(
        name=f"{field_name}_semantic_match",
        criteria=_CRITERIA[field_name],
        evaluation_params=[
            SingleTurnParams.EXPECTED_OUTPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        model=AnthropicModel(model=judge_model),
        threshold=0.5,
    )


def judge_field_match(
    field_name: str,
    ground_truth: str,
    prediction: str,
    judge_model: str = DEFAULT_JUDGE_MODEL,
) -> float:
    """Returns a 0-1 semantic match score for one free-text field value.

    Callers should short-circuit the trivial None/None and None/value cases
    themselves (see evals/field_accuracy.py) — this function assumes both
    ground_truth and prediction are non-empty strings and always calls the
    judge, so it can be tested/used in isolation.
    """
    if field_name not in _CRITERIA:
        raise ValueError(f"No judge criteria defined for field {field_name!r}")

    metric = _get_metric(field_name, judge_model)
    test_case = LLMTestCase(
        input=f"Field: {field_name}",
        expected_output=ground_truth,
        actual_output=prediction,
    )
    metric.measure(test_case)
    return metric.score
