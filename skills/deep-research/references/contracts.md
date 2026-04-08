# Subagent Return Contracts

Every subagent returns structured JSON as its final message. The director reads the return, updates `workflow_state.json`, and decides the next action. For dispatch protocols, see SKILL.md §4.

All dispatches include `research_question` as anchoring context in the task assignment.

## Status vocabulary

Every subagent return includes a `status` field:

| Status | Meaning | Director action |
|---|---|---|
| `done` | Task completed. Follow the normal task DAG. | Read type-specific fields for follow-up task creation. |
| `needs_action` | Task completed but corrective action needed beyond the normal DAG. | Read type-specific fields to scope follow-up tasks. |
| `blocked` | Task could not complete. | Error handling per §5. |

**Precedence rule:** The `status` field is a routing hint, not a bypass for verification gates. If the director's independent verification contradicts self-reported status (e.g., drafter reports `done` but subsection count shows 3 of 4), the director treats the task as `needs_action` regardless of the reported status. Director verification always takes precedence over self-reported status.

## Evaluator return contract
```json
{
  "status": "done",
  "research_complete": false,
  "section_gaps": {
    "Performance Benchmarks": "No cross-dataset comparison metrics"
  },
  "suggested_queries": ["query1", "query2"],
  "priority_section": "## 3. Core Mechanisms",
  "knowledge_gap": "No quantitative benchmarks comparing X and Y",
  "outline_evolution": "Split '## 3. Core Mechanisms' into two sections, or null",
  "summary": "Iteration 3: architecture well-covered. Main gap is benchmarks."
}
```

## Gatherer return contract
```json
{
  "status": "done",
  "sources_added": [
    {"id": 4, "title": "Page Title", "section": "### 3.1 Architecture"}
  ],
  "summary": "Executed 2 of 3 queries (1 duplicate). Added 2 sources."
}
```

## Drafter return contract
```json
{
  "status": "needs_action",
  "chapter": "## 3. Core Mechanisms",
  "subsections_expected": 4,
  "subsections_written": ["### 3.1 Architecture", "### 3.2 Training"],
  "summary": "Wrote 2 of 4 subsections. Insufficient evidence for 3.3, 3.4."
}
```

## Editor return contract
```json
{
  "chapter": "## 3. Core Mechanisms",
  "status": "done",
  "enrichments_made": 5,
  "citations_added": 3,
  "issues": [],
  "summary": "Enriched 5 claims, added 3 citations."
}
```
When issues found, `status` is `"needs_action"` and `issues` contains specific problems.

## Synthesizer return contract
```json
{
  "status": "done",
  "intro_written": true,
  "conclusion_written": true,
  "issues": [],
  "summary": "Wrote introduction and conclusion. No cross-chapter issues found."
}
```

When actionable issues are found (`contradiction` or `forward_ref`), `status` is `"needs_action"`. When only non-actionable issues are found (`gap` or `alignment`), `status` is `"done"`. The `issues` array is populated in both cases:

```json
{
  "status": "needs_action",
  "intro_written": true,
  "conclusion_written": true,
  "issues": [
    {
      "type": "contradiction",
      "chapters_affected": ["{outputs}/chapter-2.md", "{outputs}/chapter-4.md"],
      "description": "Chapter 2 characterizes adoption as slow; Chapter 4 describes rapid growth since 2020.",
      "suggested_fix": "Qualify the time period in Chapter 2 — pre-2020 vs. post-2020 distinction."
    }
  ],
  "summary": "Wrote introduction and conclusion. Found 1 contradiction across chapters 2 and 4."
}
```

Issue types and `chapters_affected` semantics:

| Type | `chapters_affected` |
|------|---------------------|
| `contradiction` | The two or more chapters in conflict |
| `gap` | Empty list — no chapter covers the missing topic |
| `alignment` | Empty list — whole-document concern, not localized |
| `forward_ref` | The chapter containing the dangling reference |

## Blocked return contract (all subagents)

Any subagent may return a blocked status instead of its normal contract:

```json
{
  "status": "blocked",
  "reason": "source_index.json is malformed -- missing closing bracket at position 4521"
}
```

**Director action on `"blocked"`:**
1. Store the blocked return in the task's `result` field
2. Mark the task as `"failed"` with `error: "blocked: <reason>"`
3. Evaluate whether the blocker is recoverable:
   - File corruption -> director reads and fixes the file, then creates a fresh task
   - Missing prerequisite -> check if the prerequisite task failed; if so, cascade failure
   - Structural error (0 subsections, missing outline) -> director fixes the structure, then retries
4. If not recoverable: mark downstream tasks as `"failed"` and continue

## Iteration cap

Maximum 15 evaluate tasks. If `iteration >= 15`, force-proceed to writing regardless of `research_complete`.
