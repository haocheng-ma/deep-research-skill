# Eval Harness

Local-only eval harness for `deep-research-skill`. Lives on the `eval` branch; never merges to master.

## Bootstrap

```bash
# from skill repo root, on the eval branch
cp .env.example .env
# edit .env to add real OPENROUTER_API_KEY and JINA_API_KEY
uv sync
git submodule update --init --recursive
```

## Running tests

```bash
uv run pytest
```

Covers skill tests (`tests/`), glue tests (`eval/tests/`), and bench tests (`eval/bench/tests/`).

## Running an eval

Shell-level env loading is required so subprocesses and `bench/run_benchmark.sh` see the keys:

```bash
set -a; source .env; set +a

# run the skill against benchmark queries
uv run python eval/run_eval.py --tasks 1,2,8

# merge per-run outputs into RACE input JSONL
uv run python eval/build_benchmark_input.py

# score via DeepResearch-Bench RACE (from bench/)
cd eval/bench && bash run_benchmark.sh --phase race
```

## Layout

- `eval/run_eval.py` — drive the skill against benchmark queries (uses `_HERE`-relative paths).
- `eval/build_benchmark_input.py` — merge per-run outputs into RACE input JSONL.
- `eval/trace_processing.py` — parse `.deep-research/` conversation traces.
- `eval/bench/` — submodule pinned to `deep_research_bench` at `eval-local`.
- `eval/runs/` — gitignored; per-run outputs land here.
