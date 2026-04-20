#!/usr/bin/env python3
"""Deep Research Skill Evaluation Harness.

Runs deep-research-skill against deep_research_bench queries via headless
Claude Code CLI, captures conversation traces and workspace artifacts.

Usage:
    python run_eval.py --tasks 1                    # single task
    python run_eval.py --tasks 1-10                 # range
    python run_eval.py --tasks 1,15,24 --model opus # explicit list, specific model
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
import pathlib

_HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(_HERE / "bench"))   # bench/utils for AIClient if ever needed
sys.path.insert(0, str(_HERE))             # so `import trace_processing` resolves

import trace_processing


QUERY_FILE = str(_HERE / "bench/data/prompt_data/query.jsonl")
PLUGIN_DIR = str(_HERE.parent)             # skill repo root — the skill is the containing repo
DEEP_RESEARCH_DIR = ".deep-research"       # CWD-relative by design; skill writes into CWD


def resolve_task_ids(tasks_arg: str) -> list[int]:
    """Resolve --tasks argument to a list of integer task IDs.

    Accepts:
      - Single ID:         "58"            -> [58]
      - Comma list:        "1,15,24"       -> [1, 15, 24]
      - Inclusive range:   "1-100"         -> [1, 2, ..., 100]

    Ranges and comma lists cannot be mixed (e.g. "1,2-5" is invalid).
    """
    s = tasks_arg.strip()
    if "-" in s and "," not in s:
        try:
            start_str, end_str = s.split("-", 1)
            start, end = int(start_str), int(end_str)
            if end < start:
                raise ValueError
            return list(range(start, end + 1))
        except ValueError:
            raise ValueError(f"Cannot parse task set: {tasks_arg!r}")

    try:
        return [int(x.strip()) for x in s.split(",")]
    except ValueError:
        raise ValueError(f"Cannot parse task set: {tasks_arg!r}")


def load_queries(query_file: str) -> dict[int, dict]:
    """Load benchmark queries from JSONL. Returns {id: {id, topic, language, prompt}}."""
    queries = {}
    with open(query_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            queries[entry["id"]] = entry
    return queries


_MKDIR_PATTERN = re.compile(r"mkdir\s+-p\s+\.deep-research/([\w][\w-]+)/")


def find_workspace_slug(conversation_path: str) -> str | None:
    """Extract the workspace slug from the first mkdir command in conversation.jsonl.

    The deep-research skill's first Bash call is always
    `mkdir -p .deep-research/<slug>/...`, so the first match is deterministic
    and sufficient. Returns None if no mkdir is found.
    """
    with open(conversation_path) as f:
        for line in f:
            match = _MKDIR_PATTERN.search(line)
            if match:
                return match.group(1)
    return None


def run_task(
    task_id: int,
    prompt: str,
    task_dir: str,
    timeout_minutes: int,
    model: str | None = None,
) -> dict:
    """Run a single deep-research task via claude -p.

    Never raises — any exception is caught and converted into a failure
    result dict. This contract lets the call site skip defensive guards.
    """
    os.makedirs(task_dir, exist_ok=True)

    conversation_path = os.path.join(task_dir, "conversation.jsonl")
    stderr_path = os.path.join(task_dir, "claude_stderr.log")

    start_time = time.time()
    slug = None
    result = None

    cmd = [
        "claude", "-p",
        "--permission-mode", "auto",
        "--output-format", "stream-json",
        "--verbose",
        "--plugin-dir", PLUGIN_DIR,
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.append(f"/deep-research {prompt}")

    try:
        with open(conversation_path, "w") as stdout_f, \
             open(stderr_path, "w") as stderr_f:
            proc = subprocess.Popen(
                cmd,
                stdout=stdout_f,
                stderr=stderr_f,
                env={**os.environ, "DEEP_RESEARCH_EVAL": "1"},
            )
            try:
                proc.wait(timeout=timeout_minutes * 60)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
                duration = time.time() - start_time
                result = _task_result(task_id, "failed", duration, 0, "timeout")
                return result

        duration = time.time() - start_time

        if proc.returncode != 0:
            result = _task_result(
                task_id, "failed", duration, 0,
                f"claude exited with code {proc.returncode}",
            )
            return result

        # Discover workspace
        slug = find_workspace_slug(conversation_path)

        if slug is None:
            result = _task_result(
                task_id, "failed", duration, 0,
                "Could not discover workspace directory",
            )
            return result

        # Copy workspace
        src_workspace = os.path.join(DEEP_RESEARCH_DIR, slug)
        dst_workspace = os.path.join(task_dir, "workspace")
        if os.path.exists(src_workspace):
            shutil.copytree(src_workspace, dst_workspace)

        # Extract report
        report_path = os.path.join(dst_workspace, "outputs", "report.md")
        if not os.path.exists(report_path):
            result = _task_result(
                task_id, "failed", duration, 0,
                "No report.md found in workspace outputs",
            )
            return result

        with open(report_path) as f:
            article_length = len(f.read())
        result = _task_result(task_id, "success", duration, article_length, None)
        return result

    except Exception as e:
        duration = time.time() - start_time
        result = _task_result(task_id, "failed", duration, 0, str(e))
        return result
    finally:
        if os.path.exists(conversation_path):
            if slug is None:
                slug = find_workspace_slug(conversation_path)
            trace_processing.process_trace(task_dir, slug)


def _task_result(
    task_id: int, status: str, duration: float, article_length: int, error: str | None,
) -> dict:
    return {
        "id": task_id,
        "status": status,
        "duration_seconds": round(duration, 1),
        "article_length": article_length,
        "error": error,
    }


def assemble_output_jsonl(run_dir: str, queries: dict[int, dict]) -> str:
    """Assemble output.jsonl from successful task results. Returns output file path."""
    output_path = os.path.join(run_dir, "output.jsonl")
    tasks_dir = os.path.join(run_dir, "tasks")

    with open(output_path, "w") as out_f:
        for task_dir_name in sorted(os.listdir(tasks_dir)):
            task_dir = os.path.join(tasks_dir, task_dir_name)
            result_path = os.path.join(task_dir, "result.json")

            if not os.path.exists(result_path):
                continue

            with open(result_path) as f:
                result = json.load(f)

            if result["status"] != "success":
                continue

            task_id = result["id"]
            report_path = os.path.join(task_dir, "workspace", "outputs", "report.md")

            with open(report_path) as f:
                article = f.read()

            entry = {
                "id": task_id,
                "prompt": queries[task_id]["prompt"],
                "article": article,
            }
            out_f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return output_path


def generate_summary(
    timestamp: str,
    task_set: str,
    timeout_minutes: int,
    results: list[dict],
) -> dict:
    """Generate summary.json content from task results."""
    succeeded = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] != "success"]

    return {
        "timestamp": timestamp,
        "task_set": task_set,
        "timeout_minutes": timeout_minutes,
        "total_tasks": len(results),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "failed_ids": [r["id"] for r in failed],
        "total_duration_seconds": round(sum(r["duration_seconds"] for r in results)),
    }



def _log(msg: str) -> None:
    """Print a progress message to stderr."""
    print(msg, file=sys.stderr, flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Run deep-research-skill against deep_research_bench queries.",
    )
    parser.add_argument(
        "--tasks", required=True,
        help="Task IDs: single (58), comma list (1,15,24), or range (1-100)",
    )
    parser.add_argument(
        "--model", default=None,
        help="Model to use for claude -p (e.g., 'sonnet', 'opus', 'claude-sonnet-4-6'). Uses Claude Code default if omitted.",
    )
    parser.add_argument(
        "--timeout", type=int, default=45,
        help="Per-task timeout in minutes (default: 45)",
    )
    args = parser.parse_args()

    # Resolve tasks
    task_ids = resolve_task_ids(args.tasks)
    queries = load_queries(QUERY_FILE)

    # Validate task IDs exist in queries
    missing_ids = [tid for tid in task_ids if tid not in queries]
    if missing_ids:
        _log(f"Error: task IDs not found in {QUERY_FILE}: {missing_ids}")
        sys.exit(1)

    # Create run directory
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    run_dir = os.path.join(str(_HERE / "runs"), timestamp)
    os.makedirs(os.path.join(run_dir, "tasks"), exist_ok=True)

    # Write config.json
    config = {
        "timestamp": timestamp,
        "task_set": args.tasks,
        "task_ids": task_ids,
        "model": args.model,
        "timeout_minutes": args.timeout,
    }
    with open(os.path.join(run_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)

    _log(f"Eval run: {timestamp}")
    _log(f"Tasks: {len(task_ids)} ({args.tasks}), "
         f"Timeout: {args.timeout}min")

    # Run tasks sequentially
    results = []
    for i, tid in enumerate(task_ids, start=1):
        task_dir = os.path.join(run_dir, "tasks", f"task_{tid:03d}")
        prompt = queries[tid]["prompt"]
        result = run_task(tid, prompt, task_dir, args.timeout, args.model)

        os.makedirs(task_dir, exist_ok=True)
        with open(os.path.join(task_dir, "result.json"), "w") as f:
            json.dump(result, f, indent=2)

        results.append(result)
        _log(f"[{i}/{len(task_ids)}] task_{tid:03d} "
             f"completed in {result['duration_seconds']:.0f}s ({result['status']})")

    # Assemble output JSONL
    _log("Assembling output.jsonl...")
    assemble_output_jsonl(run_dir, queries)

    # Generate summary
    summary = generate_summary(
        timestamp=timestamp,
        task_set=args.tasks,
        timeout_minutes=args.timeout,
        results=results,
    )
    with open(os.path.join(run_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    _log(f"\n{'='*50}")
    _log(f"Run complete: {run_dir}")
    _log(f"  Tasks: {summary['succeeded']}/{summary['total_tasks']} succeeded")
    if summary["failed_ids"]:
        _log(f"  Failed: {summary['failed_ids']}")
    _log(f"  Duration: {summary['total_duration_seconds']}s")
    _log(f"{'='*50}")


if __name__ == "__main__":
    main()
