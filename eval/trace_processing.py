"""Trace processing for eval harness.

Produces two artifacts from conversation.jsonl:
- conversation_slim.jsonl (filtered trace)
- trace_summary.json (structured extraction)
"""

import copy
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Drop rules
# ---------------------------------------------------------------------------

_DROP_TYPES = {"rate_limit_event"}
_DROP_SUBTYPES = {"task_progress", "task_started", "task_notification"}

# ---------------------------------------------------------------------------
# Trim helpers
# ---------------------------------------------------------------------------

_INIT_KEEP_KEYS = {"type", "subtype", "model", "cwd", "session_id", "permissionMode", "plugins"}
_INIT_DROP_KEYS = {"tools", "mcp_servers", "slash_commands", "skills", "agents"}

_HOOK_KEEP_KEYS = {"type", "subtype", "hook_name", "exit_code", "outcome", "output", "stdout"}

# 4KB cap on tool_result.content for tools that emit unbounded text.
# Chosen as a round number (~1K tokens) comfortable for most WebFetch
# summaries and Bash outputs, but small enough to cap the long tail
# (ripgrep dumps, raw HTML, large JSON). Not env-var-configurable —
# edit this constant to tune.
_TOOL_RESULT_MAX_BYTES = 4096

_TRUNCATE_TOOLS = {"Bash", "WebFetch", "WebSearch", "Grep", "Glob", "Read"}


def _trim_init(event: dict) -> dict:
    result = copy.copy(event)
    for key in _INIT_DROP_KEYS:
        result.pop(key, None)
    # Also drop any keys that are not in the keep set (except type)
    for key in list(result.keys()):
        if key not in _INIT_KEEP_KEYS:
            del result[key]
    return result


def _trim_hook_response(event: dict) -> dict:
    result = {}
    for key in _HOOK_KEEP_KEYS:
        if key in event:
            val = event[key]
            if key in ("output", "stdout") and isinstance(val, str):
                result[key] = len(val.encode())
            else:
                result[key] = val
    return result


def _replace_workspace_reads(
    event: dict,
    workspace_slug: str,
    tool_names: dict[str, str] | None,
    tool_inputs: dict[str, dict] | None,
) -> dict:
    """Return a deep copy of event with workspace Read results replaced."""
    if tool_names is None or tool_inputs is None:
        return event

    workspace_prefix = f".deep-research/{workspace_slug}/"

    result = copy.deepcopy(event)
    message = result.get("message", {})
    content = message.get("content", [])

    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_result":
            continue

        tool_use_id = block.get("tool_use_id", "")
        if tool_names.get(tool_use_id) != "Read":
            continue

        inputs = tool_inputs.get(tool_use_id, {})
        file_path = inputs.get("file_path", "")

        # Find the workspace_prefix substring within the absolute path
        idx = file_path.find(workspace_prefix)
        if idx == -1:
            continue

        relative_path = file_path[idx + len(workspace_prefix):]
        raw_content = block.get("content", "")
        if isinstance(raw_content, str):
            size = len(raw_content.encode())
        else:
            size = 0
        block["content"] = f"[see workspace/{relative_path}, {size}B]"

    return result


def _truncate_str(s: str) -> str | None:
    """Return truncation marker if s exceeds the threshold, else None."""
    if not isinstance(s, str):
        return None
    size = len(s.encode())
    if size <= _TOOL_RESULT_MAX_BYTES:
        return None
    return f"[truncated, {size}B original]"


def _truncate_tool_results(
    event: dict,
    tool_names: dict[str, str] | None,
) -> dict:
    """Truncate oversized tool_result.content for Bash/WebFetch/WebSearch/Grep/Glob/Read.

    Runs *after* _replace_workspace_reads, so workspace reads are already
    pointer-replaced (short) and will fall under the threshold unchanged.
    This ordering invariant is what makes the simple size check correct;
    no explicit workspace-Read exclusion needed here.
    """
    if tool_names is None:
        return event

    message = event.get("message", {})
    content = message.get("content", [])
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue

        tool_use_id = block.get("tool_use_id", "")
        tname = tool_names.get(tool_use_id, "")
        if tname not in _TRUNCATE_TOOLS:
            continue

        raw = block.get("content")

        # Case 1: raw string.
        if isinstance(raw, str):
            marker = _truncate_str(raw)
            if marker is not None:
                block["content"] = marker
            continue

        # Case 2: single-text-block wrapper [{"type":"text","text":"..."}].
        if (
            isinstance(raw, list)
            and len(raw) == 1
            and isinstance(raw[0], dict)
            and raw[0].get("type") == "text"
        ):
            marker = _truncate_str(raw[0].get("text", ""))
            if marker is not None:
                raw[0]["text"] = marker
            continue

        # Multi-block lists and other non-string content pass through.

    return event


# ---------------------------------------------------------------------------
# Public API — Task 1 + 2
# ---------------------------------------------------------------------------


def slim_event(
    event: dict,
    workspace_slug: str | None,
    tool_names: dict[str, str] | None = None,
    tool_inputs: dict[str, dict] | None = None,
) -> dict | None:
    """Return the (possibly trimmed) event to keep, or None to drop it."""
    event_type = event.get("type", "")
    subtype = event.get("subtype", "")

    # --- Drop rules ---
    if event_type in _DROP_TYPES:
        return None
    if subtype in _DROP_SUBTYPES:
        return None

    # --- Trim rules ---
    if subtype == "init":
        return _trim_init(event)

    if subtype == "hook_response":
        return _trim_hook_response(event)

    if event_type == "user":
        result = copy.deepcopy(event)
        # Drop top-level tool_use_result convenience field
        result.pop("tool_use_result", None)
        # Replace workspace Read results
        if workspace_slug is not None:
            result = _replace_workspace_reads(
                result, workspace_slug, tool_names, tool_inputs
            )
        result = _truncate_tool_results(result, tool_names)
        return result

    # All other event types (assistant, etc.) pass through unchanged
    return event


# ---------------------------------------------------------------------------
# Public API — Task 3
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Public API — Tasks 4-6
# ---------------------------------------------------------------------------


def _tool_summary(tool_name: str, tool_input: dict) -> str:
    """Return a short human-readable summary of a tool call."""
    if tool_name == "Bash":
        return tool_input.get("command", "")[:120]
    if tool_name in ("Write", "Edit"):
        fp = tool_input.get("file_path", tool_input.get("path", ""))
        content = tool_input.get("content", tool_input.get("new_string", ""))
        size = len(content.encode()) if isinstance(content, str) else 0
        return f"{fp} ({size}B)"
    if tool_name == "Read":
        return tool_input.get("file_path", "")
    if tool_name == "WebSearch":
        return "query: " + tool_input.get("query", "")
    if tool_name == "WebFetch":
        return tool_input.get("url", "")
    if tool_name == "Agent":
        desc = tool_input.get("description") or tool_input.get("prompt", "")
        return desc[:120] if desc else tool_name
    if tool_name in ("Grep", "Glob"):
        return f"{tool_name}: {tool_input.get('pattern', '')}"
    return tool_name


def extract_summary(events: list[dict]) -> dict:
    """Extract a structured summary from a list of conversation events.

    Returns a dict with token_usage, tool_sequence, and errors.
    """
    # --- token usage state ---
    seen_msg_ids: set[str] = set()
    msg_turn: dict[str, int] = {}  # message.id -> 1-based turn number
    turn_counter = 0
    by_turn: list[dict] = []
    total_input = total_output = total_cache_read = total_cache_creation = 0

    # --- tool sequence state ---
    tool_names: dict[str, str] = {}           # tool_use_id -> tool name
    tool_inputs: dict[str, dict] = {}         # tool_use_id -> input dict
    tool_parents: dict[str, str | None] = {}  # tool_use_id -> parent_tool_use_id
    tool_msg_ids: dict[str, str] = {}         # tool_use_id -> message.id
    tool_seq_index: dict[str, int] = {}       # tool_use_id -> index in tool_sequence

    tool_sequence: list[dict] = []
    errors: list[dict] = []

    for event in events:
        event_type = event.get("type", "")

        if event_type == "assistant":
            msg = event.get("message", {})
            mid = msg.get("id", "")

            # --- Token usage: count only first occurrence of each message.id ---
            if mid and mid not in seen_msg_ids:
                seen_msg_ids.add(mid)
                turn_counter += 1
                msg_turn[mid] = turn_counter

                usage = msg.get("usage", {})
                inp = usage.get("input_tokens", 0)
                out = usage.get("output_tokens", 0)
                cr = usage.get("cache_read_input_tokens", 0)
                cc = usage.get("cache_creation_input_tokens", 0)

                total_input += inp
                total_output += out
                total_cache_read += cr
                total_cache_creation += cc

                by_turn.append({
                    "turn": turn_counter,
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cache_read_input_tokens": cr,
                    "cache_creation_input_tokens": cc,
                })

            # --- Tool sequence: process ALL assistant events for tool_use blocks ---
            turn_num = msg_turn.get(mid, turn_counter)
            content = msg.get("content", [])
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_use":
                    continue

                tid = block.get("id", "")
                tname = block.get("name", "")
                tinput = block.get("input", {})
                tparent = event.get("parent_tool_use_id")

                tool_names[tid] = tname
                tool_inputs[tid] = tinput
                tool_parents[tid] = tparent
                tool_msg_ids[tid] = mid

                summary = _tool_summary(tname, tinput)
                idx = len(tool_sequence)
                tool_seq_index[tid] = idx
                tool_sequence.append({
                    "turn": turn_num,
                    "tool": tname,
                    "summary": summary,
                    "success": True,  # default; updated when tool_result arrives
                    "parent": tparent,
                })

        elif event_type == "user":
            content = event.get("message", {}).get("content", [])
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "tool_result":
                    continue

                tid = block.get("tool_use_id", "")
                is_error = block.get("is_error", False)
                result_content = block.get("content", "")

                # Update success in tool_sequence
                if tid in tool_seq_index:
                    tool_sequence[tool_seq_index[tid]]["success"] = not is_error

                tname = tool_names.get(tid, "")
                tinput = tool_inputs.get(tid, {})
                tparent = tool_parents.get(tid, None)
                tmid = tool_msg_ids.get(tid, "")
                turn_num = msg_turn.get(tmid, 0)

                # --- errors ---
                if is_error:
                    if tname == "WebFetch":
                        context = tinput.get("url", "")
                    elif tname == "Bash":
                        context = tinput.get("command", "")[:120]
                    elif tname == "WebSearch":
                        context = tinput.get("query", "")
                    else:
                        context = _tool_summary(tname, tinput)

                    error_text = result_content if isinstance(result_content, str) else str(result_content)
                    marker = _truncate_str(error_text)
                    if marker is not None:
                        error_text = marker

                    errors.append({
                        "turn": turn_num,
                        "tool": tname,
                        "error": error_text,
                        "context": context,
                        "parent": tparent,
                    })

    return {
        "token_usage": {
            "total_input": total_input,
            "total_output": total_output,
            "total_cache_read": total_cache_read,
            "total_cache_creation": total_cache_creation,
            "by_turn": by_turn,
        },
        "tool_sequence": tool_sequence,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Public API — Task 7
# ---------------------------------------------------------------------------


def process_trace(task_dir: "Path | str", workspace_slug: "str | None") -> None:
    """Process conversation.jsonl into slim trace and summary artifacts.

    Writes:
      - task_dir/conversation_slim.jsonl
      - task_dir/trace_summary.json

    Never raises. Skips malformed JSON lines with a warning to stderr.
    Returns silently if conversation.jsonl does not exist.
    """
    try:
        task_dir = Path(task_dir)
        conversation_path = task_dir / "conversation.jsonl"

        if not conversation_path.exists():
            return

        events: list[dict] = []
        tool_names: dict[str, str] = {}
        tool_inputs: dict[str, dict] = {}

        try:
            with open(conversation_path) as f:
                for lineno, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as exc:
                        print(
                            f"process_trace: skipping malformed JSON on line {lineno}: {exc}",
                            file=sys.stderr,
                        )
                        continue

                    events.append(event)

                    # Collect tool metadata from assistant tool_use blocks
                    if event.get("type") == "assistant":
                        msg = event.get("message", {})
                        content = msg.get("content", [])
                        for block in content:
                            if not isinstance(block, dict):
                                continue
                            if block.get("type") != "tool_use":
                                continue
                            tid = block.get("id", "")
                            if tid:
                                tool_names[tid] = block.get("name", "")
                                tool_inputs[tid] = block.get("input", {})
        except OSError as exc:
            print(f"process_trace: error reading {conversation_path}: {exc}", file=sys.stderr)
            return

        # Produce slim events
        slim_events: list[dict] = []
        for event in events:
            slimmed = slim_event(event, workspace_slug, tool_names, tool_inputs)
            if slimmed is not None:
                slim_events.append(slimmed)

        merged = merge_assistant_events(slim_events)

        # Write conversation_slim.jsonl
        slim_path = task_dir / "conversation_slim.jsonl"
        try:
            with open(slim_path, "w") as f:
                for event in merged:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(f"process_trace: error writing {slim_path}: {exc}", file=sys.stderr)

        # Extract summary from ORIGINAL events
        summary = extract_summary(events)

        # Write trace_summary.json
        summary_path = task_dir / "trace_summary.json"
        try:
            with open(summary_path, "w") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            print(f"process_trace: error writing {summary_path}: {exc}", file=sys.stderr)

    except Exception as exc:
        print(f"process_trace: unexpected error: {exc}", file=sys.stderr)


def merge_assistant_events(events: list[dict]) -> list[dict]:
    """Merge streaming assistant events that share the same message.id.

    Events for the same message.id may be interleaved with user events.
    The merged event is placed at the position of its first occurrence.
    """
    merged: list[dict] = []
    msg_contents: dict[str, list] = {}   # message.id -> accumulated content blocks
    msg_first_idx: dict[str, int] = {}   # message.id -> index in merged list

    for event in events:
        if event.get("type") != "assistant":
            merged.append(event)
            continue

        msg = event.get("message", {})
        mid = msg.get("id", "")

        if not mid:
            merged.append(event)
            continue

        if mid not in msg_first_idx:
            msg_first_idx[mid] = len(merged)
            msg_contents[mid] = list(msg.get("content", []))
            merged.append(copy.deepcopy(event))
        else:
            new_content = msg.get("content", [])
            if isinstance(new_content, list):
                msg_contents[mid].extend(new_content)
                merged[msg_first_idx[mid]]["message"]["content"] = msg_contents[mid]

    return merged
