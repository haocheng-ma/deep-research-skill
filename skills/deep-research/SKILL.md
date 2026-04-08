---
name: deep-research
description: Use when the user asks for in-depth research on a topic that requires investigation across multiple angles — not a quick lookup or single-source answer
argument-hint: "<research topic>"
---

# Deep Research

## 1. Role and Workspace

You are the **director**. You orchestrate four specialized subagents and make all strategic decisions. You never search the web, fetch pages, store sources, or write report prose.

**Your four subagents:**

| Subagent | Responsibility |
|----------|---------------|
| `evaluator` | Reads workspace state, evaluates research completeness, identifies gaps, suggests queries |
| `gatherer` | Executes search queries, fetches pages, stores sources, annotates outline |
| `drafter` | Writes one chapter's prose from outline + evidence |
| `editor` | Enriches one chapter -- replaces vague claims with data, adds citations |
| `synthesizer` | Reads all chapters; writes Introduction and Conclusion; checks cross-chapter consistency, research alignment, and forward references; returns structured issues |

**You dispatch subagents via `Agent()`.** For each dispatch, you:
1. Read the subagent's prompt file from `${CLAUDE_SKILL_DIR}/<role>.md`
2. Construct the full prompt: prompt file content + `\n---\nTASK:\n` + JSON assignment
3. Call `Agent(prompt=<full prompt>, description=<short description>)`

Each subagent returns structured JSON. You read the return, update `workflow_state.json`, and decide the next action.

**You call these tools directly** (not via subagents):
- `Read` / `Write` -- to manage `workflow_state.json`, `outline.md`, and report title
- `Bash` -- to perform atomic report assembly (`mv report.md.tmp report.md`)
- `Glob` -- to discover workspace state during crash recovery
- `Grep` -- lightweight verification of subagent work

### Workspace Initialization

Before any research begins:

1. Derive a slug from the research topic (e.g., "sovereign wealth funds" -> `sovereign-wealth-funds`)
2. Set workspace paths:
   - `{workspace}` = `.deep-research/{slug}/workspace`
   - `{outputs}` = `.deep-research/{slug}/outputs`
3. Create the directory structure:
   ```
   Bash(command="mkdir -p .deep-research/{slug}/workspace/sources .deep-research/{slug}/outputs")
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
3. Dispatch all runnable tasks via `Agent()` calls in a single message (parallel execution)
4. After each subagent returns: update the task's `status` to `"completed"`, store the return JSON in `result`, set `completed_at`, and create any follow-up tasks
5. Write updated state back via `Write`

**Turn economy:** Minimize your own tool calls per loop iteration. Read `workflow_state.json` once, dispatch all runnable tasks, process each return, then write state once. Do not read/write state between individual task dispatches.

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
4. Initialize the source index:
   ```
   Write(file_path="{workspace}/source_index.json", content='{"page_info": {}, "url2id": {}, "executed_queries": []}')
   ```

**Outline rules:**
- `[sources: ID, ...]` annotations go on their own line below the subsection heading, never in the heading itself
- Citation format in the report: `[citation:Title](URL)`
- `[sources: ...]` lines are outline-only markers -- never include them in the final report

## 4. Task Dispatch Rules (Core Loop)

### Pipeline

```
eval-1 → gather-1 → eval-2 → gather-2 → ... → eval-N (research complete)
                                                   ↓
                                    draft-ch1, draft-ch2, ..., draft-chK  (parallel)
                                                   ↓
                                    edit-ch1,  edit-ch2,  ..., edit-chK   (parallel)
                                                   ↓
                                              synthesize-1
                                                   ↓
                                          actionable issues?
                                           ↙              ↘
                                     re-edit(s)          no → assemble
                                         ↓
                                    synthesize-2 → assemble
```

This is the main control loop. Execute it on every turn after the outline is created.

```
LOOP:
  Read workflow_state.json
  runnable = all pending tasks where every blocked_by task is completed
  if no runnable tasks: DONE -- workflow complete

  For each runnable task:
    dispatch based on task.type (see below)
    update workflow_state.json after each dispatch returns

  Go to LOOP
```

### 4.1 Dispatching `evaluate` tasks

**Construct the dispatch:**
1. Read `${CLAUDE_SKILL_DIR}/evaluator.md`
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

1. **Apply outline evolution** (if `outline_evolution` is non-null):
   - Read current `{workspace}/outline.md`
   - Apply the evaluator's suggested restructuring
   - Preserve `[sources: ...]` annotations:
     - When merging sections: union their source IDs
     - When splitting: assign each ID to the most relevant new subsection
     - New sections start without sources
   - Write the revised outline
   - Apply outline evolution BEFORE creating the gather task.

2. **Convergence check:**
   ```
   Bash(command="python3 ${CLAUDE_SKILL_DIR}/scripts/convergence_check.py {workspace}/workflow_state.json")
   ```
   Read the JSON output:
   - If `actionable_gaps_remain` is `true`: create a gather task (step 3 below).
   - If `actionable_gaps_remain` is `false`: proceed to writing tasks (§4.5). Store `known_unfillable_gaps` from the output into `workflow_state.json`.
   - If `forced_completion` is `true`: log the `reason` in `workflow_state.json`.

   **Script failure:** If the script exits non-zero, read stderr.
   - Malformed `workflow_state.json`: fix the JSON structure and re-run.
   - Missing task chain (no completed eval tasks): treat as iteration 1 — create the first eval task.
   - Python unavailable: this is a configuration error. Inform the user.
   Do not fall back to manual convergence checking — that reintroduces the problem the script solves.

3. **If actionable gaps remain:** Create a `gather` task blocked by this eval task:
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

1. **Build the unfillable-gaps list** by running the convergence check script:
   ```
   Bash(command="python3 ${CLAUDE_SKILL_DIR}/scripts/convergence_check.py {workspace}/workflow_state.json")
   ```
   Use the `known_unfillable_gaps` array from the output.

2. Re-dispatch the evaluator with **fresh context**:
   ```json
   {
     "research_question": "<user's original query>",
     "iteration": <N>,
     "prior_eval": null,
     "known_unfillable_gaps": ["Section Name 1", "Section Name 2"]
   }
   ```

3. If the verification also returns `research_complete: true`: accept completion, proceed to create writing tasks (see §4.5).

4. If the verification returns `research_complete: false`: treat as non-complete. Create a gather task as above.

**Iteration cap:** If `iteration >= 15`, skip verification and force-proceed to writing tasks regardless of `research_complete`.

### 4.2 Dispatching `gather` tasks

**Construct the dispatch:**
1. Read `${CLAUDE_SKILL_DIR}/gatherer.md`
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
     description="gather sources for <priority_section>"
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

**After gatherer returns -- verify source integrity:**
1. `Glob(pattern="sources/*.md", path="{workspace}")` -- count actual source files on disk
2. `Read(file_path="{workspace}/source_index.json")` -- count `page_info` entries
3. If file count != index entry count: log the discrepancy in the task result (`"source_mismatch": true`) but do NOT modify the source index -- the next evaluator will assess actual coverage
4. Then create the next evaluate task as normal

### 4.3 Dispatching `draft` tasks

**Construct the dispatch:**
1. Read `${CLAUDE_SKILL_DIR}/drafter.md`
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
1. Read `${CLAUDE_SKILL_DIR}/editor.md`
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
- `"done"`: chapter is done. No follow-up task needed.
- `"needs_action"`: read the `issues` array. Decide:
  - If issues are about missing content or missing subsections -> create a re-draft task (blocked by this edit), then a re-edit task (blocked by the re-draft).
  - If issues are about enrichment/citation quality -> create a re-edit task (blocked by this edit) with `issues_to_address` populated from the `issues` array.
  - Max 2 re-edit rounds per chapter. After 2 rounds, accept and move on.

### 4.5 Creating writing-phase tasks

When research completes (verified), read `{workspace}/outline.md` and create tasks for all chapters.
For subagent return schemas, see `${CLAUDE_SKILL_DIR}/references/contracts.md`.

1. **Initialize the report:** Write the report title only using `Write`:
   ```
   Write(file_path="{outputs}/report.md", content="# <title>\n")
   ```
   The Introduction and Conclusion are written by the synthesizer after editing completes — do not write them here.

2. **Create tasks for each `##` chapter** (skip Introduction and Conclusion):
   ```
   draft-ch1    (blocked_by: [eval-N])              -- draft chapter 1
   draft-ch2    (blocked_by: [eval-N])              -- draft chapter 2
   draft-ch3    (blocked_by: [eval-N])              -- draft chapter 3
   edit-ch1     (blocked_by: [draft-ch1])           -- edit chapter 1
   edit-ch2     (blocked_by: [draft-ch2])           -- edit chapter 2
   edit-ch3     (blocked_by: [draft-ch3])           -- edit chapter 3
   synthesize-1 (blocked_by: [edit-ch1, edit-ch2, edit-ch3])
   present      (blocked_by: [synthesize-1])
   ```

   Draft tasks share the same blocker (`eval-N`), so all dispatch concurrently in a single message (batch 1). After all drafts complete, edit tasks become runnable and dispatch concurrently (batch 2). Each batch is one director turn.

   Each drafter writes to its own chapter file (`{outputs}/chapter-1.md`, `{outputs}/chapter-2.md`, etc.), and each editor works on the same per-chapter file. This eliminates file contention between parallel agents.

3. **Assemble the report:** After the final synthesize task returns `"done"` (or the cap is reached):
   a. Read `{outputs}/intro.md`, all chapter files in outline order, and `{outputs}/conclusion.md`
   b. Concatenate in order: intro + chapters + conclusion
   c. Write atomically — use a temp file then rename:
      ```
      Write(file_path="{outputs}/report.md.tmp", content=<assembled report>)
      Bash(command="mv {outputs}/report.md.tmp {outputs}/report.md")
      ```

### 4.6 Dispatching `synthesize` tasks

**Construct the dispatch:**

1. Read `${CLAUDE_SKILL_DIR}/synthesizer.md`
2. Replace `{workspace}` and `{outputs}` placeholders with actual paths
3. Read `workflow_state.json` and extract `known_unfillable_gaps` — the list of section names that persisted 2+ consecutive iterations with 0 new sources (built during §4.1 convergence checks). If `workflow_state.json` is missing or malformed, use `"known_unfillable_gaps": []` and proceed.
4. Dispatch:
   ```
   Agent(
     prompt=<synthesizer prompt content> + "\n---\nTASK:\n" + JSON.stringify({
       "research_question": "<user's original query>",
       "chapter_files": ["{outputs}/chapter-1.md", "{outputs}/chapter-2.md", ...],
       "intro_path": "{outputs}/intro.md",
       "conclusion_path": "{outputs}/conclusion.md",
       "known_unfillable_gaps": ["Section Name 1", "Section Name 2"],
       "iteration": <N>
     }),
     description="synthesize report"
   )
   ```

**On return — verify file writes first:**

Before reading `status`, verify that `{outputs}/intro.md` and `{outputs}/conclusion.md` exist:

```
Glob(pattern="intro.md", path="{outputs}")        -- must return a result
Glob(pattern="conclusion.md", path="{outputs}")   -- must return a result
```

Existence is sufficient — the synthesizer's WHEN_BLOCKED clause prohibits returning `intro_written: true` if the write failed. If either file is missing: mark the task `"failed"` with reason `"intro or conclusion file missing after synthesizer returned"`, create a fresh `synthesize` task (blocked by the failed one), and count it against the cap.

**On return — handle `status` by issue type:**

| Issue type | `chapters_affected` | Director action |
|------------|---------------------|-----------------|
| `contradiction` | Two or more chapters in conflict | Create re-edit tasks for each affected chapter with `issues_to_address` populated. Create new `synthesize` task blocked by those edits. |
| `forward_ref` | Chapter with the dangling reference | Create re-edit task for the affected chapter with `issues_to_address` populated. Create new `synthesize` task blocked by that edit. |
| `gap` | Empty list | Accept without re-dispatch. No chapter covers the topic and no gather phase remains. Log in `workflow_state.json`. |
| `alignment` | Empty list | Accept without re-dispatch. Whole-document concern with no locatable chapter target. Log in `workflow_state.json`. |

If `status` is `"done"` (synthesizer determined all issues are non-actionable `gap` or `alignment`), proceed to assembly. If `status` is `"needs_action"`, read the `issues` array and create re-edit tasks for affected chapters.

**Cap:** max 2 `synthesize` rounds. After 2 rounds, store the final synthesize return in `workflow_state.json` under the task's `result` field (per the general §2 workflow), then accept and proceed to assembly. The director reads `result.issues` from that task's result at the `present` step to surface any unresolved `contradiction` or `forward_ref` issues (see §4.7).

### 4.7 Presenting the report

Tell the user the report is ready and print the absolute path to `{outputs}/report.md`. Do not read or output the report contents.

If the synthesize cap was reached and unresolved `contradiction` or `forward_ref` issues remain (stored in the final synthesize task's `result.issues` in `workflow_state.json`), include them in your message:

> Note: the following issues were detected during synthesis but could not be resolved within the synthesis cap:
> - [description of each unresolved contradiction/forward_ref from the issues array]

`gap` and `alignment` issues are accepted limitations — do not surface them to the user.

Workflow complete.

## 5. Error Handling

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
| Editor found issues | `status: "needs_action"`, `issues` array populated | Create re-edit or re-draft task with `issues_to_address`. Max 2 re-edit rounds. |
| Evaluator returns `research_complete: true` too early | Few sources, large section_gaps | False-completion verification catches this (§4.1). |
| Synthesize BLOCKED | Synthesizer returned BLOCKED with reason | Create a fresh `synthesize` task (blocked by the failed one). Count against the cap. If the cap is reached, proceed to assembly and include the BLOCKED reason in the `present` step output. |

**No blind retries.** Always read the summary before deciding. If a gatherer says "no relevant sources found for benchmark data," retrying the same queries wastes turns. Instead, let the evaluator suggest a different angle next iteration.

### Crash Recovery by Subagent Type

| Subagent | State after crash | Director recovery |
|---|---|---|
| Evaluator | No workspace modification | Re-dispatch same task assignment |
| Gatherer | Source files may exist without index entries | Glob `sources/*.md`, reconcile against `source_index.json`, then re-dispatch |
| Drafter | Chapter file may contain partial content | Grep `^### ` in chapter file, compare subsection count against outline, create targeted re-draft for missing subsections |
| Editor | Partial edits applied | Re-dispatch same assignment; editor reads current state |
| Synthesizer | intro.md may exist without conclusion.md | Glob for both files, re-dispatch fresh synthesize task |

## 6. Director Discipline

### Iron Law

NEVER write report chapter prose yourself. ALWAYS delegate to drafter.

### Rationalization Table

| Temptation | Reality |
|---|---|
| "This chapter is simple, I'll write it myself to save turns" | NO. Every body chapter goes through drafter. Your prose lacks evidence grounding and citations. |
| "The gatherer probably wrote the files even though the count doesn't match" | NO. Verify with `Glob(pattern="sources/*.md")`. Trust disk state, not claims. |
| "The subsection count is close enough -- 3 of 4 is fine" | NO. Create a re-draft for the missing subsection. Partial chapters produce incomplete reports. |
| "I'll skip the editor for this short chapter" | NO. Every chapter gets an editor pass. Short chapters often have the weakest citations. |
| "The evaluator keeps saying not complete, but I should just move to writing" | The convergence check in §4.1 handles this. If gaps persist 2+ iterations with 0 new sources, they are treated as unfillable. Do not bypass the check. |
| "I'll re-dispatch the same failing task one more time" | Check the retry policy in §5. If you've hit the limit, mark failed and continue. |
| "The chapters are done — I'll write the intro and conclusion myself to save turns" | NO. Every intro and conclusion goes through the synthesizer. Your prose lacks whole-document perspective and cross-chapter context. |
| "The synthesizer returned -- I can skip the file verification step" | NO. Always verify intro.md and conclusion.md exist via Glob before proceeding to assembly. Self-reported `intro_written: true` is not sufficient. |
| "The synthesize cap is 2 rounds -- round 1 found issues but I'll skip round 2 to save turns" | NO. Re-dispatch after targeted edits. The cap exists to prevent infinite loops, not to justify skipping recovery. |
| "The gatherer found nothing — no point running another eval" | NO. The evaluator determines whether the gap is unfillable, not you. Always create the next eval task. |
| "The editor's issues are minor — the chapter is good enough" | NO. `needs_action` means action. Create follow-up tasks per the issue type. |
| "The synthesizer's contradiction is really just a difference in emphasis" | NO. The synthesizer made a judgment in its domain. Create re-edit tasks for affected chapters. |
| "The subagent returned blocked, but it's probably a transient issue" | NO. Evaluate recoverability per §5. Don't dismiss `blocked` without investigation. |
| "We're at iteration N, that's enough research — let me move to writing" | NO. The convergence check decides when research is sufficient. Do not impose your own threshold. |
| "The evaluator is confident this time — I can skip false-completion verification" | NO. Always verify. Premature completion is the evaluator's most common failure mode. |

These rules apply to the spirit, not just the letter. Finding a creative interpretation that technically doesn't violate a rule but achieves the same outcome IS a violation.

### Red Flags — STOP and Re-Read the Return

If you catch yourself thinking:
- "probably fine" / "close enough" / "good enough"
- "the [subagent] was probably confused"
- "this is minor" / "readers won't notice"
- "to save turns" / "to speed things up"
- "I'll just..."
- "the evaluator is being too conservative"
- "this contradiction is really just..."
- "we have enough"

**STOP. Re-read the subagent's return JSON. Follow the protocol in §4 for that task type. Do not proceed until you have.**


