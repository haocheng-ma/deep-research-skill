#!/usr/bin/env python3
"""Merge eval/runs/*/output.jsonl into the benchmark input file.

Walks every `eval/runs/<timestamp>/output.jsonl`, collapses entries by
task id with "latest timestamp wins" semantics, and writes the merged
result to `eval/bench/data/test_data/raw_data/deep-research-skill.jsonl`.

Because `run_eval.py` already filters output.jsonl to successful tasks
only, "latest" is automatically "latest successful".

Usage:
    python build_benchmark_input.py
"""

import glob
import json
import os
import pathlib


_HERE = pathlib.Path(__file__).parent

EVAL_RUNS_DIR = str(_HERE / "runs")
OUTPUT_PATH = str(_HERE / "bench/data/test_data/raw_data/deep-research-skill.jsonl")


def merge_eval_runs(eval_runs_dir: str) -> list[dict]:
    """Return merged entries sorted by integer id.

    Walks `<eval_runs_dir>/*/output.jsonl` in ascending timestamp order
    (directory name sorts lexically = chronologically because the format
    is `YYYY-MM-DDTHH-MM-SS`). Later entries overwrite earlier ones on
    matching id. Runs without an `output.jsonl` are silently skipped.
    """
    pattern = os.path.join(eval_runs_dir, "*", "output.jsonl")
    by_id: dict[int, dict] = {}
    for path in sorted(glob.glob(pattern)):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                by_id[entry["id"]] = entry
    return [by_id[k] for k in sorted(by_id.keys())]


def write_output(entries: list[dict], path: str) -> None:
    """Write entries to `path` as jsonl, preserving unicode verbatim."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    merged = merge_eval_runs(EVAL_RUNS_DIR)
    run_count = len(
        glob.glob(os.path.join(EVAL_RUNS_DIR, "*", "output.jsonl"))
    )
    write_output(merged, OUTPUT_PATH)
    print(f"{len(merged)} tasks merged from {run_count} runs → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
