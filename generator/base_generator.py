"""Adapter interface for the invoice generator under evaluation.

TODO: decide the actual generation approach (minimal Anthropic-based prompt
wrapper vs. adapting an existing open-source project) and implement it here.
Everything in evals/ and data/ depends only on this function's signature,
not on how it's implemented — the decision is deferred without blocking
the rest of the eval scaffold.
"""

from typing import Any


def generate(raw_text: str) -> dict[str, Any]:
    """Take unstructured raw text and return a predicted invoice dict.

    Expected output keys should match the ground-truth schema in
    data/schema.py (e.g. company, date, address, total, ...).
    """
    raise NotImplementedError("TODO: implement or wrap a base invoice generator")
