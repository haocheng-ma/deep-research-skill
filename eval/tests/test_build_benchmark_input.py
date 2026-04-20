"""Tests for build_benchmark_input.py."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import build_benchmark_input as bbi


def _write_run(root, timestamp, entries):
    """Create eval_runs/<timestamp>/output.jsonl with the given entries."""
    run_dir = root / "eval_runs" / timestamp
    run_dir.mkdir(parents=True)
    path = run_dir / "output.jsonl"
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


class TestMergeEvalRuns:
    def test_single_run_merges_cleanly(self, tmp_path):
        _write_run(tmp_path, "2026-04-19T00-00-00", [
            {"id": 1, "prompt": "p1", "article": "a1"},
            {"id": 2, "prompt": "p2", "article": "a2"},
        ])
        merged = bbi.merge_eval_runs(str(tmp_path / "eval_runs"))
        assert [e["id"] for e in merged] == [1, 2]
        assert merged[0]["article"] == "a1"

    def test_latest_run_wins_on_duplicate_id(self, tmp_path):
        _write_run(tmp_path, "2026-04-19T00-00-00", [
            {"id": 5, "prompt": "p5", "article": "old"},
        ])
        _write_run(tmp_path, "2026-04-19T12-00-00", [
            {"id": 5, "prompt": "p5", "article": "new"},
        ])
        merged = bbi.merge_eval_runs(str(tmp_path / "eval_runs"))
        assert len(merged) == 1
        assert merged[0]["article"] == "new"

    def test_output_sorted_by_integer_id(self, tmp_path):
        _write_run(tmp_path, "2026-04-19T00-00-00", [
            {"id": 10, "prompt": "p10", "article": "a10"},
            {"id": 2,  "prompt": "p2",  "article": "a2"},
            {"id": 1,  "prompt": "p1",  "article": "a1"},
        ])
        merged = bbi.merge_eval_runs(str(tmp_path / "eval_runs"))
        assert [e["id"] for e in merged] == [1, 2, 10]

    def test_run_without_output_jsonl_is_skipped(self, tmp_path):
        (tmp_path / "eval_runs" / "2026-04-19T00-00-00").mkdir(parents=True)
        _write_run(tmp_path, "2026-04-19T12-00-00", [
            {"id": 1, "prompt": "p1", "article": "a1"},
        ])
        merged = bbi.merge_eval_runs(str(tmp_path / "eval_runs"))
        assert [e["id"] for e in merged] == [1]

    def test_empty_eval_runs_dir_returns_empty(self, tmp_path):
        (tmp_path / "eval_runs").mkdir()
        assert bbi.merge_eval_runs(str(tmp_path / "eval_runs")) == []


class TestWriteOutput:
    def test_preserves_unicode(self, tmp_path):
        out = tmp_path / "deep-research-skill.jsonl"
        entries = [{"id": 1, "prompt": "中文提示", "article": "内容"}]
        bbi.write_output(entries, str(out))
        text = out.read_text(encoding="utf-8")
        assert "中文提示" in text
        assert "\\u" not in text  # no escape sequences

    def test_one_entry_per_line(self, tmp_path):
        out = tmp_path / "deep-research-skill.jsonl"
        entries = [
            {"id": 1, "prompt": "p1", "article": "a1"},
            {"id": 2, "prompt": "p2", "article": "a2"},
        ]
        bbi.write_output(entries, str(out))
        lines = out.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0])["id"] == 1
