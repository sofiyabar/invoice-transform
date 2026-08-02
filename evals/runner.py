"""Orchestrates a full eval run: generator -> Layer 1-5 -> saved metrics_dict.

TODO: implement pipeline:
1. Load InvoiceRecord corpus (data/loaders.py, data/synth_generate.py)
2. Call generator.base_generator.generate() per record, capture latency
3. Score via evals/layer1_field.py .. layer5_statistics.py
4. Write timestamped metrics_dict.json to eval_runs/
"""


def run(smoke: bool = False) -> dict:
    raise NotImplementedError("TODO: implement end-to-end eval run")
