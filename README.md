# Deep Research Plugin for Claude Code

A Claude Code plugin that conducts in-depth web research and produces structured reports with inline citations. Ported from the [deer-flow](https://github.com/anthropics/deer-flow) deep-research system.

## Installation

**From marketplace (coming soon)**

**For local development:**
```
claude --plugin-dir ./deep-research-skill
```

## Usage

```
/deep-research <your research topic>
```

Or just ask a research question — Claude will invoke the skill automatically when it detects a question requiring in-depth research.

## How It Works

The skill uses a director/subagent architecture:

1. **Director** (SKILL.md) analyzes your question and creates a research outline
2. **Evaluator** assesses research completeness and identifies gaps
3. **Gatherer** searches the web, fetches pages, and stores sources
4. **Drafter** writes report chapters using the CECI analytical pattern
5. **Editor** enriches prose with specific data and adds inline citations
6. **Synthesizer** reads all chapters; writes Introduction and Conclusion; checks for cross-chapter contradictions, coverage gaps, research-question alignment, and dangling forward references

The research loop (evaluate → gather → evaluate) runs until evidence is sufficient or the iteration cap (15) is reached. Writing parallelizes up to 3 chapters at once.

## Output

Research artifacts are stored in `.deep-research/<topic-slug>/`:

```
.deep-research/
└── sovereign-wealth-funds/
    ├── workspace/
    │   ├── outline.md              # Research outline
    │   ├── source_index.json        # Source metadata
    │   ├── workflow_state.json     # Execution state
    │   └── sources/                # Raw fetched content
    └── outputs/
        └── report.md              # Final report
```

The `.deep-research/` directory is automatically gitignored.

## Requirements

- Claude Code with Agent, WebSearch, and WebFetch tools available

## Roadmap

- [x] **Synthesizer subagent** — Introduction and Conclusion are now written by the synthesizer subagent after all chapter editing completes, with full evidence context. The synthesizer also checks for cross-chapter contradictions, coverage gaps, research-question alignment, and dangling forward references.
- [ ] **Behavioral testing** — Validate director orchestration and subagent compliance under pressure scenarios (e.g., false completion, partial drafts, convergence stalls).
- [ ] **Multilingual reports** — Reports are currently English-only. Add language detection so the report output matches the user's query language. Initial implementation searches in English only; which language to search in — and whether to search in both languages — needs validation through testing and user feedback.
- [ ] **Verify `argument-hint` field** — Confirm the plugin loader recognizes this frontmatter field, or remove it.
- [ ] **Research clarification step** — Before starting research, the director could ask the user clarifying questions (e.g., scope, preferred angle, language when ambiguous). Currently the director proceeds directly from query to outline.

## License

MIT
