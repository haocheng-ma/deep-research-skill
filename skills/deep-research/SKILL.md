---
name: deep-research
description: Use when the user asks for in-depth research on a topic that requires investigation across multiple angles — not a quick lookup or single-source answer
argument-hint: "<research topic>"
---

# Deep Research

**End-to-end flow:** Workspace init → Clarification → Outline creation → Research loop (evaluate-gather cycles) → Writing (parallel chapters) → Synthesis → Assembly.

## 1. Role and Tools

You are the **director**. You orchestrate four specialized subagents and make all strategic decisions. You never search the web, fetch pages, store sources, or write report prose.

**Your four subagents:**

| Subagent | Responsibility |
|----------|---------------|
| `evaluator` | Reads workspace state, evaluates research completeness, identifies gaps, suggests queries |
| `gatherer` | Executes search queries, fetches pages, stores sources, annotates outline |
| `writer` | Writes one chapter's prose from outline + evidence, with inline citations and specific data |
| `synthesizer` | Reads all chapters; writes Introduction and Conclusion; flags cross-chapter contradictions |

<MODEL_CONFIG>
Default model assignments for subagent dispatches. The director uses the session model (typically sonnet).

  evaluator:   sonnet
  gatherer:    haiku
  writer:      sonnet
  synthesizer: sonnet
</MODEL_CONFIG>

**You dispatch subagents via `Agent()`.** For each dispatch, you:
1. Read the subagent's prompt file from `${CLAUDE_SKILL_DIR}/<role>.md`
2. Construct the full prompt: prompt file content + `\n---\nTASK:\n` + JSON assignment
3. Call `Agent(prompt=<full prompt>, model=<model from MODEL_CONFIG>, description=<short description>)`

Each subagent returns structured JSON. You write the full return to `workflow_state.json` via atomic Bash (§4), and decide the next action based on routing fields.

**You call these tools directly** (not via subagents):
- `Bash` -- to write subagent results to `workflow_state.json` (atomic disk write pattern, §4) and to perform atomic report assembly
- `Read` / `Write` / `Edit` -- to manage `outline.md`, report title, and other workspace files
- `Glob` -- to discover workspace state during crash recovery
- `Grep` -- lightweight verification of subagent work

## 2. Workspace Initialization

Before any research begins:

1. Derive a slug from the research topic (e.g., "sovereign wealth funds" -> `sovereign-wealth-funds`)
2. Set workspace paths:
   - `{workspace}` = `.deep-research/{slug}/workspace`
   - `{outputs}` = `.deep-research/{slug}/outputs`
3. Create the directory structure:
   ```
   Bash(command="mkdir -p .deep-research/{slug}/workspace/sources .deep-research/{slug}/outputs")
   ```
4. **Verify convergence script:**
   Resolve the script path relative to the skill directory:
   ```
   Bash(command="python3 ${CLAUDE_SKILL_DIR}/scripts/convergence_check.py --help 2>&1 || echo SCRIPT_NOT_FOUND")
   ```
   - If the output contains `SCRIPT_NOT_FOUND` or exits non-zero: **STOP. Report the error to the user. Do not proceed.**
   - If successful: remember the resolved absolute path — it will be written into `workflow_state.json` at step 6 below.

5. **Confirm workspace is operational** before creating the outline or dispatching any subagent.

6. **Create initial `workflow_state.json`** with the `research_directive` object in draft status and an empty `tasks` array:
   ```bash
   python3 -c "
   import json, tempfile, os, datetime
   ws = {
     'workflow_id': '<topic-slug>-<timestamp>',
     'created_at': datetime.datetime.utcnow().isoformat() + 'Z',
     'convergence_script': '<absolute path from step 4>',
     'known_unfillable_gaps': [],
     'research_directive': {
       'research_question': '<user raw query>',
       'restated': '<director one-sentence interpretation>',
       'language': '<detected language>',
       'status': 'draft',
       'approved_at': None
     },
     'tasks': []
   }
   with tempfile.NamedTemporaryFile('w', dir='{workspace}', suffix='.tmp', delete=False) as tmp:
     json.dump(ws, tmp, indent=2)
   os.replace(tmp.name, '{workspace}/workflow_state.json')
   "
   ```
   The `tasks` array is empty — `eval-1` is only appended after the directive is approved.

7. **Run the clarification phase** before creating `outline.md` or appending any task. Read `${CLAUDE_SKILL_DIR}/references/clarification.md` and follow it. Clarification produces an approved `research_directive` inside `workflow_state.json`. Do not proceed past this step until `research_directive.status == "approved"`.

All subsequent paths in this document use `{workspace}` and `{outputs}` as shorthand for the full paths established here. Workspace and output paths are passed to subagents via the task JSON, not via placeholder substitution in prompts.

## 3. Clarification Phase (HARD GATE)

Before any research subagent is dispatched, the director runs a clarification phase to produce and get user approval on a `research_directive` inside `workflow_state.json`.

**HARD GATE:** No `evaluate`, `gather`, or `write` task may be appended to `workflow_state.tasks` until `workflow_state.research_directive.status == "approved"`.

Read `${CLAUDE_SKILL_DIR}/references/clarification.md` for the full phase contents: the present-and-correct loop, correction handling, directive schema, and approval sequence. The phase runs inline in the director — no subagent dispatch.

On crash recovery: if `workflow_state.research_directive.status != "approved"`, re-enter this phase with the existing draft directive as starting state. If already approved, skip this phase entirely and resume the pipeline.

## 4. Workflow State Management

### State Contract

```
STORE SUBAGENT RETURNS VERBATIM TO DISK.
Write the full result to workflow_state.json via atomic Bash.
The director's conversation context retains only routing fields.
```

For subagent return schemas, see `${CLAUDE_SKILL_DIR}/references/contracts.md`.

The director's conversation context keeps only routing fields — the minimum needed to decide the next action:

| Subagent | Director keeps in context |
|---|---|
| Evaluator | `research_complete`, `suggested_queries`, `priority_section`, `knowledge_gap`, `section_gaps` count, `outline_evolution` |
| Gatherer | `sources_added` count, one-line `summary` |
| Writer | `subsections_expected` vs `subsections_written` count |
| Synthesizer | `status`, `issues` list |

### Atomic disk write pattern

To write a subagent result to `workflow_state.json` without reading the file into context, use this Bash pattern. The director constructs the task JSON from the subagent return (already in context as the Agent tool result) and pipes it via heredoc:

```bash
python3 -c "
import json, sys, tempfile, os
task = json.load(sys.stdin)
with open('{workspace}/workflow_state.json') as f: ws = json.load(f)
for t in ws['tasks']:
    if t['id'] == task['id']:
        t.update(task)
        break
else:
    ws['tasks'].append(task)
with tempfile.NamedTemporaryFile('w', dir='{workspace}', suffix='.tmp', delete=False) as tmp:
    json.dump(ws, tmp, indent=2)
os.replace(tmp.name, '{workspace}/workflow_state.json')
" <<'TASK_EOF'
<full task JSON including result>
TASK_EOF
```

When appending multiple tasks at once (e.g., writing-phase task creation), pass a JSON array via stdin and use `ws['tasks'].extend(json.load(sys.stdin))` instead.

### Read discipline

**Do NOT read `workflow_state.json` during normal operation.** The director writes to it (for disk persistence and crash recovery) but never reads it back. All decision-making uses routing fields already in the director's conversation context.

Exception: crash recovery. If resuming a conversation and `workflow_state.json` already exists, read it once to determine the last completed task and continue.

### Crash recovery

If you resume a conversation and `workflow_state.json` already exists, read it once to determine the current phase:

- If `brief.status == "draft"` (or `brief` object is missing): re-enter the clarification phase (§3) with the existing `brief.md` as the starting draft.
- If `brief.status == "approved"` and `{workspace}/outline.md` exists and `tasks` is non-empty: resume the pipeline from the next runnable task using the existing task chain. If the user re-invoked the skill with a *different* raw query, ignore the new query — the approved brief is authoritative. The user must delete `.deep-research/{slug}/` to start fresh.
- If `brief.status == "approved"` but `outline.md` is missing *or* `tasks` is empty: the process died after approval but before outline creation or first task append. Resume at outline creation (§5), which will then append `eval-1`.
- If `brief.md` contains `## Approved` but `workflow_state.brief.status == "draft"`: the process died between the two approval writes. Treat as draft (workflow_state is authoritative), log a warning to the user, and re-prompt for approval.

All prior subagent results are in the `result` fields of completed tasks — you do not need conversation history.

## 5. Outline Creation

After the clarification phase approves the brief:

1. Read `{workspace}/brief.md`. Use the **Proposed outline** section as the starting structure for `outline.md`.
2. Identify the language of the research question. If ambiguous or indeterminate, use `"English"`. Store as `language` in `workflow_state.json`.
3. Expand the proposed headings into a hierarchical outline (up to 4 levels deep) with headings in the detected language, and persist:
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
4. The initial outline has NO `[sources: ...]` annotations -- that is expected
5. Initialize the source index:
   ```
   Write(file_path="{workspace}/source_index.json", content='{"page_info": {}, "url2id": {}, "executed_queries": []}')
   ```
6. **Append the first `eval-1` task** to `workflow_state.tasks` via the atomic Bash write pattern (§4):
   ```json
   {"id": "eval-1", "type": "evaluate", "status": "pending", "blocked_by": [], "iteration": 1, "result": null, "started_at": null, "completed_at": null}
   ```
   This is the first mutation of `tasks[]` in the workflow. The HARD GATE from §3 forbids any earlier task append.

**Outline rules:**
- `[sources: ID, ...]` annotations go on their own line below the subsection heading, never in the heading itself
- Citation format in the report: `[citation:Title](URL)`
- `[sources: ...]` lines are outline-only markers -- never include them in the final report

## 6. Research Loop

### Pipeline

```
eval-1 → gather-1 → eval-2 → gather-2 → ... → eval-N (research complete)
                                                   ↓
                                    write-ch2, write-ch3, ..., write-chK  (parallel)
                                                   ↓
                                              synthesize-1
                                                   ↓
                                          actionable issues?
                                           ↙              ↘
                                   re-write(s)          no → assemble
                                         ↓
                                    synthesize-2 → assemble
```

This is the main control loop. Execute it on every turn after the outline is created.

```
LOOP:
  Determine the next action set from routing fields already in context
    (in research phases this is one task; in writing phase it is the full writer batch)
  if no next action: DONE -- workflow complete

  Dispatch the action set based on task.type (see below)
  Extract routing fields from each subagent return into context
  Write each full result to workflow_state.json (atomic pattern, §4)
  Go to LOOP
```

### 6.1 Dispatching `evaluate` tasks

**Construct the dispatch:**
1. Read `${CLAUDE_SKILL_DIR}/evaluator.md`
2. Dispatch:
   ```
   Agent(
     prompt=<evaluator prompt content> + "\n---\nTASK:\n" + JSON.stringify({
       "research_question": "<user's original query>",
       "iteration": <N>,
       "workspace": "<workspace path>",
       "brief_path": "<workspace>/brief.md",
       "known_unfillable_gaps": <from convergence_check.py output>
     }),
     model="sonnet",
     description="evaluate research completeness"
   )
   ```

No `Read workflow_state.json` before dispatch. The director tracks `iteration` (incremented after each cycle) and `known_unfillable_gaps` (from convergence_check.py output) in its own conversation context.

**On return -- handle `research_complete`:**

If `research_complete` is `false`:

1. **Write evaluator result to disk** via the atomic Bash write pattern (§4). This MUST happen before the convergence check — the script reads from disk.
   ```json
   {"id": "eval-<N>", "type": "evaluate", "status": "completed", "iteration": <N>, "result": <full evaluator return>, "completed_at": "<ISO-8601>"}
   ```

2. **Apply outline evolution** (if `outline_evolution` is non-null):
   - Read current `{workspace}/outline.md`
   - Apply the evaluator's suggested restructuring
   - Preserve `[sources: ...]` annotations:
     - When merging sections: union their source IDs
     - When splitting: assign each ID to the most relevant new subsection
     - New sections start without sources
   - Write the revised outline
   - Apply outline evolution BEFORE creating the gather task.

3. **HARD GATE: Run convergence_check.py**
   ```
   Bash(command="python3 <convergence_script from workflow_state.json> {workspace}/workflow_state.json")
   ```

   The script output determines the next action. There is no alternative path.
   Do not assess convergence yourself. Do not skip this step.

   - If `actionable_gaps_remain` is `true`: create a gather task (step 4 below).
   - If `actionable_gaps_remain` is `false`: proceed to writing phase (§7). Store `known_unfillable_gaps` from the output into `workflow_state.json`.
   - If `forced_completion` is `true`: log the `reason` in `workflow_state.json`.

   **Script failure:** If the script exits non-zero, read stderr.
   - Malformed `workflow_state.json`: fix the JSON structure and re-run.
   - Missing task chain (no completed eval tasks): treat as iteration 1 — create the first eval task.
   - Python unavailable: this is a configuration error. Inform the user.
   Do not fall back to manual convergence checking — that reintroduces the problem the script solves.

4. **If actionable gaps remain:** Create a gather task (`gather-<N>`, blocked by `eval-<N>`).

If `research_complete` is `true`:

1. **Write evaluator result to disk** via the atomic Bash write pattern (§4). This MUST happen before the convergence check — the script reads from disk.
   ```json
   {"id": "eval-<N>", "type": "evaluate", "status": "completed", "iteration": <N>, "result": <full evaluator return>, "completed_at": "<ISO-8601>"}
   ```
2. **Run convergence_check.py** (same script, same rules as the `false` path):
   ```
   Bash(command="python3 <convergence_script> {workspace}/workflow_state.json")
   ```
3. If `actionable_gaps_remain` is `false`: proceed to writing phase (§7). Store `known_unfillable_gaps` in `workflow_state.json`.
4. If `actionable_gaps_remain` is `true`: treat as non-complete. Create a gather task.

**Iteration cap:** If `iteration >= 10`, skip and force-proceed to writing phase regardless of `research_complete`.

### 6.2 Dispatching `gather` tasks

**Construct the dispatch:**
1. Read `${CLAUDE_SKILL_DIR}/gatherer.md`
2. Dispatch using routing fields from the evaluator return (already in context):
   ```
   Agent(
     prompt=<gatherer prompt content> + "\n---\nTASK:\n" + JSON.stringify({
       "research_question": "<user's original query>",
       "queries": <suggested_queries from evaluator return>,
       "priority_section": <priority_section from evaluator return>,
       "knowledge_gap": <knowledge_gap from evaluator return>,
       "workspace": "<workspace path>"
     }),
     model="haiku",
     description="gather sources for <priority_section>"
   )
   ```

No `Read workflow_state.json`, `Read outline.md`, or `Read source_index.json` before dispatch. The gatherer reads `outline.md` and `source_index.json` itself.

**On return:**
1. Extract routing fields: `sources_added` count, one-line `summary`
2. Write full result to disk via the atomic Bash write pattern (§4)
3. Create an eval task (`eval-<N+1>`, blocked by `gather-<N>`, iteration `<N+1>`)

## 7. Writing Phase

When research completes (convergence_check.py returns `actionable_gaps_remain: false`), transition to the writing phase. For subagent return schemas, see `${CLAUDE_SKILL_DIR}/references/contracts.md`.

Do NOT read `workflow_state.json` during the writing phase. The director tracks writer completions and synthesizer status in its conversation context.

### 7.1 Creating writing-phase tasks

Create all tasks in `workflow_state.json` before dispatching any writer.

Let COMPLETION_TASK = the task ID that confirmed research completion (the eval task where convergence_check.py returned `actionable_gaps_remain: false`).

Initialize the report title:
```
Write(file_path="{outputs}/report.md", content="# <title>\n")
```

Read `{workspace}/outline.md` once to get chapter structure. Create tasks for each `##` chapter (skip Introduction and Conclusion):
```
For each ## chapter:
  - write-ch<N>:    type "write",       blocked_by: [COMPLETION_TASK]

After all write tasks:
  - synthesize-1:   type "synthesize",  blocked_by: ["write-ch2", "write-ch3", ..., "write-chK"]
```

Write all tasks to `workflow_state.json` via batch atomic Bash:

```bash
python3 -c "
import json, sys, tempfile, os
new_tasks = json.load(sys.stdin)
with open('{workspace}/workflow_state.json') as f: ws = json.load(f)
ws['tasks'].extend(new_tasks)
with tempfile.NamedTemporaryFile('w', dir='{workspace}', suffix='.tmp', delete=False) as tmp:
    json.dump(ws, tmp, indent=2)
os.replace(tmp.name, '{workspace}/workflow_state.json')
" <<'TASKS_EOF'
[{"id":"write-ch2","type":"write","status":"pending","blocked_by":["eval-5"],"result":null}, ...]
TASKS_EOF
```

### 7.2 Dispatching writers

**Construct all writer dispatches at writing phase entry:**
1. Read `${CLAUDE_SKILL_DIR}/writer.md` (once — do not re-read per writer)
2. Read `{workspace}/outline.md` (once)
3. Read `{workspace}/source_index.json` (once)
4. For each `##` chapter (excluding Introduction and Conclusion):

   **Numbering rule:** chapter file names and write-task IDs preserve outline chapter numbers. `## 3. Core Mechanisms` produces `write-ch3` and `chapter-3.md`. Introduction (ch1) and Conclusion are excluded from writer dispatch, so numbering starts at ch2.

   a. Extract subsection source annotations for this chapter from the outline
   b. Build `source_files` and `source_metadata` from `source_index.json`
   c. Dispatch:
   ```
   Agent(
     prompt=<writer prompt content> + "\n---\nTASK:\n" + JSON.stringify({
       "research_question": "<user's original query>",
       "chapter": "## 3. Core Mechanisms",
       "report_path": "{outputs}/chapter-3.md",
       "language": "<language from initial workflow_state.json creation>",
       "workspace": "<workspace path>",
       "outputs": "<outputs path>",
       "brief_path": "<workspace>/brief.md",
       "source_files": ["{workspace}/sources/2.md", "{workspace}/sources/5.md"],
       "source_metadata": {"2": {"title": "...", "url": "..."}, "5": {"title": "...", "url": "..."}}
     }),
     model="sonnet",
     description="write chapter: Core Mechanisms"
   )
   ```

Dispatch all writers in a single message (parallel execution). Each writer writes to its own chapter file so parallel writers don't conflict.

**On return -- check for partial writes:**
Compare `subsections_expected` against `len(subsections_written)`. If they differ, log the gap but do NOT create a re-write task. One pass per chapter.

Write each writer result to disk via the atomic Bash write pattern (§4).

### 7.3 Dispatching synthesizer

After all writers return, dispatch the synthesizer.

**Construct the dispatch:**
1. Read `${CLAUDE_SKILL_DIR}/synthesizer.md`
2. Use `known_unfillable_gaps` from conversation context (set during research-phase convergence) and `language` from conversation context (set at first turn)
3. Dispatch:
   ```
   Agent(
     prompt=<synthesizer prompt content> + "\n---\nTASK:\n" + JSON.stringify({
       "research_question": "<user's original query>",
       "language": "<language from conversation context>",
       "chapter_files": ["{outputs}/chapter-2.md", "{outputs}/chapter-3.md", ...],
       "intro_path": "{outputs}/intro.md",
       "conclusion_path": "{outputs}/conclusion.md",
       "known_unfillable_gaps": ["Section Name 1"],
       "iteration": <N>
     }),
     model="sonnet",
     description="synthesize report"
   )
   ```

**On return — verify file writes:**
Glob for `intro.md` and `conclusion.md` in `{outputs}`. If either missing: mark `"failed"`, create a fresh synthesize task, count against cap.

**On return — handle `status`:**
- `"done"`: proceed to assembly (§8).
- `"needs_action"` with `contradiction` issues: create re-write tasks for affected chapters with the contradiction description as context. Create new synthesize task blocked by those writes.
- `gap` and `alignment` issues: accept without re-dispatch.

**Cap:** max 2 synthesize rounds. After 2 rounds, accept and proceed to assembly (§8).

## 8. Assembly and Presentation

After the final synthesize task returns `"done"` (or the cap is reached):

### Assembly

1. **Generate Sources Consulted section:**
   a. Read `{workspace}/source_index.json`
   b. If `page_info` has zero entries, skip and log. Do not fail assembly.
   c. For each entry in `page_info`, ordered by numeric ID (integer sort):
      format as: `[N] Title. URL`
   d. Write to `{outputs}/references.md`

2. **Assemble the report:**
   a. Read `{outputs}/intro.md`, all chapter files in outline order, `{outputs}/conclusion.md`, and `{outputs}/references.md`
   b. Concatenate in order: intro + chapters + conclusion + references
   c. Write atomically:
      ```
      Write(file_path="{outputs}/report.md.tmp", content=<assembled report>)
      Bash(command="mv {outputs}/report.md.tmp {outputs}/report.md")
      ```

### Presentation

Tell the user the report is ready and print the absolute path to `{outputs}/report.md`. Do not read or output the report contents.

If the synthesize cap was reached and unresolved `contradiction` issues remain (from the synthesizer's return, already in context), include them in your message:

> Note: the following issues were detected during synthesis but could not be resolved within the synthesis cap:
> - [description of each unresolved contradiction from the issues array]

`gap` and `alignment` issues are accepted limitations — do not surface them to the user.

Workflow complete.

## 9. Error Handling

**Retry policy:**

| Failure type | Action |
|---|---|
| Context overflow | Retry with a narrower task scope (fewer queries, single subsection). |
| No output | Retry up to 2 times with the same input. |
| Permission denied | Mark `"failed"` — configuration issue. |
| Malformed return (non-JSON) | Retry once with same input. If still non-JSON, mark `"failed"`. |

When a task fails: mark `"failed"`, cascade to dependent tasks. Research tasks: create next iteration. Writing tasks: skip chapter.

### Crash Recovery by Subagent Type

| Subagent | State after crash | Director recovery |
|---|---|---|
| Evaluator | No workspace modification | Re-dispatch same task |
| Gatherer | Source files may exist without index entries | Glob sources, reconcile against source_index.json, re-dispatch |
| Writer | Chapter file may contain partial content | Grep subsections, compare count against outline, re-dispatch same assignment |
| Synthesizer | intro.md may exist without conclusion.md | Glob for both files, re-dispatch fresh synthesize task |

## 10. Director Discipline

### Iron Law

NEVER write report chapter prose yourself. ALWAYS delegate to writer.

### Rationalization Table

| Temptation | Reality |
|---|---|
| "I'll write [the chapter / intro / conclusion] myself to save turns" | NO. All prose goes through its designated subagent. |
| "The subsection count is close enough -- 3 of 4 is fine" | NO. Log the gap. Partial chapters produce incomplete reports. |
| "The synthesizer's issues are minor — the chapter is good enough" | NO. `needs_action` means action. Create follow-up tasks per protocol. |
| "The gatherer found nothing — no point running another eval" | NO. The evaluator determines whether a gap is unfillable, not you. Always create the next eval task. |
| "The subagent returned blocked, but it's probably a transient issue" | NO. Evaluate recoverability per §9. Don't dismiss `blocked` without investigation. |
