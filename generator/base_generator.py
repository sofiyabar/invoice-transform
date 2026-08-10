"""Adapter interface for the invoice generator under evaluation.

Generator uses Gemini (google-genai SDK); judges in evals/ remain on
Anthropic — this is an intentional split, not an oversight.
Everything in evals/ and data/ depends only on this function's signature,
not on how it's implemented.
"""

from google import genai
from dotenv import load_dotenv
import json
import re

load_dotenv()  # подхватывает .env из корня проекта, если переменная ещё не в окружении

client = genai.Client()  # читает GEMINI_API_KEY из переменной окружения

def parse_invoice_from_text(text: str) -> dict:
    # Промпт скопирован дословно из aiController.js (Finvoice-AI, MIT license)
    prompt = f"""
      You are an expert invoice data extraction AI. Analyze the following text and extract the relevant information to create an invoice.
      The output MUST be a valid JSON object.
      The JSON object should have the following structure:
      {{
        "clientName": "string",
        "email": "string (if available)",
        "address": "string (if available)",
        "items": [
          {{
            "name": "string",
            "quantity": "number",
            "unitPrice": "number"
          }}
        ]
      }}
      Here is the text to parse:
      --- TEXT START ---
      {text}
      --- TEXT END ---
      Extract the data and provide only the JSON object.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    response_text = response.text

    # Та же хрупкая логика парсинга, что и в оригинале — намеренно не улучшена
    cleaned = re.sub(r"```json|```", "", response_text).strip()
    return json.loads(cleaned)  # намеренно без try/except — фиксируем реальный parse failure rate


def normalize_prediction(raw: dict) -> dict:
    """Normalize known Gemini output quirks (see CHANGELOG.md, 2026-08-06 smoke
    test) so the raw dict from parse_invoice_from_text() validates cleanly
    against data.schema.InvoiceFields:
      - missing scalar fields come back as "" rather than the schema's null
      - item quantity/unitPrice can come back non-numeric (e.g. "") when the
        model couldn't extract a number; InvoiceItem requires float, so a raw
        "" would raise a pydantic ValidationError. Coerced to NaN instead --
        downstream numeric comparisons treat NaN as a mismatch, which is the
        correct signal, not a harness crash.

    This lives here (not in evals/) because it's part of the generator's
    output contract -- generator.completeness_gate and any other generator/
    consumer needs well-typed InvoiceFields too, not just eval scoring.
    """
    coerced = dict(raw)
    for field in ("clientName", "email", "address"):
        if isinstance(coerced.get(field), str) and coerced[field].strip() == "":
            coerced[field] = None

    items = coerced.get("items")
    if not isinstance(items, list):
        coerced["items"] = []
        return coerced

    fixed_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item = dict(item)
        if not isinstance(item.get("name"), str):
            item["name"] = "" if item.get("name") is None else str(item["name"])
        for numeric_field in ("quantity", "unitPrice"):
            v = item.get(numeric_field)
            try:
                item[numeric_field] = float(v)
            except (TypeError, ValueError):
                item[numeric_field] = float("nan")
        fixed_items.append(item)
    coerced["items"] = fixed_items
    return coerced
