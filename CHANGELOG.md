# Changelog

Implementation history grouped by feature, newest first.

## 2026-04-13 — Clarification Gate

Adds an interactive clarification phase before the research pipeline starts. The director asks 0–3 clarifying questions (one at a time, multiple-choice preferred), then writes a research brief at `{workspace}/brief.md` and gets user approval before any eval, gather, or write task is dispatched. A non-interactive bypass (`DEEP_RESEARCH_SKIP_CLARIFICATION=1`) lets the eval harness skip the gate entirely.

### What changed

- **New `references/clarification.md`** — self-contained prompt spec for the clarification phase: when to ask questions vs. default, brief template (original query verbatim + restated question + audience + scope + constraints + known unknowns + clarification log), revision protocol (cap at 3, `revision_cap_overridden` flag), approval sequence with exact atomic-write bash incantations, edge cases, and anti-patterns table.
- **`SKILL.md` §1** — step 4 deferred path write to step 6; steps 6–7 added: create `workflow_state.json` with `brief` object in draft status and empty `tasks` array, then run the clarification phase.
- **`SKILL.md` §1.5** — new section: "Clarification Phase (HARD GATE)". No eval/gather/write task may be appended to `workflow_state.tasks` until `workflow_state.brief.status == "approved"`.
- **`SKILL.md` §2 First turn** — `workflow_state.json` schema now includes the `brief` object; `tasks` array starts empty; `eval-1` is appended only after brief approval.
- **`SKILL.md` §2 Crash recovery** — 4-branch decision tree: `brief.status == "draft"` re-enters clarification; `approved` with outline and tasks resumes pipeline; `approved` with missing outline or empty tasks reconstructs outline and appends `eval-1`; split-brain (markdown `## Approved` but state says draft) treats as draft and warns.
- **`SKILL.md` §3 Outline Creation** — new step 6 appends `eval-1` to `workflow_state.tasks` via atomic write after outline is created.
- **`SKILL.md` §4.1 / §4.3** — evaluator and writer dispatch task JSON gains `"brief_path": "<workspace>/brief.md"`.
- **`evaluator.md`** — new step 1 reads `brief_path`; `## Original query` section treated as untrusted data. New `<BRIEF_CONSTRAINTS>` block: out-of-scope gaps not flagged; timeframe/geography/language constraints filter suggested queries. Guidance is soft (prompt-level, not director-enforced).
- **`writer.md`** — new step 1 reads `brief_path`; same untrusted-input note. New `<BRIEF_ANCHORING>` block: audience/purpose calibrates tone and depth; out-of-scope sections avoided even when sources contain them. Also soft.
- **`tests/test_brief_fixture.py`** — 8 pytest tests pinning the expected `brief` object schema (`status`, `path`, `approved_at`, `revision_count`, `revision_cap_overridden`). Honest docstring: documents the expected shape; manual discipline required to update in lockstep with `SKILL.md`.

| Commit | Description |
|--------|-------------|
| `a529af5` | feat(clarification): add clarification phase reference file |
| `8d0f4c4` | feat(skill): workspace init creates workflow_state with brief; add §1.5 clarification gate; §3 appends eval-1 post-approval |
| `966546e` | feat(skill): pass brief_path in evaluate and write dispatches |
| `9505f68` | feat(evaluator): read brief and apply scope/constraints |
| `41a84b4` | feat(writer): read brief for tone and scope anchoring |
| `31045bc` | test: pin expected brief-object schema |
| `b7bd44c` | fix(skill): address code-review prose issues in §2 first-turn and clarification.md bypass |

---

## 2026-04-13 — Rollback: Codex CLI Platform Abstraction

Reverted the 2026-04-11 Codex CLI Support work from master. The skill is once again tied to the Claude Code platform: `${CLAUDE_SKILL_DIR}`, concrete model names (`sonnet`, `haiku`), and `Agent()` dispatch calls are restored. The platform-abstraction work is fully preserved on the `platform-abstraction` branch for future revival.

The six commits removed from master: `8cd5a7a`, `0160b4b`, `badd423`, `97ba74a`, `9427b3d`, `f47146f`. Master was rewritten via `git reset --hard 25c29ab` + cherry-pick of the seven non-abstraction commits. No functional changes — the skill behavior on Claude Code is identical to before the abstraction was introduced.

---

## 2026-04-12 — README Refresh and SKILL.md Consistency Fixes

### README refresh

Rewrote `README.md` to serve both newcomers discovering the plugin and existing users needing accurate reference:

- Replaced the one-liner description with a 4-paragraph narrative: the hook (director builds the outline), the research loop (evaluator + gatherer cycle), the writing phase (parallel writers + synthesizer), the output (`report.md` with inline citations)
- Restructured "How It Works" as a 5-step numbered workflow: Director → Evaluator → Gatherer → Writer → Synthesizer, with a one-line note on iteration cap (10) and parallel writing
- Fixed stale architecture references: Drafter/Editor → Writer, iteration cap 15 → 10
- Added Codex CLI installation section alongside the existing Claude Code instructions; updated Requirements section for both platforms
- Removed completed Synthesizer subagent roadmap item; kept 4 open items unchanged

### SKILL.md consistency fixes

Four targeted edits eliminating two inconsistencies identified in a post-implementation review, plus a cleanup of master.

**Issue 1 — LOOP pseudocode contradicted the disk-first architecture.** The main-loop pseudocode opened with `Read workflow_state.json` on every iteration, directly contradicting the "Do NOT read `workflow_state.json` during normal operation" rule stated three other times in §2. The pseudocode reflected the pre-Lean Director disk-driven scheduler; the rest of the spec had already moved to a context-driven model.

**Issue 2 — Chapter numbering.** The pipeline diagram and synthesizer dispatch example incorrectly started chapter numbering at `ch1`/`chapter-1.md`. Introduction (ch1) and Conclusion are excluded from writer dispatch; body chapters use outline-preserving numbering starting at `ch2`.

Additionally removed Tavily MCP preferences that had been merged to master by mistake; Tavily support is being developed on a separate feature branch.

- **Rewrote LOOP pseudocode** to match the context-driven model: the director determines the next action from routing fields already in context, not by reading `workflow_state.json`. Preserves the writing phase's parallel fan-out (all writers dispatched in a single message)
- **Fixed pipeline diagram** — writer task IDs now start at `write-ch2` (was `write-ch1`)
- **Fixed synthesizer dispatch example** — `chapter_files` now starts at `chapter-2.md` (was `chapter-1.md`)
- **Added explicit chapter-numbering rule** to §4.3: `## 3. Core Mechanisms` → `write-ch3` and `chapter-3.md`; numbering starts at `ch2` because Introduction is excluded
- **Removed Tavily gatherer preferences** — reverted `90b0b05`; belongs on `feature/tavily-integration`

| Commit | Description |
|--------|-------------|
| `636fc21` | Update README — narrative architecture, Codex install, remove completed roadmap |
| `98b7be1` | Rewrite LOOP pseudocode to context-driven model |
| `23b884c` | Fix pipeline diagram — writer tasks start at ch2, not ch1 |
| `5f7d2de` | Add explicit chapter-numbering rule to §4.3 |
| `92090a4` | Remove Tavily MCP preferences from master |

---

## 2026-04-11 — Codex CLI Support *(reverted 2026-04-13 — preserved on `platform-abstraction` branch)*

Makes deep-research-skill platform-neutral so it can run on Codex CLI with full parity alongside Claude Code. The approach: single shared skill files with per-platform reference docs; the director reads a reference doc at startup to resolve abstract model tiers and tool dispatch patterns to platform-native equivalents. No build step, no forked skill files.

### Architecture changes

- **Abstract model tiers.** Concrete model names (`sonnet`, `haiku`) replaced with tiers (`balanced`, `fast`) in `MODEL_CONFIG`. Each platform's reference doc maps tiers to concrete model names — Claude Code: `fast → haiku`, `balanced → sonnet`; Codex: `fast → o4-mini`, `balanced → gpt-4o`.
- **Platform-neutral dispatch pseudocode.** All 4 `Agent()` call sites converted to `dispatch subagent(role, tier, prompt_file, task, description)`. The platform reference doc provides the full dispatch lifecycle in native calls: Claude Code uses synchronous `Agent()`; Codex uses `spawn_agent` + `wait` + `close_agent`.
- **`${SKILL_DIR}` replaces `${CLAUDE_SKILL_DIR}`.** 7 occurrences updated. Each reference doc defines what `${SKILL_DIR}` resolves to on that platform.
- **Director startup step.** §1 preamble instructs the director to read the platform tools reference doc before beginning any research session. The bootstrap file (CLAUDE.md or AGENTS.md) identifies which doc to load.
- **Claude Code tools reference doc** (`references/claude-code-tools.md`). Documents the dispatch lifecycle, tool mapping table, model tier table, and evaluator tool scope for Claude Code. Can be loaded via `@`-include at bootstrap time so existing Claude Code users see no additional startup step.

Subagent files (`evaluator.md`, `gatherer.md`, `writer.md`, `synthesizer.md`, `contracts.md`) are unchanged — they continue using Claude Code tool names and are translated at runtime via the reference doc.

| Commit | Description |
|--------|-------------|
| `8cd5a7a` | Add Claude Code platform tools reference doc |
| `0160b4b` | Replace model names with abstract tiers in MODEL_CONFIG |
| `badd423` | Rename CLAUDE_SKILL_DIR to SKILL_DIR for platform neutrality |
| `97ba74a` | Convert evaluator + gatherer dispatches to platform-neutral pseudocode |
| `9427b3d` | Convert writer + synthesizer dispatches to platform-neutral pseudocode |
| `f47146f` | Update director preamble to platform-neutral dispatch and tool references |

---

## 2026-04-11 — Gatherer Model: Sonnet → Haiku

Changed gatherer from `sonnet` to `haiku`. The gatherer's workflow is mechanical — execute queries, fetch pages, save source files, update the source index, annotate the outline with source IDs — and does not require Sonnet-level reasoning. Its prompt is already highly prescriptive with numbered steps, hard rules, and explicit output format.

The evaluator acts as a safety net: if the gatherer stores low-quality sources or misses relevant results, the next evaluator cycle detects the gap and suggests better-targeted queries. The convergence script prevents runaway cycles.

Based on a sample run (487K total subagent tokens, ~147K from the gatherer at 30%), moving to Haiku pricing is estimated to reduce total subagent cost by 20–25%. No prompt changes; no workflow or dispatch protocol changes; no fallback logic changes.

Evaluator, writer, and synthesizer remain on Sonnet: the evaluator makes the highest-leverage convergence decisions and a premature "complete" costs more than a gather round; the writer's prose quality is the user-facing product; the synthesizer needs cross-chapter reasoning capability.

| Commit | Description |
|--------|-------------|
| `649645a` | Move gatherer subagent from sonnet to haiku |

---

## 2026-04-11 — Lean Director Pattern

Eliminates the director's Read-modify-Write cycle on `workflow_state.json`, which was the dominant cause of context bloat. A 123-turn run peaked at 102K context, consumed 4.67M tokens total, and failed to complete the writing phase; 63% of tokens were the director re-reading its own accumulated history.

### Root cause

The previous State Contract required the director to read `workflow_state.json` before every subagent dispatch, extract the previous result, inject fields into the dispatch JSON, then write the full result back after. Each evaluate/gather cycle added ~15K tokens to the director's context via this Read-modify-Write pattern. Subagents also received director-injected fields (`prior_eval`, `outline_excerpt`, `executed_queries`, `url2id`) that required additional reads per cycle.

### Architecture changes

- **Revised Iron Law.** "STORE SUBAGENT RETURNS VERBATIM" now specifies verbatim to disk only. The director's conversation context retains only routing fields — the minimum needed to decide the next action per subagent type.
- **Atomic Bash write pattern.** `workflow_state.json` is updated via a Python heredoc one-liner that performs an atomic write (temp file + rename) without reading the file into context.
- **Disk-first evaluator dispatch.** Removed pre-dispatch `Read workflow_state.json` and dropped `prior_eval` from the evaluator's INPUT. The evaluator now receives only: `research_question`, `iteration`, `workspace`, `known_unfillable_gaps` (from `convergence_check.py` output, already in context). Cross-iteration convergence detection moved fully to `convergence_check.py` + `known_unfillable_gaps`.
- **Self-serving gatherer.** Removed `outline_excerpt`, `executed_queries`, and `url2id` from the gatherer's INPUT. The gatherer reads `source_index.json` at the start of its own workflow to extract `executed_queries` and `url2id` for duplicate detection. Also removed the post-return source integrity verification (Glob + Read `source_index.json`) from the director — the evaluator catches coverage discrepancies on the next cycle.
- **Consolidated writing-phase reads.** `writer.md`, `outline.md`, and `source_index.json` are read once at writing phase entry. All writer task JSONs are built from that single read. Per-writer re-reads eliminated.
- **Removed DAG-driven writing-phase loop.** Replaced `Read workflow_state.json → find runnable tasks → loop` with procedural dispatch: all chapter writers dispatched in one parallel message; synthesizer dispatched after all writers return. The director tracks writer completions in conversation context.

### Expected impact

| Metric | Before | After |
|--------|--------|-------|
| Director context peak | 102K | ~48K |
| Director context growth per cycle | ~15K | ~3.3K |
| Director total tokens | 2,930K | 600–900K |
| Full pipeline total tokens | 4.67M (incomplete) | 1.5–2M (complete) |

### Files

| Commit | Description |
|--------|-------------|
| `e8e5e4d` | Rewrite §2 State Contract — Iron Law to disk only, routing fields table, atomic write pattern |
| `6753a0b` | Update §1 dispatch overview to match new state contract |
| `3a477ce` | Slim evaluator dispatch — drop `prior_eval`, pre-dispatch `workflow_state.json` read; disk-write before convergence check |
| `5729456` | Slim gatherer dispatch — drop `outline_excerpt`, `executed_queries`, `url2id`, post-return source integrity check |
| `1092a63` | Consolidate writing-phase reads — `writer.md`, `outline.md`, `source_index.json` read once at writing phase entry |
| `1cac065` | Rewrite writing-phase loop and synthesizer dispatch — no `workflow_state.json` reads |
| `9111b86` | Drop `prior_eval` from `evaluator.md` — convergence handled by `convergence_check.py` + `known_unfillable_gaps` |
| `cf83a9e` | `gatherer.md` self-serves `executed_queries` and `url2id` from `source_index.json` |
| `25c29ab` | Fix stale convergence reason string — cap is 10, not 15 |

---

## 2026-04-10 — Token Optimization Redesign

Major structural simplification to reduce token consumption by ~45-55% (structural savings) plus ~5x cost reduction from Sonnet subagent dispatch. The pipeline was too expensive to run eval tasks at scale, and most complexity had been added prophylactically rather than in response to observed failures.

### Architecture changes

- **Merged drafter + editor into single writer agent.** The two-pass model (draft then enrich with citations) is replaced by a single writer that drafts with inline citations and specific source data from the start. This eliminates K subagent dispatches per report (one editor per chapter). The writer uses the CECI pattern and receives `source_files` + `source_metadata` directly in its task JSON.
- **Removed false-completion verification loop.** The evaluator re-dispatch that double-checked `research_complete: true` is removed. `convergence_check.py` is now the sole convergence gate.
- **Reduced iteration cap from 15 to 10.** No empirical evidence justified 15. Late-iteration data capture window (8-10) is preserved.
- **Per-subagent model dispatch.** `<MODEL_CONFIG>` block in SKILL.md defines model per agent type. All subagents default to Sonnet; director inherits session model (typically Opus).
- **Workspace paths via task JSON.** Subagent prompts no longer contain `<WORKSPACE>` blocks with hardcoded path patterns. The director passes `workspace`, `outputs`, and related paths in each task JSON. This eliminates placeholder substitution in prompt construction.

### Prompt optimization

- **Temptation/reality tables trimmed.** Full tables (5-9 entries) replaced with 2-3 highest-risk entries per prompt, targeting anti-patterns documented in the benchmark optimization guide. Bulk defensive prose removed.
- **Evaluator calibration examples abbreviated.** 3 full examples replaced with 1 good + 1 bad abbreviated example as a behavioral anchor for Sonnet.
- **Output schemas moved to contracts.md.** Subagent prompts reference `contracts.md` instead of inlining full JSON schemas.
- **Synthesizer simplified.** Four cross-chapter check types (contradiction, coverage gap, alignment, forward-ref) reduced to one-line contradiction detection. Forward-reference validation and coverage gap analysis removed.
- **Re-draft and re-edit retry loops removed.** One pass per chapter. If quality is poor, the prompt is the problem.

### Files

| Commit | Description |
|--------|-------------|
| `dd954c9` | Reduce iteration cap from 15 to 10 in convergence_check.py (with test update) |
| `d46610a` | Update contracts.md: add writer contract, remove drafter/editor, cap 10 |
| `176cb0c` | Add writer.md — merged drafter+editor prompt |
| `b12f83a` | Simplify evaluator prompt — trim tables, abbreviate calibration |
| `818c26e` | Simplify gatherer prompt — trim tables, paths via task JSON |
| `d071a80` | Simplify synthesizer — one-line contradiction check, trim tables |
| `e7abd2c` | Rewrite SKILL.md — writer pipeline, model config, no false-completion |
| `8ec5445` | Remove drafter.md and editor.md |
| `01969d7` | Activate Phase 2 — Sonnet for all subagent dispatches |

### Maintainer notes

- **Deferred features.** Every removed feature has a concrete, observable condition for reinstatement (listed below under each item). Consult these before re-adding complexity.
- **Editor reinstatement trigger.** If >30% of factual claims in any chapter lack citations after running evals, reinstate a separate editor pass.
- **Iteration cap tuning.** If 90%+ of tasks converge by iteration 7 in eval data, lower the cap. If forced completion at 10 leaves fillable gaps on >30% of tasks, raise it.
- **Model upgrades.** If Sonnet consistently underperforms on a specific agent role despite prompt tuning, upgrade that one agent to Opus — don't upgrade all of them.
- **The bitter lesson applies.** Every piece of removed scaffolding was compensating for an assumed model limitation. Before re-adding it, verify the failure actually occurs with the current model.

---

## 2026-04-09 — Move Scripts Under Skill Directory

Relocate `convergence_check.py` from repo-root `scripts/` into `skills/deep-research/scripts/` to co-locate it with the skill that owns it. Eliminates fragile `../../` path traversal in SKILL.md.

| Commit | Description |
|--------|-------------|
| `dd03fc4` | Move convergence_check.py under skill directory, update SKILL.md and test paths |

---

## 2026-04-09 — Benchmark Prompt Alignment

Proactive alignment pass targeting gaps between the benchmark evaluation criteria and subagent behavior, before the next live test round. 11 sentence- or paragraph-level additions across 5 files — no structural changes, no new files.

Each addition maps to a specific benchmark dimension:

- **Evaluator** — distinguish topic-level vs data-level coverage (a section that discusses a topic without specific values, dates, or entity names has a data gap); verify all research question components (geography, time period, comparison set) before declaring complete; require late-iteration queries to target specific metrics, not broad topic terms
- **Gatherer** — target 3+ independent sources per major claim area; clarify that queries targeting the same topic but different organizations are not semantically equivalent (both should run); preserve exact numerical values, entity names, and dates from fetched content
- **Drafter** — emphasize Comparison and Implication steps in the CECI pattern; a subsection that stops at Evidence reads as a fact list
- **Editor** — extend analytical enrichment beyond facts to causation, trade-offs, and implications
- **Synthesizer** — add explicit scope statement (geography, time period, knowledge cutoff); identify future directions where the evidence points but doesn't fully resolve; acknowledge known unfillable gaps as explicit research limitations

| Commit | Description |
|--------|-------------|
| `766417e` | Add data-level gap detection, instruction fidelity check, and late-iteration query specificity to evaluator |
| `73e5c64` | Add source diversity target (3+), semantic-equivalence clarification with cap, and value preservation to gatherer |
| `49a6a2b` | Emphasize Comparison and Implication steps in drafter CECI pattern |
| `7d9491f` | Add analytical enrichment requirement with example to editor |
| `defd476` | Add scope statement, future directions, and limitations acknowledgment to synthesizer |

---

## 2026-04-09 — Protocol Fixes

Structured response to 17 issues identified during a review of the first real-world run (Japan elderly market: 22 sources, 9 chapters). The run revealed that the director was summarizing subagent returns rather than storing them verbatim, the convergence check was optional rather than gated, writing-phase tasks weren't tracked in the workflow state, and the gatherer had no format guidance for outline annotations.

Five fixes applied to SKILL.md and the gatherer prompt:

- **Workspace init checklist.** Before outline creation, the director verifies the convergence script is reachable (`convergence_check.py --help`) and stores the resolved absolute path in `workflow_state.json`. Research does not start if the script is missing.
- **State Contract with Iron Law.** A new §2 section adds the Iron Law ("STORE SUBAGENT RETURNS VERBATIM — NO SUMMARIZING, NO KEY RENAMING, NO FIELD OMISSION"), a rationalization table for state-corruption temptations (composite keys, integer compression, empty arrays), and the full result schema the director must write on every subagent return.
- **Convergence Hard Gate.** The convergence check is now mandatory after every evaluator return, before any gather dispatch. The resolved script path from init is stored and used for every call.
- **Writing-phase state management.** Draft, edit, and synthesize tasks are now created in `workflow_state.json` before dispatch, under the same DAG model as research tasks. The writing phase is no longer "off-book."
- **Gatherer annotation format.** Exact inline format for annotating outline sections with source IDs (`[sources: 1, 2, 3]`), with examples, added to the gatherer prompt.

| Commit | Description |
|--------|-------------|
| `8db0da9` | Add workspace init checklist — convergence script verification before research starts |
| `ccaf63a` | Add State Contract — Iron Law, rationalization table, result schema |
| `42a06e9` | Make convergence check a Hard Gate — mandatory after every evaluator return |
| `2c83b2b` | Restructure writing phase — draft/edit/synthesize tasks tracked in workflow_state.json |
| `e503442` | Specify exact outline annotation format with examples in gatherer |

---

## 2026-04-08 — Multilingual Reports

Reports were English-only regardless of query language. The director now detects the query language, stores it in `workflow_state.json`, and passes it through all writing-phase dispatches. Drafter, editor, and synthesizer produce prose in the target language; outline headings are also written in the target language so the drafter can use them directly as report section headings.

Key design decisions: search stays English-only as a pragmatic default (broader source coverage; target-language search deferred for validation). Citation format remains `[citation:English Title](URL)` — honest, since the linked page is in English. Internal prompts and director messages remain in English. Ambiguous or short queries default to English. The research phase (evaluator, gatherer, convergence) is language-agnostic and unchanged.

| Commit | Description |
|--------|-------------|
| `01e4b4a` | Add language detection to director — stored in workflow_state.json; outline headings in target language |
| `f5c7490` | Pass language field through drafter, editor, and synthesizer dispatches |
| `c98906c` | Add multilingual editing instructions to editor — preserve target-language expression, don't introduce English phrasing |
| `ffa83dd` | Add multilingual writing instructions to drafter — target-language prose, handle source-language bridging for citations |
| `45179ab` | Add multilingual writing instructions to synthesizer — Introduction and Conclusion in target language |
| `8f2e470` | Update roadmap — add multilingual scoping note and research clarification step item |

---

## 2026-04-08 — Deep Research Skill Refinement

Structured response to a full design and implementation review against the agent engineering and Superpowers design guides. Eight issues addressed across 11 commits; four issues deferred (evaluator tool restriction, model tier specification, SKILL.md length, eval methodology).

### Changes

- **Unified status vocabulary.** Each subagent previously used its own status strings (`research_complete: true/false`, `status: "pass" | "needs_revision"`, `status: "pass" | "issues_found"`, no status field). All subagents now return a shared three-value enum — `done / needs_action / blocked` — giving the director a single routing vocabulary across all agent types.
- **Convergence logic moved to code.** The convergence check — comparing current section gaps against prior evaluator results, tracking unfillable gaps across iterations — was expressed as prose instructions for the director to follow on every evaluation turn. This is now `convergence_check.py`: a pure Python function with JSON I/O, no side effects, and a test suite. The SKILL.md dispatch section invokes it via Bash rather than describing the algorithm in prompt text.
- **Parallel dispatch cap removed.** The hardcoded limit of 3 concurrent `Agent()` calls in §2 is removed. The full writing phase can now dispatch all chapter writers in one message.
- **Pipeline diagram added.** A visual task graph in SKILL.md §4 shows the full evaluate → gather → write → synthesize workflow.
- **Orchestration anti-rationalization.** §6 restructured with an orchestration-specific rationalization table (don't dismiss BLOCKED status, don't treat `needs_action` as `done`, don't skip verification) and a red flags list for the director's own failure modes.
- **Crash recovery consolidated.** Director crash recovery procedure moved from scattered inline notes to a dedicated §5. Crash resilience notes in drafter and editor prompts removed — it was describing director behavior in subagent context, wasting their prompt tokens.
- **Plugin description aligned** with triggering conditions rather than describing the workflow (which belongs in SKILL.md, not in plugin discovery metadata).
- **SKILL.md trim.** Rationalization table cut from 15 to 8 entries (vestigial entries made redundant by the convergence script; duplicate entries merged). Error handling restructured: Layer 3 quality-shortfall rows removed (duplicated §4 dispatch rules); task JSON boilerplate blocks replaced with one-liners. Net: ~74 lines removed.

| Commit | Description |
|--------|-------------|
| `b4cfbea` | Align plugin description with triggering conditions, not workflow details |
| `6298765` | Remove fixed parallel dispatch cap of 3 from §2 |
| `5efced4` | Add pipeline diagram to §4 dispatch rules |
| `f336555` | Restructure §6 — orchestration rationalization table and red flags list |
| `f66580a` | Move director crash recovery to §5; remove crash resilience notes from subagent prompts |
| `3a421b8` | Add unified status vocabulary (done/needs_action/blocked) to contracts.md |
| `715648d` | Add unified status field to evaluator, gatherer, drafter prompts |
| `f334f69` | Align editor, synthesizer, and SKILL.md to unified status vocabulary |
| `9dcbe9f` | Add convergence_check.py with test suite |
| `a863a48` | Replace §4.1 convergence prose with convergence_check.py invocation |
| `195569f` | Trim SKILL.md — rationalization table 15→8, restructure error handling, remove task JSON boilerplate |

---

## 2026-04-07 — Synthesizer Subagent

The original pipeline had no whole-document view. Introduction and Conclusion were written by the director without evidence grounding, and no agent could detect cross-chapter contradictions, coverage gaps, research question misalignment, or dangling forward references. `validate_report.py` provided mechanical sanity checks only.

The synthesizer is the fifth subagent. It runs after all chapter edits complete and holds the only full-document context in the system. It owns three responsibilities:

1. **Write Introduction and Conclusion** — post-editing, with all chapters as context, so both sections reflect what the report actually argues rather than what was planned in the outline
2. **Cross-chapter consistency check** — factual contradictions, coverage gaps, and dangling forward references
3. **Research question alignment** — confirms the assembled report answers what was asked

Returns a structured issues list with per-issue type routing: `contradiction` and `forward_ref` trigger targeted re-edit tasks and a re-dispatch; `gap` and `alignment` issues are accepted without re-dispatch (no gather phase remains). Capped at 2 synthesize rounds; unresolved issues from the final round are surfaced to the user at the present step.

Assembly is atomic: director concatenates intro + chapters + conclusion into `report.md.tmp`, then renames to `report.md`. `validate_report.py` is removed.

| Commit | Description |
|--------|-------------|
| `bd6717f` | Add synthesizer return contract to contracts.md |
| `0014c95` | Add synthesizer subagent prompt |
| `452a680` | Address code review issues in synthesizer.md — add Iron Law, rationalization table, WHEN_BLOCKED, atomic assembly |
| `9f0fea8` | Add synthesizer to SKILL.md subagent table |
| `d6dbd6c` | Update writing-phase task DAG and atomic assembly for synthesizer |
| `022ceab` | Add synthesize dispatch section (§4.6) with issue-type routing and cap logic |
| `02004e3` | Update present step to surface unresolved issues; add Synthesize BLOCKED to error table |
| `e3248c0` | Add synthesizer discipline rules to §6 rationalization table |
| `bf4f50b` | Remove validate_report.py — replaced by synthesizer |
| `4158afb` | Mark synthesizer complete in roadmap; remove Python 3 requirement |
| `06ec4b3` | Address final review issues — README validator reference, director tool list |

---

## 2026-04-07 — Consistency and Naming Unification

Pre-review standardization pass to align all five prompt files and SKILL.md before the first external design review. Four categories of changes applied uniformly across the codebase.

**File naming.** All subagent files drop the `-prompt` suffix (`evaluator-prompt.md` → `evaluator.md`, etc.), matching the convention used in SKILL.md dispatch instructions.

**Structural layout.** Each prompt's role definition is wrapped in `<ROLE>` tags for a consistent parsing boundary. SKILL.md's preamble, section ordering, and task schema are restructured to match the updated prompt conventions.

**Terminology alignment.** Workspace paths, source naming, task field names, and status vocabulary are standardized across all files — eliminating per-file variations that had accumulated during the initial implementation sprint.

**Contract extraction.** Subagent return schemas are moved out of each individual prompt and into `references/contracts.md` as a single authoritative reference. Prompts now cite the contract file rather than inlining their own schema copies.

| Commit | Description |
|--------|-------------|
| `7eccf98` | Rename subagent files — drop `-prompt` suffix across all four files |
| `4900d63` | Standardize evaluator prompt — role boundary, workspace terminology, output schema |
| `13c2721` | Complete terminology cleanup in evaluator.md |
| `119d814` | Final terminology fixes in evaluator.md |
| `bcd0fd2` | Standardize drafter prompt — role boundary, workspace terminology, INPUT section |
| `753681c` | Standardize gatherer prompt — role boundary, workspace terminology, source naming, output schema |
| `8be7b73` | Standardize editor prompt — role boundary, workspace terminology, content standards |
| `3fc66a8` | Align INPUT section terminology in drafter and editor |
| `826228e` | Code quality fixes across gatherer, drafter, editor |
| `14760bc` | Extract subagent return contracts to references/contracts.md |
| `208b1ea` | Restructure SKILL.md — preamble, layout, task schema |
| `bc2bcf8` | Move preambles inside `<ROLE>` tags across all prompts |
| `51e7df5` | Update README and improve skill description |

---

## 2026-04-06 — Initial Implementation

Establishes the director/subagent architecture with four specialized subagents, a director orchestration layer, and a filesystem-backed state model.

### Architecture

**Director** (`SKILL.md`) — orchestrates all subagents, never produces report content directly. Core responsibilities:

- Workspace initialization: derives a topic slug, creates `.deep-research/{slug}/workspace/` and `outputs/`, gitignores `.deep-research/`
- Workflow state: `workflow_state.json` tracks every task with `id`, `type`, `status`, `blocked_by`, `result`, and timestamps. All subagent returns are stored verbatim
- Research loop: dispatches evaluator → if incomplete, dispatches gatherer → loops until evaluator declares `research_complete: true` or iteration cap is reached
- Writing phase: dispatches one drafter per chapter, then one editor per chapter, then `validate_report.py`, then assembles `report.md` via atomic temp-file rename
- Crash recovery: reads `workflow_state.json` on session resume to determine last completed task

**Subagents** — each receives a prompt file content + JSON task assignment, runs in an isolated context, returns structured JSON:

| Subagent | Responsibility |
|----------|---------------|
| `evaluator` | Reads workspace state; evaluates research completeness against outline; identifies section gaps and suggests queries; returns `research_complete` flag |
| `gatherer` | Executes search queries, fetches pages, stores source files, annotates outline sections with source IDs |
| `drafter` | Writes one chapter's prose from outline + evidence using the CECI pattern (Claim → Evidence → Comparison → Implication) |
| `editor` | Enriches one drafted chapter: replaces vague claims with specific data, adds inline citations |

**`validate_report.py`** — post-assembly script validating report structure and citation completeness. Replaced by the synthesizer subagent in 2026-04-07.

### State model

The workspace directory layout established here persists across all subsequent revisions:

```
.deep-research/{slug}/
  workspace/
    workflow_state.json   — task DAG and all subagent results
    outline.md            — research outline with source annotations
    source_index.json     — source metadata and executed queries
    sources/              — per-source markdown files
  outputs/
    chapter-N.md          — one file per chapter
    report.md             — final assembled report
```

| Commit | Description |
|--------|-------------|
| `0dd6512` | Initialize plugin scaffold (`.claude-plugin/`, directory layout) |
| `f39fa7d` | Add report validation script |
| `e2d1ab3` | Add evaluator subagent prompt |
| `6cc1bf7` | Add gatherer subagent prompt |
| `b3bb7ed` | Add drafter subagent prompt |
| `ae14311` | Add editor subagent prompt |
| `9672b11` | Add SKILL.md director instructions |
| `7cd965c` | Add README with installation and usage instructions |
| `0052fe5` | Fix: director prints report path, not full report contents, at present step |
