# Subagent Return Contracts

Every subagent returns structured JSON as its final message. The director reads the return, updates `workflow_state.json`, and decides the next action. For dispatch protocols, see SKILL.md §4.

All dispatches include `research_question` as anchoring context in the task assignment.

## Evaluator return contract
```json
{
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
  "sources_added": [
    {"id": 4, "title": "Page Title", "section": "### 3.1 Architecture"}
  ],
  "summary": "Executed 2 of 3 queries (1 duplicate). Added 2 sources."
}
```

## Drafter return contract
```json
{
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
  "status": "pass",
  "enrichments_made": 5,
  "citations_added": 3,
  "issues": [],
  "summary": "Enriched 5 claims, added 3 citations."
}
```
When issues found, `status` is `"needs_revision"` and `issues` contains specific problems.

## Synthesizer return contract
```json
{
  "intro_written": true,
  "conclusion_written": true,
  "status": "pass",
  "issues": [],
  "summary": "Wrote introduction and conclusion. No cross-chapter issues found."
}
```

When issues are found, `status` is `"issues_found"` and `issues` contains specific problems:

```json
{
  "intro_written": true,
  "conclusion_written": true,
  "status": "issues_found",
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
