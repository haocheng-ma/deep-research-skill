# Deep Research Plugin for Claude Code

It starts from the moment you ask a research question. The Director presents a research directive — scope, audience, constraints — for your approval. Once you approve, it builds a research outline and the loop begins.

An Evaluator reads the outline and scores what's covered. Where gaps exist, a Gatherer goes to work: searching the web, fetching pages, storing sources, annotating the outline. The loop runs until the evidence is solid — or the iteration cap is reached.

Once research converges, Writers tackle every chapter in parallel. Each one uses the CECI pattern — Claim, Evidence, Comparison, Implication — writing with inline citations drawn directly from the gathered sources. When the chapters are done, a Synthesizer reads them all together, writes the Introduction and Conclusion, and catches any cross-chapter contradictions before final assembly.

The result: a structured report with inline citations, saved to `.deep-research/<topic>/outputs/report.md`.

## Installation

**Install:**
```
/plugin marketplace add haocheng-ma/deep-research-skill
/plugin install deep-research@deep-research-skill-dev
```

**For local development:**
```
claude --plugin-dir ./deep-research-skill
```

**Update to latest version:**
```
/plugin update deep-research
```
Restart your session after updating.

**Uninstall:**
```
/plugin uninstall deep-research
```

### Verify Installation

Start a new session and ask a research question. Claude should invoke the skill automatically, or trigger it explicitly with `/deep-research <topic>`.

## Usage

```
/deep-research <your research topic>
```

Or just ask a research question — Claude will invoke the skill automatically when it detects a question requiring in-depth research.

## How It Works

1. **Director** — presents a research directive (scope, constraints, audience) and gets your approval before committing to a research run
2. **Director** — builds a research outline from the approved directive: chapters, subsections, the shape of a thorough answer
3. **Evaluator** — scores the outline against gathered evidence; identifies gaps and suggests follow-up queries
4. **Gatherer** — executes searches, fetches pages, annotates the outline with source IDs
5. **Writer** — writes each chapter in parallel using the CECI pattern (Claim, Evidence, Comparison, Implication) with inline citations drawn from gathered sources
6. **Synthesizer** — reads all chapters together; writes Introduction and Conclusion; checks for cross-chapter contradictions

The clarification phase (step 1) produces a research directive that anchors scope, audience, and constraints for the entire run. The evaluate-gather loop (steps 3-4) runs until evidence is sufficient or the iteration cap (10) is reached. Writing (step 5) parallelizes all chapters at once.

## Output

Research artifacts are stored in `.deep-research/<topic-slug>/`:

```
.deep-research/
└── sovereign-wealth-funds/
    ├── workspace/
    │   ├── outline.md              # Research outline with source annotations
    │   ├── source_index.json       # Source metadata and query history
    │   ├── workflow_state.json     # Execution state (research directive, tasks)
    │   └── sources/                # Raw fetched content (1.md, 2.md, ...)
    └── outputs/
        ├── intro.md               # Introduction (written by synthesizer)
        ├── chapter-2.md, ...      # Chapter files (written by writers)
        ├── conclusion.md          # Conclusion (written by synthesizer)
        ├── references.md          # Sources consulted
        └── report.md              # Final assembled report
```

## Requirements

- Claude Code with Agent, WebSearch, and WebFetch tools available
- Ensure `.deep-research/` is gitignored in your repo (the skill writes large scratch artifacts there)

## Roadmap

- [ ] **Behavioral testing** — Validate director orchestration and subagent compliance under pressure scenarios (e.g., false completion, partial drafts, convergence stalls).
- [ ] **Multilingual reports** — Reports are currently English-only. Add language detection so the report output matches the user's query language. Initial implementation searches in English only; which language to search in — and whether to search in both languages — needs validation through testing and user feedback.

## License

MIT
