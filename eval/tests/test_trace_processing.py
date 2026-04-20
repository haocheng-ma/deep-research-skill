"""Tests for trace processing (slim trace + structured summary)."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import trace_processing


class TestSlimDropRules:
    def test_slim_drops_task_progress(self):
        event = {"type": "system", "subtype": "task_progress", "task_id": "abc123",
                 "description": "Reading outline.md", "uuid": "uuid-1", "session_id": "sess-1"}
        assert trace_processing.slim_event(event, workspace_slug=None) is None

    def test_slim_drops_task_started(self):
        event = {"type": "system", "subtype": "task_started", "task_id": "abc123",
                 "description": "evaluate research", "task_type": "local_agent", "uuid": "uuid-2", "session_id": "sess-1"}
        assert trace_processing.slim_event(event, workspace_slug=None) is None

    def test_slim_drops_task_notification(self):
        event = {"type": "system", "subtype": "task_notification", "task_id": "abc123",
                 "status": "completed", "summary": "evaluate research", "uuid": "uuid-3", "session_id": "sess-1"}
        assert trace_processing.slim_event(event, workspace_slug=None) is None

    def test_slim_drops_rate_limit(self):
        event = {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed",
                 "resetsAt": 1775800800}, "uuid": "uuid-4", "session_id": "sess-1"}
        assert trace_processing.slim_event(event, workspace_slug=None) is None


class TestSlimTrimRules:
    def test_slim_trims_init(self):
        event = {
            "type": "system",
            "subtype": "init",
            "model": "claude-opus-4-5",
            "cwd": "/home/user",
            "session_id": "abc123",
            "permissionMode": "default",
            "plugins": [],
            "tools": ["bash", "read"],
            "mcp_servers": {"server": {}},
            "slash_commands": ["/foo"],
            "skills": ["skill_a"],
            "agents": ["agent_b"],
        }
        result = trace_processing.slim_event(event, workspace_slug=None)
        assert result is not None
        # Kept keys
        assert result["model"] == "claude-opus-4-5"
        assert result["cwd"] == "/home/user"
        assert result["session_id"] == "abc123"
        assert result["permissionMode"] == "default"
        assert result["plugins"] == []
        # Dropped keys
        assert "tools" not in result
        assert "mcp_servers" not in result
        assert "slash_commands" not in result
        assert "skills" not in result
        assert "agents" not in result

    def test_slim_trims_hook_response(self):
        event = {
            "type": "system",
            "subtype": "hook_response",
            "hook_name": "pre_commit",
            "exit_code": 0,
            "outcome": "success",
            "output": "All checks passed.\n",
            "stdout": "running linter...\n",
            "extra_field": "should be dropped",
        }
        result = trace_processing.slim_event(event, workspace_slug=None)
        assert result is not None
        assert result["hook_name"] == "pre_commit"
        assert result["exit_code"] == 0
        assert result["outcome"] == "success"
        # output/stdout replaced with byte lengths
        assert result["output"] == len("All checks passed.\n")
        assert result["stdout"] == len("running linter...\n")
        assert "extra_field" not in result

    def test_slim_drops_tool_use_result(self):
        event = {
            "type": "user",
            "tool_use_result": {"id": "tool_abc", "content": "some output"},
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool_abc",
                        "content": "some output",
                    }
                ],
            },
        }
        result = trace_processing.slim_event(event, workspace_slug=None)
        assert result is not None
        assert "tool_use_result" not in result
        # message.content is untouched
        assert result["message"]["content"][0]["content"] == "some output"

    def test_slim_replaces_workspace_reads(self):
        workspace_slug = "my-task-slug"
        # 73 bytes of content
        content_str = "a" * 73
        tool_id = "toolu_read_ws"
        event = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": content_str,
                    }
                ],
            },
        }
        tool_names = {tool_id: "Read"}
        tool_inputs = {tool_id: {"file_path": f"/home/user/.deep-research/{workspace_slug}/sources/1.md"}}
        result = trace_processing.slim_event(
            event,
            workspace_slug=workspace_slug,
            tool_names=tool_names,
            tool_inputs=tool_inputs,
        )
        assert result is not None
        content_block = result["message"]["content"][0]
        assert content_block["content"] == "[see workspace/sources/1.md, 73B]"

    def test_slim_keeps_non_workspace_reads(self):
        workspace_slug = "my-task-slug"
        content_str = "hello world"
        tool_id = "toolu_read_other"
        event = {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": content_str,
                    }
                ],
            },
        }
        tool_names = {tool_id: "Read"}
        tool_inputs = {tool_id: {"file_path": "/home/user/other_dir/file.txt"}}
        result = trace_processing.slim_event(
            event,
            workspace_slug=workspace_slug,
            tool_names=tool_names,
            tool_inputs=tool_inputs,
        )
        assert result is not None
        content_block = result["message"]["content"][0]
        assert content_block["content"] == content_str


class TestSlimKeepAndMerge:
    def test_slim_keeps_assistant_events(self):
        event = {
            "type": "assistant",
            "message": {
                "id": "msg_001",
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "Let me reason..."},
                    {"type": "text", "text": "Here is my answer."},
                ],
            },
        }
        result = trace_processing.slim_event(event, workspace_slug=None)
        assert result is not None
        assert result["type"] == "assistant"
        assert len(result["message"]["content"]) == 2
        assert result["message"]["content"][0]["type"] == "thinking"
        assert result["message"]["content"][1]["type"] == "text"

    def test_slim_keeps_web_tool_results(self):
        tool_id = "toolu_web_search"
        event = {
            "type": "user",
            "tool_use_result": {"id": tool_id, "content": "search results"},
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_id,
                        "content": "search results",
                    }
                ],
            },
        }
        result = trace_processing.slim_event(event, workspace_slug=None)
        assert result is not None
        assert "tool_use_result" not in result
        assert result["message"]["content"][0]["content"] == "search results"

    def test_slim_merges_streaming_duplicates(self):
        # 3 consecutive assistant events with same message.id → 1 merged event with 3 content blocks
        events = [
            {
                "type": "assistant",
                "message": {
                    "id": "msg_stream",
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "step 1"}],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "id": "msg_stream",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "part 1"}],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "id": "msg_stream",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "part 2"}],
                },
            },
        ]
        merged = trace_processing.merge_assistant_events(events)
        assert len(merged) == 1
        assert merged[0]["message"]["id"] == "msg_stream"
        content = merged[0]["message"]["content"]
        assert len(content) == 3
        assert content[0]["type"] == "thinking"
        assert content[1]["text"] == "part 1"
        assert content[2]["text"] == "part 2"

    def test_slim_merges_non_consecutive_events(self):
        # assistant(msg_1, tool_use_1) → user(tool_result) → assistant(msg_1, tool_use_2)
        # → merged to 1 assistant (with 2 content blocks) + 1 user
        events = [
            {
                "type": "assistant",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash"}],
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "output"}
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_2", "name": "Read"}],
                },
            },
        ]
        merged = trace_processing.merge_assistant_events(events)
        assert len(merged) == 2
        # First is the merged assistant event
        assistant = merged[0]
        assert assistant["type"] == "assistant"
        assert assistant["message"]["id"] == "msg_1"
        content = assistant["message"]["content"]
        assert len(content) == 2
        assert content[0]["id"] == "toolu_1"
        assert content[1]["id"] == "toolu_2"
        # Second is the user event
        user = merged[1]
        assert user["type"] == "user"


# ---------------------------------------------------------------------------
# Task 4: Summary Extraction — Token Usage
# ---------------------------------------------------------------------------


class TestSummaryTokenUsage:
    def test_summary_token_usage(self):
        """2 events sharing msg_1 + 1 event with msg_2 + 1 user event.
        Totals must NOT double-count msg_1. by_turn has 2 entries."""
        events = [
            # First event for msg_1
            {
                "type": "assistant",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hello"}],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "cache_read_input_tokens": 50,
                        "cache_creation_input_tokens": 10,
                    },
                },
            },
            # Second event for msg_1 — same usage, should NOT be counted again
            {
                "type": "assistant",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {}}],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "cache_read_input_tokens": 50,
                        "cache_creation_input_tokens": 10,
                    },
                },
            },
            # User event — should not contribute to token counts
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "toolu_1", "content": "done"}
                    ],
                },
            },
            # New turn: msg_2
            {
                "type": "assistant",
                "message": {
                    "id": "msg_2",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Done"}],
                    "usage": {
                        "input_tokens": 200,
                        "output_tokens": 30,
                        "cache_read_input_tokens": 0,
                        "cache_creation_input_tokens": 5,
                    },
                },
            },
        ]

        result = trace_processing.extract_summary(events)

        # Check top-level structure
        assert "token_usage" in result
        assert "tool_sequence" in result
        assert "errors" in result

        tu = result["token_usage"]
        assert tu["total_input"] == 300       # 100 + 200 (msg_1 not doubled)
        assert tu["total_output"] == 50       # 20 + 30
        assert tu["total_cache_read"] == 50   # 50 + 0
        assert tu["total_cache_creation"] == 15  # 10 + 5

        by_turn = tu["by_turn"]
        assert len(by_turn) == 2
        # Turn 1 = msg_1
        t1 = by_turn[0]
        assert t1["turn"] == 1
        assert t1["input_tokens"] == 100
        assert t1["output_tokens"] == 20
        assert t1["cache_read_input_tokens"] == 50
        assert t1["cache_creation_input_tokens"] == 10
        # Turn 2 = msg_2
        t2 = by_turn[1]
        assert t2["turn"] == 2
        assert t2["input_tokens"] == 200
        assert t2["output_tokens"] == 30



# ---------------------------------------------------------------------------
# Task 5: Tool Sequence and Parent Tracking
# ---------------------------------------------------------------------------


class TestSummaryToolSequence:
    def test_summary_tool_sequence(self):
        """Bash + Write calls with results; verify ordered sequence, summaries, success=True, parent=None."""
        events = [
            {
                "type": "assistant",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_bash1",
                            "name": "Bash",
                            "input": {"command": "mkdir -p /tmp/test"},
                        }
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 5,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_bash1",
                            "content": "",
                        }
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_write1",
                            "name": "Write",
                            "input": {"file_path": "/tmp/test/hello.txt", "content": "hello world"},
                        }
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 5,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_write1",
                            "content": "File written",
                        }
                    ],
                },
            },
        ]

        result = trace_processing.extract_summary(events)
        seq = result["tool_sequence"]

        assert len(seq) == 2

        bash_entry = seq[0]
        assert bash_entry["turn"] == 1
        assert bash_entry["tool"] == "Bash"
        assert bash_entry["summary"] == "mkdir -p /tmp/test"
        assert bash_entry["success"] is True
        assert bash_entry["parent"] is None

        write_entry = seq[1]
        assert write_entry["turn"] == 1
        assert write_entry["tool"] == "Write"
        assert "/tmp/test/hello.txt" in write_entry["summary"]
        assert write_entry["success"] is True
        assert write_entry["parent"] is None

    def test_summary_subagent_parent_tracking(self):
        """Agent dispatch (parent=None) + subagent WebFetch (parent=toolu_agent1).
        len(seq) == 2, NOT 3 (user events don't add entries)."""
        events = [
            {
                "type": "assistant",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_agent1",
                            "name": "Agent",
                            "input": {"description": "Fetch some data"},
                        }
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 5,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                },
            },
            {
                "type": "assistant",
                "parent_tool_use_id": "toolu_agent1",
                "message": {
                    "id": "msg_2",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_fetch1",
                            "name": "WebFetch",
                            "input": {"url": "https://example.com/data"},
                        }
                    ],
                    "usage": {"input_tokens": 15, "output_tokens": 8,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_fetch1",
                            "content": "some data",
                        }
                    ],
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_agent1",
                            "content": "agent done",
                        }
                    ],
                },
            },
        ]

        result = trace_processing.extract_summary(events)
        seq = result["tool_sequence"]

        assert len(seq) == 2

        agent_entry = seq[0]
        assert agent_entry["tool"] == "Agent"
        assert agent_entry["parent"] is None

        fetch_entry = seq[1]
        assert fetch_entry["tool"] == "WebFetch"
        assert fetch_entry["parent"] == "toolu_agent1"


# ---------------------------------------------------------------------------
# Task 6: Errors
# ---------------------------------------------------------------------------


class TestSummaryErrors:
    def test_summary_errors(self):
        """WebFetch error + Bash error: verify 2 errors with correct tool/error/context/parent."""
        events = [
            {
                "type": "assistant",
                "message": {
                    "id": "msg_1",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_agent1",
                            "name": "Agent",
                            "input": {"description": "Do research"},
                        },
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 5,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                },
            },
            {
                "type": "assistant",
                "parent_tool_use_id": "toolu_agent1",
                "message": {
                    "id": "msg_2",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_fetch1",
                            "name": "WebFetch",
                            "input": {"url": "https://restricted.com/data"},
                        },
                    ],
                    "usage": {"input_tokens": 15, "output_tokens": 8,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_fetch1",
                            "content": "403 Forbidden",
                            "is_error": True,
                        },
                    ],
                },
            },
            {
                "type": "assistant",
                "message": {
                    "id": "msg_3",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "toolu_bash1",
                            "name": "Bash",
                            "input": {"command": "rm -rf /important"},
                        },
                    ],
                    "usage": {"input_tokens": 20, "output_tokens": 10,
                              "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
                },
            },
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_bash1",
                            "content": "Permission denied",
                            "is_error": True,
                        },
                    ],
                },
            },
        ]

        result = trace_processing.extract_summary(events)
        errors = result["errors"]

        assert len(errors) == 2

        fetch_err = next(e for e in errors if e["tool"] == "WebFetch")
        assert fetch_err["error"] == "403 Forbidden"
        assert fetch_err["context"] == "https://restricted.com/data"
        assert fetch_err["parent"] == "toolu_agent1"

        bash_err = next(e for e in errors if e["tool"] == "Bash")
        assert bash_err["error"] == "Permission denied"
        assert bash_err["context"] == "rm -rf /important"
        assert bash_err["parent"] is None

    def test_error_text_capped_at_threshold(self, tmp_path):
        """errors[].error is truncated at the same 4KB threshold."""
        big = "q" * (trace_processing._TOOL_RESULT_MAX_BYTES + 50)
        events = [
            {
                "type": "assistant",
                "message": {
                    "id": "m1",
                    "content": [{"type": "tool_use", "id": "t1",
                                 "name": "Bash", "input": {"command": "false"}}],
                    "usage": {"input_tokens": 0, "output_tokens": 0,
                              "cache_read_input_tokens": 0,
                              "cache_creation_input_tokens": 0},
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [{"type": "tool_result", "tool_use_id": "t1",
                                 "is_error": True, "content": big}],
                },
            },
        ]
        summary = trace_processing.extract_summary(events)
        assert len(summary["errors"]) == 1
        assert summary["errors"][0]["error"] == f"[truncated, {len(big.encode())}B original]"


# ---------------------------------------------------------------------------
# Task 7: process_trace()
# ---------------------------------------------------------------------------


class TestProcessTrace:
    def test_process_trace_graceful_failure(self, tmp_path):
        """Malformed JSON lines are skipped; no exception raised; raw trace unchanged."""
        conv_path = tmp_path / "conversation.jsonl"
        valid_line1 = json.dumps({"type": "system", "subtype": "init", "model": "m", "session_id": "s"})
        valid_line2 = json.dumps({"type": "assistant", "message": {"id": "msg_1", "role": "assistant", "content": []}})
        conv_path.write_text(
            valid_line1 + "\n"
            + "THIS IS NOT JSON\n"
            + valid_line2 + "\n"
        )
        raw_before = conv_path.read_text()

        # Must not raise
        trace_processing.process_trace(tmp_path, None)

        # Raw trace is unchanged
        assert conv_path.read_text() == raw_before

    def test_process_trace_produces_files(self, tmp_path):
        """4-event trace: verify both output files are created with correct content."""
        conv_path = tmp_path / "conversation.jsonl"

        # Event 1: system:init with tools/mcp_servers (should be trimmed)
        init_event = {
            "type": "system",
            "subtype": "init",
            "model": "claude-opus-4-5",
            "cwd": "/home/user",
            "session_id": "sess-abc",
            "permissionMode": "default",
            "plugins": [],
            "tools": ["bash", "read"],
            "mcp_servers": {"server": {}},
        }
        # Event 2: system:task_progress (should be dropped)
        task_progress_event = {
            "type": "system",
            "subtype": "task_progress",
            "task_id": "t1",
            "description": "doing stuff",
        }
        # Event 3: assistant with usage
        assistant_event = {
            "type": "assistant",
            "message": {
                "id": "msg_1",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello"}],
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                },
            },
        }
        # Event 4: rate_limit_event (should be dropped)
        rate_limit_event = {
            "type": "rate_limit_event",
            "rate_limit_info": {"status": "allowed"},
        }

        lines = "\n".join([
            json.dumps(init_event),
            json.dumps(task_progress_event),
            json.dumps(assistant_event),
            json.dumps(rate_limit_event),
        ]) + "\n"
        conv_path.write_text(lines)

        trace_processing.process_trace(tmp_path, None)

        # Both output files exist
        slim_path = tmp_path / "conversation_slim.jsonl"
        summary_path = tmp_path / "trace_summary.json"
        assert slim_path.exists(), "conversation_slim.jsonl should be created"
        assert summary_path.exists(), "trace_summary.json should be created"

        # Parse slim events
        slim_events = [json.loads(line) for line in slim_path.read_text().splitlines() if line.strip()]

        # task_progress and rate_limit_event must be dropped
        slim_subtypes = [e.get("subtype") for e in slim_events]
        slim_types = [e.get("type") for e in slim_events]
        assert "task_progress" not in slim_subtypes, "task_progress must be dropped from slim"
        assert "rate_limit_event" not in slim_types, "rate_limit_event must be dropped from slim"

        # init must be present and trimmed (no "tools" key)
        init_slims = [e for e in slim_events if e.get("subtype") == "init"]
        assert len(init_slims) == 1, "init event must appear in slim"
        assert "tools" not in init_slims[0], "tools must be stripped from init in slim"

        # Summary has correct token_usage totals
        with open(summary_path) as f:
            summary = json.load(f)

        tu = summary["token_usage"]
        assert tu["total_input"] == 100
        assert tu["total_output"] == 20

        # Exactly 1 by_turn entry (one unique message.id)
        assert len(tu["by_turn"]) == 1


# ---------------------------------------------------------------------------
# Task 8: Tool Result Truncation
# ---------------------------------------------------------------------------


class TestToolResultTruncation:
    """4KB cap on tool_result.content for Bash/WebFetch/WebSearch/Grep/Glob/non-workspace Read."""

    THRESHOLD = 4096

    def _tool_use_event(self, tid: str, name: str, tool_input: dict) -> dict:
        return {
            "type": "assistant",
            "message": {
                "id": f"msg-for-{tid}",
                "content": [
                    {"type": "tool_use", "id": tid, "name": name, "input": tool_input}
                ],
                "usage": {
                    "input_tokens": 0, "output_tokens": 0,
                    "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                },
            },
        }

    def _tool_result_event(self, tid: str, content, is_error: bool = False) -> dict:
        return {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": tid,
                     "is_error": is_error, "content": content}
                ],
            },
        }

    def _process(self, tmp_path, events, workspace_slug="proj"):
        task_dir = tmp_path / "task"
        task_dir.mkdir()
        conv = task_dir / "conversation.jsonl"
        with open(conv, "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        trace_processing.process_trace(str(task_dir), workspace_slug)
        slim = task_dir / "conversation_slim.jsonl"
        lines = [json.loads(l) for l in slim.read_text().splitlines() if l.strip()]
        return lines

    def _result_content(self, slim_lines, tid):
        for ev in slim_lines:
            if ev.get("type") != "user":
                continue
            for b in ev.get("message", {}).get("content", []):
                if b.get("type") == "tool_result" and b.get("tool_use_id") == tid:
                    return b.get("content")
        return None

    def test_bash_result_over_threshold_truncated(self, tmp_path):
        big = "x" * (self.THRESHOLD + 100)
        events = [
            self._tool_use_event("t1", "Bash", {"command": "ls"}),
            self._tool_result_event("t1", big),
        ]
        lines = self._process(tmp_path, events)
        content = self._result_content(lines, "t1")
        assert content == f"[truncated, {len(big.encode())}B original]"

    def test_bash_result_under_threshold_untouched(self, tmp_path):
        small = "x" * 100
        events = [
            self._tool_use_event("t1", "Bash", {"command": "ls"}),
            self._tool_result_event("t1", small),
        ]
        lines = self._process(tmp_path, events)
        assert self._result_content(lines, "t1") == small

    def test_workspace_read_uses_pointer_not_truncation_marker(self, tmp_path):
        big = "y" * (self.THRESHOLD + 500)
        events = [
            self._tool_use_event("r1", "Read",
                {"file_path": "/abs/path/.deep-research/proj/workspace/outline.md"}),
            self._tool_result_event("r1", big),
        ]
        lines = self._process(tmp_path, events)
        content = self._result_content(lines, "r1")
        assert content.startswith("[see workspace/workspace/outline.md")
        assert "truncated" not in content

    def test_non_workspace_read_truncated(self, tmp_path):
        big = "z" * (self.THRESHOLD + 1)
        events = [
            self._tool_use_event("r1", "Read", {"file_path": "/etc/somewhere.md"}),
            self._tool_result_event("r1", big),
        ]
        lines = self._process(tmp_path, events)
        assert self._result_content(lines, "r1") == f"[truncated, {len(big.encode())}B original]"

    @pytest.mark.parametrize("tool_name", ["WebFetch", "WebSearch", "Grep", "Glob"])
    def test_other_tools_truncated(self, tmp_path, tool_name):
        big = "q" * (self.THRESHOLD + 1)
        events = [
            self._tool_use_event("t1", tool_name, {"url": "x", "query": "x", "pattern": "x"}),
            self._tool_result_event("t1", big),
        ]
        lines = self._process(tmp_path, events)
        assert self._result_content(lines, "t1") == f"[truncated, {len(big.encode())}B original]"

    def test_single_text_block_wrapper_truncated(self, tmp_path):
        big = "w" * (self.THRESHOLD + 1)
        wrapped = [{"type": "text", "text": big}]
        events = [
            self._tool_use_event("t1", "Bash", {"command": "ls"}),
            self._tool_result_event("t1", wrapped),
        ]
        lines = self._process(tmp_path, events)
        content = self._result_content(lines, "t1")
        assert isinstance(content, list) and len(content) == 1
        assert content[0]["text"] == f"[truncated, {len(big.encode())}B original]"

    def test_multi_block_list_passes_through(self, tmp_path):
        """Scoped-out case from spec: multi-block list content is untouched."""
        big = "m" * (self.THRESHOLD + 1)
        multi = [
            {"type": "text", "text": big},
            {"type": "image", "source": {"data": "abc"}},
        ]
        events = [
            self._tool_use_event("t1", "Read", {"file_path": "/tmp/img.png"}),
            self._tool_result_event("t1", multi),
        ]
        lines = self._process(tmp_path, events)
        content = self._result_content(lines, "t1")
        assert content == multi

    def test_error_result_also_truncated(self, tmp_path):
        big = "e" * (self.THRESHOLD + 1)
        events = [
            self._tool_use_event("t1", "Bash", {"command": "false"}),
            self._tool_result_event("t1", big, is_error=True),
        ]
        lines = self._process(tmp_path, events)
        assert self._result_content(lines, "t1") == f"[truncated, {len(big.encode())}B original]"

    def test_tool_sequence_still_records_truncated_call(self, tmp_path):
        big = "x" * (self.THRESHOLD + 1)
        events = [
            self._tool_use_event("t1", "Bash", {"command": "echo hi"}),
            self._tool_result_event("t1", big),
        ]
        task_dir = tmp_path / "task"
        task_dir.mkdir()
        conv = task_dir / "conversation.jsonl"
        with open(conv, "w") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        trace_processing.process_trace(str(task_dir), "proj")
        summary = json.loads((task_dir / "trace_summary.json").read_text())
        assert len(summary["tool_sequence"]) == 1
        assert summary["tool_sequence"][0]["tool"] == "Bash"
        assert summary["tool_sequence"][0]["success"] is True
