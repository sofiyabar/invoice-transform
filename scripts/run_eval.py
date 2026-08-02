"""CLI entry point: run the full eval pipeline end-to-end.

TODO: parse args (corpus size, --smoke), call evals.runner.run(), print summary.
"""

from evals.runner import run

if __name__ == "__main__":
    run()
