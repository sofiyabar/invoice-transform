"""Load external datasets into the unified InvoiceRecord schema.

TODO: implement remaining loaders per source (SROIE, Enron, HF invoice
datasets, ...), each returning list[InvoiceRecord]. Kept separate per source
so a broken/skipped source doesn't block the others.
"""

import json
from pathlib import Path

from data.schema import (
    CRITICAL_FIELDS,
    DocType,
    IntentGateRecord,
    InvoiceFields,
    InvoiceRecord,
    Segment,
    SufficiencyGateRecord,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SYNTHETIC_EVAL_DATASET = REPO_ROOT / "data" / "synthetic" / "eval_dataset.jsonl"

# eval_dataset.jsonl "style" -> schema.DocType. formal_email is the only style
# with real email structure; casual_note and chat_message are both short,
# unstructured, informal-register text, so both map to CHAT. receipt_ocr has
# no representative rows in this dataset (reserved for a future OCR source).
STYLE_TO_DOC_TYPE = {
    "formal_email": DocType.EMAIL,
    "casual_note": DocType.CHAT,
    "chat_message": DocType.CHAT,
}

# eval_dataset.jsonl's real segment values are clean/noisy/edge (see CHANGELOG.md,
# 2026-08-09 generator_probe.py audit); Segment enum spells the third one
# edge_case. Documented mismatch, fixed here at the ingestion boundary rather
# than in schema.py or the dataset.
DATASET_SEGMENT_TO_SCHEMA = {
    "clean": Segment.CLEAN,
    "noisy": Segment.NOISY,
    "edge": Segment.EDGE_CASE,
}


def _achievable_ground_truth(row: dict) -> dict:
    """row["ground_truth"] is the ORIGINAL invoice's full field set, even for
    noisy/edge rows where removed_fields/removed_item were deliberately cut
    from raw_text during generation (see data_generation_process.md) -- the
    value is real, just never mentioned in the text the generator actually
    sees. Scoring against that unmodified ground_truth guarantees an "error"
    on every removed field/item regardless of extraction quality: a perfect
    extractor can't recover a fact that isn't in its input. E.g.
    row_000_noisy_a's raw_text never mentions an email at all; the generator
    correctly returned "" and got scored wrong against the original email.

    This null-out/drop step builds the ground truth field accuracy should
    actually score against: what a perfect extractor operating on raw_text
    alone could produce. See conversation record ("почему у тебя все ошибки?").
    """
    gt = dict(row["ground_truth"])
    for field in row.get("removed_fields") or []:
        gt[field] = None

    removed_item = row.get("removed_item")
    if removed_item and gt.get("items"):
        gt["items"] = [item for item in gt["items"] if item.get("name") != removed_item]

    return gt


def load_synthetic_extraction(path: Path = SYNTHETIC_EVAL_DATASET) -> list[InvoiceRecord]:
    """Rows of eval_dataset.jsonl usable for field/document/segment accuracy
    scoring: those with a real ground_truth, i.e. segment in {clean, noisy,
    edge_case}. Excludes Intake rows (out-of-scope / no-data / robustness),
    which carry ground_truth=null and belong to the intent-gate eval instead.

    ground_truth is the "achievable" version (see _achievable_ground_truth),
    not the raw original invoice -- field accuracy must never score a
    field/item that raw_text never mentioned in the first place.
    """
    records: list[InvoiceRecord] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("ground_truth") is None:
                continue
            records.append(
                InvoiceRecord(
                    id=row["id"],
                    raw_text=row["raw_text"],
                    ground_truth=InvoiceFields(**_achievable_ground_truth(row)),
                    segment=DATASET_SEGMENT_TO_SCHEMA[row["segment"]],
                    doc_type=STYLE_TO_DOC_TYPE[row["style"]],
                    source="synthetic_extraction_dataset_v1",
                )
            )
    return records


def load_intent_gate_dataset(path: Path = SYNTHETIC_EVAL_DATASET) -> list[IntentGateRecord]:
    """All 600 rows of eval_dataset.jsonl for Intake Gate, Step 1
    (is-invoice-intent classifier) eval. Unlike load_synthetic_extraction(),
    this does NOT filter by ground_truth -- Intake's whole job is telling
    invoice rows apart from non-invoice ones, so it needs both classes, not
    just the ones with real ground_truth fields.
    """
    records: list[IntentGateRecord] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            records.append(
                IntentGateRecord(
                    id=row["id"],
                    raw_text=row["raw_text"],
                    is_invoice_request=row["is_invoice_request"],
                    source="synthetic_extraction_dataset_v1",
                )
            )
    return records


def load_sufficiency_gate_dataset(path: Path = SYNTHETIC_EVAL_DATASET) -> list[SufficiencyGateRecord]:
    """Rows where is_invoice_request is True, with Intake Step 2 ground
    truth: sufficiency_label plus which CRITICAL_FIELDS are actually missing
    from the raw text (derived from removed_fields/naturally_missing_fields
    the same way sufficiency_label itself was recomputed -- see CHANGELOG.md
    2026-08-10). Rows where is_invoice_request is False are excluded:
    sufficiency doesn't apply to non-invoice text.

    Rows with ground_truth=null (the "nodata_*" family -- is_invoice_request
    is True but no target invoice was ever defined for them, since the text
    gives nothing to build one from) are special-cased: removed_fields and
    naturally_missing_fields are empty for these by construction (there's no
    ground_truth to remove fields FROM), NOT because nothing is missing --
    treating that as "nothing missing" silently mislabeled 54 rows as
    "complete" in the first recompute pass. See CHANGELOG.md 2026-08-10,
    "Layer 0 Step 2 -- ground_truth=null bug" (as CHANGELOG.md still calls it,
    predating this rename).
    """
    records: list[SufficiencyGateRecord] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if not row.get("is_invoice_request"):
                continue
            if row.get("ground_truth") is None:
                missing = set(CRITICAL_FIELDS)
            else:
                missing = (
                    set(row.get("removed_fields") or []) | set(row.get("naturally_missing_fields") or [])
                ) & set(CRITICAL_FIELDS)
            records.append(
                SufficiencyGateRecord(
                    id=row["id"],
                    raw_text=row["raw_text"],
                    sufficiency_label=row["sufficiency_label"],
                    missing_critical_fields=sorted(missing),
                    source="synthetic_extraction_dataset_v1",
                )
            )
    return records


def load_sroie() -> list[InvoiceRecord]:
    raise NotImplementedError("TODO: fix schema mismatch, see notebooks/datasets_searching.ipynb")


def load_enron_filtered() -> list[InvoiceRecord]:
    raise NotImplementedError("TODO: filter Enron email dataset for invoice/payment context")
