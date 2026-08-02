"""Generate synthetic (raw_text, ground_truth) invoice pairs via Claude.

TODO: implement generation loop over (segment, doc_type) combinations,
producing InvoiceRecord instances with parallel ground truth for Layer 3
segmentation.
"""

from data.schema import DocType, InvoiceRecord, Segment


def generate_synthetic_record(segment: Segment, doc_type: DocType) -> InvoiceRecord:
    raise NotImplementedError("TODO: call Anthropic to produce text + parallel ground truth JSON")
