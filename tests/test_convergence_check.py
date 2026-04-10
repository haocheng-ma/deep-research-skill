"""Tests for convergence_check.py"""

import json
import subprocess
import sys
import tempfile
import os

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "skills", "deep-research", "scripts", "convergence_check.py")


def run_script(workflow_state: dict) -> dict:
    """Write workflow_state to a temp file, run the script, return parsed output."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(workflow_state, f)
        f.flush()
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, tmp_path],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"Script failed: {result.stderr}"
        return json.loads(result.stdout)
    finally:
        os.unlink(tmp_path)


def run_script_expect_error(workflow_state_content: str) -> str:
    """Write raw string to temp file, run script, return stderr."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(workflow_state_content)
        f.flush()
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, tmp_path],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, f"Script should have failed but returned: {result.stdout}"
        return result.stderr
    finally:
        os.unlink(tmp_path)


def make_eval_task(iteration, section_gaps, research_complete=False):
    """Helper to create a completed evaluate task."""
    return {
        "id": f"eval-{iteration}",
        "type": "evaluate",
        "status": "completed",
        "blocked_by": [] if iteration == 1 else [f"gather-{iteration - 1}"],
        "iteration": iteration,
        "result": {
            "status": "done",
            "research_complete": research_complete,
            "section_gaps": section_gaps,
            "suggested_queries": [],
            "priority_section": "none",
            "knowledge_gap": "none",
            "outline_evolution": None,
            "summary": f"Iteration {iteration}",
        },
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:01:00Z",
    }


def make_gather_task(iteration, sources_added):
    """Helper to create a completed gather task."""
    return {
        "id": f"gather-{iteration}",
        "type": "gather",
        "status": "completed",
        "blocked_by": [f"eval-{iteration}"],
        "result": {
            "status": "done",
            "sources_added": sources_added,
            "summary": f"Gather {iteration}",
        },
        "started_at": "2026-01-01T00:02:00Z",
        "completed_at": "2026-01-01T00:03:00Z",
    }


def test_first_iteration_gaps_remain():
    """First eval with gaps: actionable gaps remain, no unfillable gaps."""
    state = {
        "workflow_id": "test-1",
        "tasks": [
            make_eval_task(1, {"Benchmarks": "No data"}),
        ],
    }
    out = run_script(state)
    assert out["actionable_gaps_remain"] is True
    assert out["known_unfillable_gaps"] == []
    assert out["forced_completion"] is False


def test_gap_persists_with_sources_not_unfillable():
    """Same gap in 2 consecutive evals, but gatherer found sources — NOT unfillable."""
    state = {
        "workflow_id": "test-2",
        "tasks": [
            make_eval_task(1, {"Benchmarks": "No data"}),
            make_gather_task(1, [{"id": 1, "title": "P1", "section": "Benchmarks"}]),
            make_eval_task(2, {"Benchmarks": "Still thin"}),
        ],
    }
    out = run_script(state)
    assert out["actionable_gaps_remain"] is True
    assert out["known_unfillable_gaps"] == []


def test_gap_persists_without_sources_is_unfillable():
    """Same gap in 2 consecutive evals, gatherer found 0 sources — unfillable."""
    state = {
        "workflow_id": "test-3",
        "tasks": [
            make_eval_task(1, {"Benchmarks": "No data"}),
            make_gather_task(1, []),
            make_eval_task(2, {"Benchmarks": "Still no data"}),
        ],
    }
    out = run_script(state)
    assert "Benchmarks" in out["known_unfillable_gaps"]


def test_all_gaps_unfillable_forces_completion():
    """When every remaining gap is unfillable, forced_completion is True."""
    state = {
        "workflow_id": "test-4",
        "tasks": [
            make_eval_task(1, {"Benchmarks": "No data"}),
            make_gather_task(1, []),
            make_eval_task(2, {"Benchmarks": "Still no data"}),
        ],
    }
    out = run_script(state)
    assert out["forced_completion"] is True
    assert out["actionable_gaps_remain"] is False
    assert "Benchmarks" in out["known_unfillable_gaps"]


def test_iteration_cap_forces_completion():
    """At iteration >= 10, forced completion regardless of gaps."""
    state = {
        "workflow_id": "test-5",
        "tasks": [
            make_eval_task(10, {"Benchmarks": "No data"}),
        ],
    }
    out = run_script(state)
    assert out["forced_completion"] is True
    assert "Iteration cap" in out["reason"]


def test_research_complete_no_gaps():
    """When research_complete is true and no gaps: no actionable gaps, not forced."""
    state = {
        "workflow_id": "test-6",
        "tasks": [
            make_eval_task(1, {"Benchmarks": "No data"}),
            make_gather_task(1, [{"id": 1, "title": "P1", "section": "Benchmarks"}]),
            make_eval_task(2, {}, research_complete=True),
        ],
    }
    out = run_script(state)
    assert out["actionable_gaps_remain"] is False
    assert out["forced_completion"] is False


def test_mixed_gaps_some_unfillable():
    """One gap is unfillable, another is actionable — actionable gaps remain."""
    state = {
        "workflow_id": "test-7",
        "tasks": [
            make_eval_task(1, {"Benchmarks": "No data", "Limitations": "Missing"}),
            make_gather_task(1, [{"id": 1, "title": "P1", "section": "Limitations"}]),
            make_eval_task(2, {"Benchmarks": "Still no data", "Limitations": "Thin"}),
            make_gather_task(2, []),
            make_eval_task(3, {"Benchmarks": "Still no data"}),
        ],
    }
    out = run_script(state)
    assert "Benchmarks" in out["known_unfillable_gaps"]
    # Benchmarks persisted 3 evals with no sources across 2 gathers — unfillable
    # But Limitations was dropped by eval-3, so no remaining actionable gaps?
    # Actually eval-3 has only Benchmarks, which is unfillable → forced_completion
    assert out["actionable_gaps_remain"] is False


def test_outline_evolution_resets_convergence():
    """When a section is renamed between iterations, convergence resets."""
    state = {
        "workflow_id": "test-8",
        "tasks": [
            make_eval_task(1, {"Performance Benchmarks": "No data"}),
            make_gather_task(1, []),
            # Outline evolution renamed "Performance Benchmarks" to "Evaluation Metrics"
            make_eval_task(2, {"Evaluation Metrics": "No data"}),
        ],
    }
    out = run_script(state)
    # Different key names — convergence counter resets
    assert "Performance Benchmarks" not in out["known_unfillable_gaps"]
    assert "Evaluation Metrics" not in out["known_unfillable_gaps"]
    assert out["actionable_gaps_remain"] is True


def test_research_complete_with_remaining_gaps():
    """research_complete: true but section_gaps non-empty — actionable gaps remain.
    The director's false-completion verification would catch this."""
    state = {
        "workflow_id": "test-9",
        "tasks": [
            make_eval_task(1, {"Benchmarks": "No data"}),
            make_gather_task(1, [{"id": 1, "title": "P1", "section": "Benchmarks"}]),
            make_eval_task(2, {"Benchmarks": "Still thin"}, research_complete=True),
        ],
    }
    out = run_script(state)
    # Evaluator claims complete but gaps exist — script reports actionable gaps
    assert out["actionable_gaps_remain"] is True
    assert out["forced_completion"] is False


def test_substring_match_false_positive():
    """A gap key that is a substring of an unrelated source section — false positive.
    This is a known limitation: 'Data' matches '### 5.2 Data Quality' even if
    the gap was about '### 3.1 Data Collection'. For convergence checking,
    false positives (thinking sources were found when they weren't exactly for
    this section) are safer than false negatives (incorrectly marking as unfillable)."""
    state = {
        "workflow_id": "test-10",
        "tasks": [
            make_eval_task(1, {"Data": "No data collection info"}),
            make_gather_task(1, [{"id": 1, "title": "P1", "section": "### 5.2 Data Quality"}]),
            make_eval_task(2, {"Data": "Still missing collection info"}),
        ],
    }
    out = run_script(state)
    # "Data" substring-matches "### 5.2 Data Quality", so the script thinks
    # sources were found — gap is NOT marked unfillable (false positive).
    # This is the safe direction: we keep searching rather than giving up.
    assert "Data" not in out["known_unfillable_gaps"]
    assert out["actionable_gaps_remain"] is True


def test_malformed_json_returns_error():
    """Malformed workflow_state.json triggers non-zero exit."""
    stderr = run_script_expect_error("{invalid json")
    assert "malformed" in stderr.lower() or "json" in stderr.lower()


def test_no_eval_tasks_returns_error():
    """No completed eval tasks triggers non-zero exit."""
    state = {
        "workflow_id": "test-9",
        "tasks": [],
    }
    stderr_result = None
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(state, f)
        f.flush()
        tmp_path = f.name
    try:
        result = subprocess.run(
            [sys.executable, SCRIPT, tmp_path],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode != 0, f"Should fail with no eval tasks: {result.stdout}"
        assert "no completed eval" in result.stderr.lower()
    finally:
        os.unlink(tmp_path)
