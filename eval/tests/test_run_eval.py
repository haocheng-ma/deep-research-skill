"""Tests for the evaluation harness."""

import json
import os
import time
import pytest
from unittest.mock import patch, call

# Adjust path so we can import run_eval from the project root
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import run_eval


class TestResolveTaskIds:
    def test_single_id(self):
        assert run_eval.resolve_task_ids("58") == [58]

    def test_comma_separated(self):
        assert run_eval.resolve_task_ids("3,7,12") == [3, 7, 12]

    def test_comma_separated_with_whitespace(self):
        assert run_eval.resolve_task_ids("3, 7 , 12") == [3, 7, 12]

    def test_range(self):
        assert run_eval.resolve_task_ids("1-5") == [1, 2, 3, 4, 5]

    def test_range_single(self):
        assert run_eval.resolve_task_ids("7-7") == [7]

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Cannot parse task set"):
            run_eval.resolve_task_ids("bogus_name")

    def test_reversed_range_raises(self):
        with pytest.raises(ValueError, match="Cannot parse task set"):
            run_eval.resolve_task_ids("10-5")


class TestLoadQueries:
    def test_load_queries(self, tmp_path):
        qfile = tmp_path / "query.jsonl"
        qfile.write_text(
            '{"id": 1, "topic": "Finance", "language": "zh", "prompt": "test prompt 1"}\n'
            '{"id": 58, "topic": "Science", "language": "en", "prompt": "test prompt 58"}\n'
        )
        queries = run_eval.load_queries(str(qfile))
        assert len(queries) == 2
        assert queries[1]["prompt"] == "test prompt 1"
        assert queries[58]["language"] == "en"

    def test_load_queries_empty(self, tmp_path):
        qfile = tmp_path / "query.jsonl"
        qfile.write_text("")
        queries = run_eval.load_queries(str(qfile))
        assert queries == {}


class TestFindWorkspaceSlug:
    def test_finds_slug_from_mkdir(self, tmp_path):
        """Primary path: extracts slug from the first mkdir -p command."""
        conv = tmp_path / "conversation.jsonl"
        conv.write_text(
            '{"type":"tool_use","tool":"Bash","input":{"command":"mkdir -p .deep-research/sovereign-wealth-funds/workspace/sources .deep-research/sovereign-wealth-funds/outputs"}}\n'
            '{"type":"assistant","message":"Starting research..."}\n'
        )
        assert run_eval.find_workspace_slug(str(conv)) == "sovereign-wealth-funds"

    def test_returns_none_when_no_match(self, tmp_path):
        conv = tmp_path / "conversation.jsonl"
        conv.write_text('{"type":"assistant","message":"Hello"}\n')
        assert run_eval.find_workspace_slug(str(conv)) is None

    def test_handles_slug_with_digits_and_underscores(self, tmp_path):
        conv = tmp_path / "conversation.jsonl"
        conv.write_text(
            '{"msg": "mkdir -p .deep-research/k8s_autoscaling-2025/workspace"}\n'
        )
        assert run_eval.find_workspace_slug(str(conv)) == "k8s_autoscaling-2025"


class TestAssembleOutputJsonl:
    def test_assembles_successful_tasks(self, tmp_path):
        run_dir = tmp_path / "run"
        tasks_dir = run_dir / "tasks"

        t1 = tasks_dir / "task_001"
        t1.mkdir(parents=True)
        (t1 / "result.json").write_text('{"id": 1, "status": "success"}')
        report_dir = t1 / "workspace" / "outputs"
        report_dir.mkdir(parents=True)
        (report_dir / "report.md").write_text("# Report about finance")

        t2 = tasks_dir / "task_058"
        t2.mkdir(parents=True)
        (t2 / "result.json").write_text('{"id": 58, "status": "failed"}')

        queries = {
            1: {"id": 1, "prompt": "finance prompt", "topic": "Finance", "language": "zh"},
            58: {"id": 58, "prompt": "science prompt", "topic": "Science", "language": "en"},
        }

        output_path = run_eval.assemble_output_jsonl(str(run_dir), queries)

        assert os.path.exists(output_path)
        with open(output_path) as f:
            lines = [json.loads(l) for l in f if l.strip()]

        assert len(lines) == 1
        assert lines[0]["id"] == 1
        assert lines[0]["prompt"] == "finance prompt"
        assert lines[0]["article"] == "# Report about finance"

    def test_empty_when_all_failed(self, tmp_path):
        run_dir = tmp_path / "run"
        tasks_dir = run_dir / "tasks"

        t1 = tasks_dir / "task_001"
        t1.mkdir(parents=True)
        (t1 / "result.json").write_text('{"id": 1, "status": "failed"}')

        queries = {1: {"id": 1, "prompt": "p", "topic": "T", "language": "en"}}
        output_path = run_eval.assemble_output_jsonl(str(run_dir), queries)

        with open(output_path) as f:
            assert f.read().strip() == ""


class TestGenerateSummary:
    def test_generates_summary(self):
        results = [
            {"id": 1, "status": "success", "duration_seconds": 300, "article_length": 5000, "error": None},
            {"id": 58, "status": "failed", "duration_seconds": 120, "article_length": 0, "error": "timeout"},
            {"id": 68, "status": "success", "duration_seconds": 450, "article_length": 8000, "error": None},
        ]
        summary = run_eval.generate_summary(
            timestamp="2026-04-17T14:30:00",
            task_set="1,58,68",
            timeout_minutes=45,
            results=results,
        )
        assert summary["total_tasks"] == 3
        assert summary["succeeded"] == 2
        assert summary["failed"] == 1
        assert summary["failed_ids"] == [58]
        assert summary["total_duration_seconds"] == 870
        # Positive shape:
        assert set(summary.keys()) == {
            "timestamp", "task_set", "timeout_minutes",
            "total_tasks", "succeeded", "failed", "failed_ids",
            "total_duration_seconds",
        }


class TestCliArgparse:
    def test_tasks_required(self, monkeypatch, capsys):
        """Running main() with no --tasks exits with argparse error (in-process)."""
        monkeypatch.setattr(sys, "argv", ["run_eval.py"])
        with pytest.raises(SystemExit) as exc:
            run_eval.main()
        assert exc.value.code == 2
        captured = capsys.readouterr()
        assert "--tasks" in captured.err


class TestRunTaskEnv:
    def test_run_task_sets_eval_env_var(self, tmp_path, monkeypatch):
        """run_task must propagate DEEP_RESEARCH_EVAL=1 to the claude subprocess."""
        monkeypatch.setenv("PATH", "/usr/bin")  # pin a known inherited var
        task_dir = tmp_path / "task_001"

        captured = {}

        class FakeProc:
            returncode = 1  # non-zero so run_task short-circuits before workspace discovery

            def wait(self, timeout):
                return 1

        def fake_popen(cmd, stdout, stderr, env):
            captured["cmd"] = cmd
            captured["env"] = env
            return FakeProc()

        monkeypatch.setattr(run_eval.subprocess, "Popen", fake_popen)

        result = run_eval.run_task(
            task_id=1,
            prompt="test prompt",
            task_dir=str(task_dir),
            timeout_minutes=1,
            model=None,
        )

        assert captured["env"]["DEEP_RESEARCH_EVAL"] == "1"
        # Inherited env is preserved (not a freshly-built empty dict):
        assert captured["env"].get("PATH") == "/usr/bin"
        assert result["status"] == "failed"  # sanity: the fake proc's non-zero exit propagates
