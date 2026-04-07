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
6. **Validator** checks the final report for quality (length, citations, structure)

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
- Python 3 (for the validation script — stdlib only, no dependencies)

## Roadmap

- [ ] **Assembler subagent** — Introduction and Conclusion are currently written by the director without evidence grounding or editorial review. A dedicated assembler subagent would ensure these sections receive the same quality treatment as body chapters.
- [ ] **Behavioral testing** — Validate director orchestration and subagent compliance under pressure scenarios (e.g., false completion, partial drafts, convergence stalls).
- [ ] **Multilingual reports** — Reports are currently English-only. Add language selection so the research output matches the user's preferred language.
- [ ] **Verify `argument-hint` field** — Confirm the plugin loader recognizes this frontmatter field, or remove it.

## License

MIT
