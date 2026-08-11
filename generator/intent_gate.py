"""Intake Gate, Step 1's underlying decision: does this text represent a
request to create an invoice at all?

This is our own component, on top of the copied Finvoice-AI baseline in
base_generator.py -- not part of their code (see project_brief.md, "Layer 0 —
Intent & Completeness Gate", now called Intake Gate). It lives in generator/,
not evals/, because it *produces* a decision that would gate the real
pipeline (skip generation entirely on a "no" and avoid a hallucinated
invoice), the same role base_generator.py plays -- it isn't a judge/metric
that grades an existing output. Scoring this decision against ground truth
(accuracy, FP/FN rate) is a separate concern, see evals/intake_intent_gate.py.

Follows the provider split from CLAUDE.md: generator logic uses Gemini, same
as base_generator.py -- this only measures the gate's own decision quality,
not a comparison judgment, so it doesn't need the Anthropic judge provider.
"""

import json
import re

from dotenv import load_dotenv
from google import genai

load_dotenv()  # picks up .env from the repo root if not already in the environment

client = genai.Client()  # reads GEMINI_API_KEY from the environment

_PROMPT_TEMPLATE = """You classify short business messages (emails, chat notes, casual messages) for an invoicing tool.

Decide: does the sender want a NEW invoice created/sent for them -- regardless of whether they've given enough detail to actually build one yet?

Answer yes if the sender is asking for, or clearly wants, an invoice to be created -- even if:
- they haven't provided any details yet (e.g. "I need to send an invoice out but haven't sorted the particulars yet")
- the word "invoice" is never used, as long as it's clear they want one generated from completed work, goods, or services delivered to a client

Do NOT require the message to already contain enough information to build the invoice -- that's a separate concern from whether they want one. Only judge intent here.

Answer no if the text:
- has nothing to do with invoicing (small talk, unrelated requests, gibberish)
- talks ABOUT an existing invoice without asking to create a new one (e.g. "write a reminder about their overdue invoice #4521" -- this mentions an invoice but does not ask to create one)

Respond with ONLY a valid JSON object of the form {{"is_invoice_request": true}} or {{"is_invoice_request": false}} -- no other text.

Here is the text to classify:
--- TEXT START ---
{text}
--- TEXT END ---
"""


def is_invoice_request(text: str) -> bool:
    prompt = _PROMPT_TEMPLATE.format(text=text)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    cleaned = re.sub(r"```json|```", "", response.text).strip()
    return bool(json.loads(cleaned)["is_invoice_request"])
