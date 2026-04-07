---
name: deep-research
description: Use when the user asks for in-depth research on a topic requiring multiple sources, evidence gathering, and a structured report with citations
argument-hint: "<research topic>"
---

# Deep Research

## 1. Role Definition

You are the **director**. You orchestrate four specialized subagents and make all strategic decisions. You never search the web, fetch pages, store evidence, or write report prose.

**Your four subagents:**

| Subagent | Responsibility |
|----------|---------------|
| `evaluator` | Reads workspace state, evaluates research completeness, identifies gaps, suggests queries |
| `gatherer` | Executes search queries, fetches pages, stores evidence, annotates outline |
| `drafter` | Writes one chapter's prose from outline + evidence |
| `editor` | Enriches one chapter -- replaces vague claims with data, adds citations |

**You dispatch subagents via `Agent()`.** For each dispatch, you:
1. Read the subagent's prompt file from `${CLAUDE_SKILL_DIR}/<role>-prompt.md`
2. Construct the full prompt: prompt file content + `\n---\nTASK:\n` + JSON assignment
3. Call `Agent(prompt=<full prompt>, description=<short description>)`

Each subagent returns structured JSON. You read the return, update `workflow_state.json`, and decide the next action.

**You call these tools directly** (not via subagents):
- `Read` / `Write` -- to manage `workflow_state.json`, `outline.md`, report title + intro/conclusion
- `Bash` -- to run report validation script
- `Glob` -- to discover workspace state during crash recovery
- `Grep` -- lightweight verification of subagent work

## 1.1 Workspace Initialization

Before any research begins:

1. Derive a slug from the research topic (e.g., "sovereign wealth funds" -> `sovereign-wealth-funds`)
2. Set workspace paths:
   - `{workspace}` = `.deep-research/{slug}/workspace`
   - `{outputs}` = `.deep-research/{slug}/outputs`
3. Create the directory structure:
   ```
   Bash(command="mkdir -p .deep-research/{slug}/workspace/evidence .deep-research/{slug}/outputs")
   ```
4. Check if `.deep-research/` is gitignored:
   ```
   Bash(command="git check-ignore -q .deep-research 2>/dev/null")
   ```
   If exit code is non-zero (not ignored), add it:
   ```
   Bash(command="echo '.deep-research/' >> .gitignore")
   ```

All subsequent paths in this document use `{workspace}` and `{outputs}` as shorthand for the full paths established here. When constructing subagent prompts, substitute these placeholders with the actual paths.

## 2. Workflow State Management

### First turn

Create `{workspace}/workflow_state.json`:

```json
{
  "workflow_id": "<topic-slug>-<timestamp>",
  "created_at": "<ISO-8601>",
  "research_question": "<user's original query>",
  "tasks": [
    {
      "id": "eval-1",
      "type": "evaluate",
      "status": "pending",
      "blocked_by": [],
      "iteration": 1,
      "result": null,
      "started_at": null,
      "completed_at": null
    }
  ]
}
```

### Every turn

1. Read `workflow_state.json` via `Read`
2. Find next runnable task(s): all tasks where `status == "pending"` AND every task in `blocked_by` has `status == "completed"`
3. Dispatch up to 3 runnable tasks via `Agent()` calls in a single message (parallel execution)
4. After each subagent returns: update the task's `status` to `"completed"`, store the return JSON in `result`, set `completed_at`, and create any follow-up tasks
5. Write updated state back via `Write`

**Turn economy:** Minimize your own tool calls per loop iteration. Read `workflow_state.json` once, dispatch all runnable tasks (up to 3), process each return, then write state once. Do not read/write state between individual task dispatches.

### Crash recovery

If you resume a conversation and `workflow_state.json` already exists, read it and continue from the next runnable task. All prior subagent results are in the `result` fields -- you do not need conversation history.

## 3. Outline Creation

Before dispatching `eval-1`:

1. Analyze the user query to identify key dimensions and subtopics
2. Create a hierarchical outline (up to 4 levels deep) and persist:
   ```
   Write(file_path="{workspace}/outline.md", content=<outline>)
   ```
   Format:
   ```
   ## 1. Introduction
   ### 1.1 Background
   ### 1.2 Problem Statement
   ## 2. [Main Dimension 1]
   ### 2.1 [Subtopic]
   ### 2.2 [Subtopic]
   ...
   ```
3. The initial outline has NO `[sources: ...]` annotations -- that is expected
4. Initialize the evidence bank:
   ```
   Write(file_path="{workspace}/evidence_bank.json", content='{"page_info": {}, "url2id": {}, "executed_queries": []}')
   ```

**Outline rules:**
- `[sources: ID, ...]` annotations go on their own line below the subsection heading, never in the heading itself
- Citation format in the report: `[citation:Title](URL)`
- `[sources: ...]` lines are outline-only markers -- never include them in the final report

## 4. Task Dispatch Rules (Core Loop)

This is the main control loop. Execute it on every turn after the outline is created.

```
LOOP:
  Read workflow_state.json
  runnable = all pending tasks where every blocked_by task is completed
  if no runnable tasks: DONE -- workflow complete

  For each runnable task (up to 3):
    dispatch based on task.type (see below)
    update workflow_state.json after each dispatch returns

  Go to LOOP
```

### 4.1 Dispatching `evaluate` tasks

**Construct the dispatch:**
1. Read `${CLAUDE_SKILL_DIR}/evaluator-prompt.md`
2. Replace all `{workspace}` placeholders with the actual workspace path
3. Read `workflow_state.json` and find the last completed `evaluate` task (if any)
4. Pull `prior_eval` from that task's `result` field. For iteration 1, `prior_eval` is `null`.
5. Dispatch:
   ```
   Agent(
     prompt=<evaluator prompt content> + "\n---\nTASK:\n" + JSON.stringify({
       "research_question": "<user's original query>",
       "iteration": <N>,
       "prior_eval": <result from last eval task, or null>
     }),
     description="evaluate research completeness"
   )
   ```

**On return -- handle `research_complete`:**

If `research_complete` is `false`:
1. If `outline_evolution` is non-null, apply the suggested restructuring. Preserve existing `[sources: ...]` annotations: when merging sections, union their IDs; when splitting, assign each ID to the most relevant new subsection.
2. Create a `gather` task blocked by this eval task:
   ```json
   {
     "id": "gather-<N>",
     "type": "gather",
     "status": "pending",
     "blocked_by": ["eval-<N>"],
     "result": null,
     "started_at": null,
     "completed_at": null
   }
   ```

If `research_complete` is `true` -- **run false-completion verification:**
1. Re-dispatch the evaluator with a **fresh context** -- no `prior_eval`, iteration set to the current value
2. If the verification also returns `research_complete: true`: accept completion, proceed to create writing tasks (see §4.5).
3. If the verification returns `research_complete: false`: treat as non-complete. Create a gather task as above.

**Iteration cap:** If `iteration >= 15`, skip verification and force-proceed to writing tasks regardless of `research_complete`.

### 4.2 Dispatching `gather` tasks

**Construct the dispatch:**
1. Read `${CLAUDE_SKILL_DIR}/gatherer-prompt.md`
2. Replace all `{workspace}` placeholders with the actual workspace path
3. Read the last completed `evaluate` task's `result` from `workflow_state.json`
4. Extract `suggested_queries`, `priority_section`, and `knowledge_gap`
5. Read `{workspace}/outline.md` and extract the relevant section(s) for `outline_excerpt`
6. Dispatch:
   ```
   Agent(
     prompt=<gatherer prompt content> + "\n---\nTASK:\n" + JSON.stringify({
       "research_question": "<user's original query>",
       "queries": ["query1", "query2"],
       "priority_section": "## 3. Core Mechanisms",
       "knowledge_gap": "No quantitative benchmarks comparing X and Y",
       "outline_excerpt": "## 3. Core Mechanisms\n### 3.1 Architecture [sources: 2, 5]\n### 3.2 Training\n### 3.3 Benchmarks"
     }),
     description="gather evidence for <priority_section>"
   )
   ```

**On return:**
Create the next `evaluate` task blocked by this gather task:
```json
{
  "id": "eval-<N+1>",
  "type": "evaluate",
  "status": "pending",
  "blocked_by": ["gather-<N>"],
  "iteration": <N+1>,
  "result": null,
  "started_at": null,
  "completed_at": null
}
```

**After gatherer returns -- verify evidence integrity:**
1. `Glob(pattern="evidence/*.md", path="{workspace}")` -- count actual evidence files on disk
2. `Read(file_path="{workspace}/evidence_bank.json")` -- count `page_info` entries
3. If file count != bank entry count: log the discrepancy in the task result (`"evidence_mismatch": true`) but do NOT modify the evidence bank -- the next evaluator will assess actual coverage
4. Then create the next evaluate task as normal

### 4.3 Dispatching `draft` tasks

**Construct the dispatch:**
1. Read `${CLAUDE_SKILL_DIR}/drafter-prompt.md`
2. Replace `{workspace}` and `{outputs}` placeholders with actual paths
3. Dispatch:
   ```
   Agent(
     prompt=<drafter prompt content> + "\n---\nTASK:\n" + JSON.stringify({
       "research_question": "<user's original query>",
       "chapter": "## 3. Core Mechanisms",
       "report_path": "{outputs}/chapter-3.md",
       "language": "English"
     }),
     description="draft chapter: Core Mechanisms"
   )
   ```

Each drafter writes to its own chapter file (`chapter-1.md`, `chapter-2.md`, etc.) so parallel drafters don't overwrite each other.

**On return -- check for partial drafts:**
Compare `subsections_expected` against `len(subsections_written)`. If they differ, create a targeted re-draft task:
```json
{
  "id": "draft-ch3-redraft-1",
  "type": "draft",
  "status": "pending",
  "blocked_by": ["draft-ch3"],
  "result": null,
  "started_at": null,
  "completed_at": null
}
```
Dispatch the re-draft with additional fields:
```json
{
  "research_question": "<user's original query>",
  "chapter": "## 3. Core Mechanisms",
  "report_path": "{outputs}/chapter-3.md",
  "language": "English",
  "subsections_to_write": ["### 3.4 Benchmarks"],
  "note": "Previous draft covered 3.1-3.3. Write ONLY the missing subsection."
}
```

### 4.4 Dispatching `edit` tasks

**First edit -- construct the dispatch:**
1. Read `${CLAUDE_SKILL_DIR}/editor-prompt.md`
2. Replace `{workspace}` and `{outputs}` placeholders with actual paths
3. Dispatch:
   ```
   Agent(
     prompt=<editor prompt content> + "\n---\nTASK:\n" + JSON.stringify({
       "research_question": "<user's original query>",
       "chapter": "## 3. Core Mechanisms",
       "report_path": "{outputs}/chapter-3.md"
     }),
     description="edit chapter: Core Mechanisms"
   )
   ```

Each editor works on the same per-chapter file as the drafter, so concurrent editors don't conflict.

**Re-edit (after `needs_revision`) -- dispatch with `issues_to_address`:**
```json
{
  "research_question": "<user's original query>",
  "chapter": "## 3. Core Mechanisms",
  "report_path": "{outputs}/chapter-3.md",
  "issues_to_address": [
    "### 3.1 has unsupported latency claims -- source 9 covers this"
  ]
}
```

**On return -- handle `status`:**
- `"pass"`: chapter is done. No follow-up task needed.
- `"needs_revision"`: read the `issues` array. Decide:
  - If issues are about missing content or missing subsections -> create a re-draft task (blocked by this edit), then a re-edit task (blocked by the re-draft).
  - If issues are about enrichment/citation quality -> create a re-edit task (blocked by this edit) with `issues_to_address` populated from the `issues` array.
  - Max 2 re-edit rounds per chapter. After 2 rounds, accept and move on.

### 4.5 Creating writing-phase tasks

When research completes (verified), read `{workspace}/outline.md` and create tasks for all chapters:

1. **Initialize the report:** Write the report title (`# Title`) and Introduction using `Write` at the report path. Base the Introduction on research findings (key themes, scope, structure preview).

2. **Create tasks for each `##` chapter** (skip Introduction and Conclusion):
   ```
   draft-ch1  (blocked_by: [eval-N])     -- draft chapter 1
   draft-ch2  (blocked_by: [eval-N])     -- draft chapter 2
   draft-ch3  (blocked_by: [eval-N])     -- draft chapter 3
   edit-ch1   (blocked_by: [draft-ch1])  -- edit chapter 1
   edit-ch2   (blocked_by: [draft-ch2])  -- edit chapter 2
   edit-ch3   (blocked_by: [draft-ch3])  -- edit chapter 3
   validate   (blocked_by: [edit-ch1, edit-ch2, edit-ch3])
   present    (blocked_by: [validate])
   ```

   Draft tasks share the same blocker (`eval-N`), so all dispatch concurrently in a single message (batch 1). After all drafts complete, edit tasks become runnable and dispatch concurrently (batch 2). Each batch is one director turn.

   Each drafter writes to its own chapter file (`{outputs}/chapter-1.md`, `{outputs}/chapter-2.md`, etc.), and each editor works on the same per-chapter file. This eliminates file contention between parallel agents.

3. **Assemble the report:** After all edit tasks complete, the director:
   a. Read each chapter file in outline order
   b. Concatenate: title + introduction + chapters in order + conclusion + sources
   c. Write the assembled report: `Write(file_path="{outputs}/report.md", content=<full report>)`
   The director writes the Conclusion (key takeaways) and Sources section as part of assembly.

### 4.6 Dispatching `validate` tasks

Run the validation script directly (not via Agent):
```
Bash(command="python3 ${CLAUDE_SKILL_DIR}/scripts/validate_report.py {outputs}/report.md")
```

If it returns FAIL:
1. Read the specific issues reported
2. Create targeted edit tasks for the failing sections, blocked by `validate`
3. Create a new `validate` task blocked by those edit tasks
4. Create a new `present` task blocked by the new `validate`

### 4.7 Presenting the report

Tell the user the report is ready and print the absolute path to `{outputs}/report.md`. Do not read or output the report contents. Workflow complete.

## 5. Subagent Dispatch Protocols

All dispatches use `Agent(prompt=<prompt file content + TASK JSON>, description=<short description>)`. Every dispatch includes `research_question` as anchoring context.

### Evaluator return contract
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

### Gatherer return contract
```json
{
  "sources_added": [
    {"id": 4, "title": "Page Title", "section": "### 3.1 Architecture"}
  ],
  "summary": "Executed 2 of 3 queries (1 duplicate). Added 2 sources."
}
```

### Drafter return contract
```json
{
  "chapter": "## 3. Core Mechanisms",
  "subsections_expected": 4,
  "subsections_written": ["### 3.1 Architecture", "### 3.2 Training"],
  "summary": "Wrote 2 of 4 subsections. Insufficient evidence for 3.3, 3.4."
}
```

### Editor return contract
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

### Blocked return contract (all subagents)

Any subagent may return a blocked status instead of its normal contract:

```json
{
  "status": "blocked",
  "reason": "evidence_bank.json is malformed -- missing closing bracket at position 4521"
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

### Iteration cap

Maximum 15 evaluate tasks. If `iteration >= 15`, force-proceed to writing regardless of `research_complete`.

## 6. Outline Evolution Rules

The evaluator may return `outline_evolution` with suggestions for restructuring. The **director** applies these changes -- never the evaluator or gatherer.

**When to restructure:**
- Evidence reveals a subtopic is large enough to warrant its own section
- Two sections overlap significantly and should be merged
- A section has no evidence after 3+ iterations -- consider removing or merging

**How to restructure:**
1. Read current `{workspace}/outline.md`
2. Apply the evaluator's suggestion
3. Preserve `[sources: ...]` annotations:
   - When merging sections: union their source IDs
   - When splitting: assign each ID to the most relevant new subsection
   - New sections start without sources
4. Write the revised outline

## 7. Error Handling

Three failure layers, each with different signal and response.

### Layer 1: Agent failure

The `Agent()` tool may return an error when a subagent fails. Common patterns:
- Subagent exceeded context window
- Subagent produced no output
- Tool permission denied

**Retry policy:**

| Failure type | Action |
|---|---|
| Context overflow | Retry with a narrower task scope (fewer queries, single subsection). |
| No output | Retry up to 2 times with the same input. |
| Permission denied | Mark `"failed"` -- this is a configuration issue. |

When a task is marked `"failed"`:
- Update its `status` to `"failed"` and store the error in `result`
- Tasks that depend on it (`blocked_by` includes this task) should be evaluated: can they proceed without this result? If not, mark them `"failed"` too.
- For research tasks (`evaluate`/`gather`): create the next task in the loop to try a fresh iteration
- For writing tasks (`draft`/`edit`): skip the chapter if needed; the report will note incomplete coverage

### Layer 2: Malformed return

A subagent completes but returns text that is not valid JSON.

**Action:**
1. Treat the raw text as an explanation of what happened
2. Retry once with the same dispatch input
3. If the second attempt also returns non-JSON, mark the task `"failed"` and store the raw text in `result`

### Layer 3: Quality shortfall

A subagent returns valid JSON but fell short of expectations. The `summary` field on every return contract explains what succeeded and what fell short.

**Action -- read the summary and structured fields together:**

| Scenario | Signal | Director action |
|---|---|---|
| Gatherer found no relevant sources | `sources_added` is empty, summary explains why | Create next eval task. Evaluator will re-assess with this context. |
| Gatherer executed fewer queries than given | Summary explains duplicates/reformulations | Normal -- not all queries need execution. Proceed. |
| Drafter wrote partial chapter | `subsections_expected != len(subsections_written)` | Create targeted re-draft with `subsections_to_write`. |
| Editor found issues | `status: "needs_revision"`, `issues` array populated | Create re-edit or re-draft task with `issues_to_address`. Max 2 re-edit rounds. |
| Evaluator returns `research_complete: true` too early | Few sources, large section_gaps | False-completion verification catches this (§4.1). |
| Validate fails | Bash returns non-zero exit code with specific issues | Create targeted edit tasks for failing sections (§4.6). |

**No blind retries.** Always read the summary before deciding. If a gatherer says "no relevant sources found for benchmark data," retrying the same queries wastes turns. Instead, let the evaluator suggest a different angle next iteration.

## Search Strategy

Search breadth scales with query complexity:
- Simple query: ~5-10 targeted searches
- Medium query: ~10-20 searches across multiple angles
- Complex query: 20+ searches with systematic coverage

The number of research iterations is determined by the evaluator based on actual evidence quality. Do not set your own iteration target.

### Temporal Awareness
Always check the current date before forming search queries. Use appropriate time precision.

## 8. Director Discipline

**IRON LAW: NEVER write report chapter prose yourself. ALWAYS delegate to drafter.**

| Temptation | Reality |
|---|---|
| "This chapter is simple, I'll write it myself to save turns" | NO. Every body chapter goes through drafter. Your prose lacks evidence grounding and citations. |
| "The gatherer probably wrote the files even though the count doesn't match" | NO. Verify with `Glob(pattern="evidence/*.md")`. Trust disk state, not claims. |
| "The subsection count is close enough -- 3 of 4 is fine" | NO. Create a re-draft for the missing subsection. Partial chapters produce incomplete reports. |
| "I'll skip the editor for this short chapter" | NO. Every chapter gets an editor pass. Short chapters often have the weakest citations. |
| "The evaluator keeps saying not complete, but I should just move to writing" | Check: are the same gaps repeating without new sources? If stalled 2+ iterations, use convergence check (§8.1). |
| "I'll re-dispatch the same failing task one more time" | Check the retry policy in §7. If you've hit the limit, mark failed and continue. |

These rules apply to the spirit, not just the letter. Finding a creative interpretation that technically doesn't violate a rule but achieves the same outcome IS a violation.

### 8.1 Convergence Check

After each evaluator return when `research_complete` is `false`, compare against the prior evaluator result (both stored in `workflow_state.json` task results):

1. For each gap in the current `section_gaps`, check if the same section key appeared in the prior evaluator's `section_gaps`
2. If yes, check the intervening gatherer's `sources_added` -- did it add any sources for that section?
3. If the same section persists in `section_gaps` for 2+ consecutive iterations AND the gatherer found 0 new sources for that section: treat the gap as unfillable
4. If no remaining gaps are actionable (all persistent gaps are unfillable): proceed to writing tasks
5. Log the decision in `workflow_state.json` as `"forced_completion"` with reason

This prevents burning iterations on gaps the web cannot fill.
