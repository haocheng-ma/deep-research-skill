# Deep Research Plugin for Claude Code

It starts from the moment you ask a research question. Instead of a quick summary, the Director analyzes your question and builds a research outline — chapters, subsections, the shape of what a thorough answer would actually look like.

Then the research loop begins. An Evaluator reads the outline and scores what's covered. Where gaps exist, a Gatherer goes to work: searching the web, fetching pages, storing sources, annotating the outline. The loop runs until the evidence is solid — or the iteration cap is reached.

Once research converges, Writers tackle every chapter in parallel. Each one uses the CECI pattern — Claim, Evidence, Comparison, Implication — writing with inline citations drawn directly from the gathered sources. When the chapters are done, a Synthesizer reads them all together, writes the Introduction and Conclusion, and catches any cross-chapter contradictions before final assembly.

The result: a structured report with inline citations, saved to `.deep-research/<topic>/outputs/report.md`.

## Installation

**From marketplace** — not yet published; use the local dev install below.

**For local development:**
```
claude --plugin-dir ./deep-research-skill
```

### Verify Installation

Start a new session and ask a research question. Claude should invoke the skill automatically, or trigger it explicitly with `/deep-research <topic>`.

## Usage

```
/deep-research <your research topic>
```

Or just ask a research question — Claude will invoke the skill automatically when it detects a question requiring in-depth research.

## How It Works

1. **Director** — analyzes your question and builds a research outline: chapters, subsections, the shape of a thorough answer
2. **Evaluator** — scores the outline against gathered evidence; identifies gaps and suggests follow-up queries
3. **Gatherer** — executes searches, fetches pages, annotates the outline with source IDs
4. **Writer** — writes each chapter in parallel using the CECI pattern (Claim → Evidence → Comparison → Implication) with inline citations drawn from gathered sources
5. **Synthesizer** — reads all chapters together; writes Introduction and Conclusion; checks for cross-chapter contradictions

The evaluate→gather loop (steps 2–3) runs until evidence is sufficient or the iteration cap (10) is reached. Writing (step 4) parallelizes all chapters at once.

## Output

Research artifacts are stored in `.deep-research/<topic-slug>/`:

```
.deep-research/
└── sovereign-wealth-funds/
    ├── workspace/
    │   ├── outline.md              # Research outline
    │   ├── source_index.json       # Source metadata
    │   ├── workflow_state.json     # Execution state
    │   └── sources/                # Raw fetched content
    └── outputs/
        └── report.md              # Final report
```

The `.deep-research/` directory is automatically gitignored.

## Requirements

- Claude Code with Agent, WebSearch, and WebFetch tools available

## Roadmap

- [ ] **Behavioral testing** — Validate director orchestration and subagent compliance under pressure scenarios (e.g., false completion, partial drafts, convergence stalls).
- [ ] **Multilingual reports** — Reports are currently English-only. Add language detection so the report output matches the user's query language. Initial implementation searches in English only; which language to search in — and whether to search in both languages — needs validation through testing and user feedback.
- [ ] **Research clarification step** — Before starting research, the director could ask the user clarifying questions (e.g., scope, preferred angle, language when ambiguous). Currently the director proceeds directly from query to outline.

## License

MIT
