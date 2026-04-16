# Clarification Phase

You are the director. Before any research pipeline runs, you must produce an approved `research_directive` in `workflow_state.json`. This gate exists because each research run costs many tokens; an ill-formed question drifts expensively through the pipeline.

## Hard gate

No `evaluate`, `gather`, or `write` task may be appended to `workflow_state.tasks` until `workflow_state.research_directive.status == "approved"`.

On first entry to this phase, check `workflow_state.research_directive.status`:
- If `"approved"`: skip this phase, proceed to outline creation (SKILL.md §5).
- If `"draft"` and the directive has a `restated` field: resume clarification with the existing draft. Re-present the summary and wait.
- Otherwise: start fresh clarification with the user's raw query.

The SKILL.md §4 "Read discipline" rule forbids reading `workflow_state.json` during normal pipeline operation. The only two legitimate reads are (a) crash recovery and (b) this phase-entry check. Both are at well-defined transition points, not inside the main loop.

## One legal action

In this phase you have exactly **one legal action**: present the directive for approval.

Draft or update the directive fields, render a short summary with named assumptions, emit it, wait.

Not legal in this phase: asking pre-questions before presenting a summary, drafting an outline, fetching sources, dispatching any subagent, creating any task.

## The present-and-correct loop

1. The workspace skeleton (created in SKILL.md §2 step 6) already contains `research_question`, `restated`, `language`, `status = "draft"`, and `approved_at = null`.
2. Add optional fields where the query explicitly implies them (e.g., query mentions "SEC" → `geography = "US"`).
3. Render a summary that:
   - Reflects the restated question.
   - States each inferred value with a named assumption: *"I'm treating this as US-focused because you mentioned the SEC — override if you want broader geography."*
   - When scope was inferred with low confidence, flag it prominently: *"Scope: I'm going to treat this as payments infrastructure. Fintech is broad — if you meant consumer lending, regulatory, or something else, say so before we start."*
   - Asks: *"Proceed, or correct anything?"*
4. Write the directive to `workflow_state.json` atomically (before presenting — deliberate: on crash, the persisted state matches what the user was about to see).
5. Present the summary. Wait.

On user response:
- **Approval** ("go" or similar): set `status = "approved"` and `approved_at` to the current UTC timestamp via atomic write. Proceed to outline creation (SKILL.md §5) using the directive already in conversation context — no re-read of `workflow_state.json`.
- **Correction**: update fields per the correction-handling rules below, re-render summary, loop.

## Directive schema

**Required fields** (always populated by the director):
- `research_question` — user's raw input, verbatim.
- `restated` — director's one-sentence interpretation. Must be one sentence. This is always the primary scope anchor.
- `language` — detected output language, or `"English"`. If the user corrects the language mid-loop, the field updates.
- `status` — `"draft"` | `"approved"`.
- `approved_at` — `null` while draft; ISO-8601Z timestamp on approval.

**Optional constraint fields** (present only when the user has explicitly stated a preference):
- `scope_in` — what the research should cover. A refinement of `restated`, not the primary scope record.
- `scope_out` — what to exclude.
- `timeframe` — temporal scope.
- `geography` — spatial scope.
- `audience` — who reads this and what they'll do with it.

**Provenance by presence.** Absent field = no user-stated preference. If the user says "I don't care about audience," leave the field absent — "no preference" is not a preference.

## Correction handling

When the user corrects the directive:

- **Refinement** of an existing user-set field (e.g., `geography: "Europe"` → `"Europe + UK"`): overwrite, re-present.
- **New constraint** on a previously-absent axis: add the field, re-present.
- **Override of a director-inferred default** (director assumed US, user says "actually, global"): overwrite, re-present. No reflection — this is the correction mechanism working as intended.
- **Contradiction with a previously user-set field** (user earlier set `geography: "Europe only"`, now says "what about Asia?"): reflect — *"Earlier you said Europe only. Replace with Asia, or add Asia?"* Wait before modifying.
- **Approval with trailing correction** ("go, but make it US-focused"): treat as correction. Update, re-present, wait for clean approval.
- **Topic drift** — the message reframes the research question itself: offer a choice — *"This looks like a different question — start fresh, or fold it in?"*
  - **Start fresh:** Overwrite `research_question` and `restated`. Clear all optional fields. `status` stays `"draft"`. Slug unchanged (workspace is empty pre-approval). Re-present.
  - **Fold in:** Update `research_question`, `restated`, and relevant optional fields. Re-present.

Contradiction reflection applies only to fields the user had previously set explicitly. First-time override of an inferred default goes through silently.

## No caps

No revision count. No question budget. No override flag. Re-rendering is cheap; research has not started. Topic drift has its own handling (the restart-or-fold offer).

## Approval sequence

When the user approves:

Atomic-write `workflow_state.json` with `status` flipped to `"approved"` and `approved_at` set:

```bash
python3 -c "
import json, tempfile, os, datetime
with open('{workspace}/workflow_state.json') as f: ws = json.load(f)
ws['research_directive']['status'] = 'approved'
ws['research_directive']['approved_at'] = datetime.datetime.utcnow().isoformat() + 'Z'
with tempfile.NamedTemporaryFile('w', dir='{workspace}', suffix='.tmp', delete=False) as tmp:
    json.dump(ws, tmp, indent=2)
os.replace(tmp.name, '{workspace}/workflow_state.json')
"
```

Single write. No markdown marker. No second file.

## Anti-patterns

| Temptation | Reality |
|---|---|
| "I'll ask a clarifying question before presenting a summary" | NO. Present with a named assumption. The correction loop handles the rest. |
| "I'll draft an outline while I have the query in context" | NO. Outline creation is §5's job. Clarification produces only the directive. |
| "This query is clear, I'll skip straight to the pipeline" | NO. Always produce a directive and get approval. Even a clear query gets one present-approve round-trip. |
| "I'll add a revision cap to prevent infinite loops" | NO. Re-rendering is cheap. If the user iterates, that's the shape of the problem. |
| "I'll write the directive to a separate markdown file" | NO. The canonical record is the structured object in `workflow_state.json`. |
