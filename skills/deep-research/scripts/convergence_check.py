#!/usr/bin/env python3
"""Convergence check for deep-research workflow.

Pure function: reads workflow_state.json, computes convergence state.
Does not modify any files or make any decisions beyond convergence detection.

Usage: python3 convergence_check.py <path_to_workflow_state.json>
Output: JSON to stdout
Errors: Non-zero exit with message to stderr
"""

import json
import sys


def load_workflow_state(path: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Malformed workflow_state.json: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        print(f"File not found: {path}", file=sys.stderr)
        sys.exit(1)


def get_completed_evals(tasks: list) -> list:
    """Return completed evaluate tasks sorted by iteration."""
    evals = [
        t for t in tasks
        if t.get("type") == "evaluate" and t.get("status") == "completed"
    ]
    evals.sort(key=lambda t: t.get("iteration", 0))
    return evals


def get_gather_between(tasks: list, eval_before: dict, eval_after: dict) -> dict | None:
    """Find the completed gather task between two consecutive evals."""
    before_id = eval_before["id"]
    for t in tasks:
        if (
            t.get("type") == "gather"
            and t.get("status") == "completed"
            and before_id in t.get("blocked_by", [])
        ):
            return t
    return None


def sources_added_for_section(gather_task: dict | None, section_name: str) -> bool:
    """Check if the gather task added any sources for the given section."""
    if gather_task is None or gather_task.get("result") is None:
        return False
    sources = gather_task["result"].get("sources_added", [])
    for source in sources:
        source_section = source.get("section", "")
        # Match if the section name appears in the source's section field.
        # Source sections use outline heading format ("### 3.1 Architecture")
        # while section_gaps keys use descriptive names ("Architecture").
        # We check if the gap key is a substring of the source section.
        if section_name.lower() in source_section.lower():
            return True
    return False


def compute_convergence(state: dict) -> dict:
    tasks = state.get("tasks", [])
    evals = get_completed_evals(tasks)

    if not evals:
        print("No completed evaluate tasks found in workflow_state.json", file=sys.stderr)
        sys.exit(1)

    latest_eval = evals[-1]
    latest_result = latest_eval.get("result", {})
    latest_iteration = latest_eval.get("iteration", 1)

    # Iteration cap check
    if latest_iteration >= 10:
        all_gaps = list(latest_result.get("section_gaps", {}).keys())
        return {
            "actionable_gaps_remain": False,
            "known_unfillable_gaps": all_gaps,
            "forced_completion": True,
            "reason": "Iteration cap reached (>= 10)",
        }

    # Always walk consecutive eval pairs to find unfillable gaps.
    # This must run before checking research_complete, because the
    # false-completion verification calls this script to get the
    # known_unfillable_gaps list (computed from the full task chain).
    known_unfillable = set()

    for i in range(1, len(evals)):
        prev_eval = evals[i - 1]
        curr_eval = evals[i]

        prev_gaps = set(prev_eval.get("result", {}).get("section_gaps", {}).keys())
        curr_gaps = set(curr_eval.get("result", {}).get("section_gaps", {}).keys())

        # Persistent gaps: appear in both consecutive evals
        persistent = prev_gaps & curr_gaps

        if persistent:
            gather = get_gather_between(tasks, prev_eval, curr_eval)
            for section in persistent:
                if not sources_added_for_section(gather, section):
                    known_unfillable.add(section)

    # Determine actionable gaps: current gaps that are NOT known unfillable
    current_gaps = set(latest_result.get("section_gaps", {}).keys())
    actionable = current_gaps - known_unfillable

    # Research complete with no remaining gaps
    if latest_result.get("research_complete") and not current_gaps:
        return {
            "actionable_gaps_remain": False,
            "known_unfillable_gaps": sorted(known_unfillable),
            "forced_completion": False,
            "reason": None,
        }

    # All remaining gaps are unfillable — force completion
    if not actionable and current_gaps:
        return {
            "actionable_gaps_remain": False,
            "known_unfillable_gaps": sorted(known_unfillable),
            "forced_completion": True,
            "reason": "All persistent gaps are unfillable after 2+ iterations with 0 new sources",
        }

    return {
        "actionable_gaps_remain": bool(actionable),
        "known_unfillable_gaps": sorted(known_unfillable),
        "forced_completion": False,
        "reason": None,
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: convergence_check.py <workflow_state.json>", file=sys.stderr)
        sys.exit(1)

    state = load_workflow_state(sys.argv[1])
    result = compute_convergence(state)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
