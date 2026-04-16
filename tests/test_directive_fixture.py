"""Fixture tests documenting the expected research_directive object shape.

The research_directive object's shape is documented in:
- skills/deep-research/SKILL.md (§2 Workspace Initialization, step 6)
- skills/deep-research/references/clarification.md (directive schema)

This file encodes the same shape in runnable form so schema assumptions made
by downstream code (or future director implementations) can be pinned.

This test does NOT parse the markdown documents — it cannot automatically
detect drift if SKILL.md changes the schema. When SKILL.md's schema changes,
update this file in the same commit.
"""

import json


REQUIRED_DIRECTIVE_FIELDS = {
    "research_question",
    "restated",
    "language",
    "status",
    "approved_at",
}

OPTIONAL_DIRECTIVE_FIELDS = {
    "scope_in",
    "scope_out",
    "timeframe",
    "geography",
    "audience",
}

VALID_STATUSES = {"draft", "approved"}


def make_draft_directive():
    """Expected shape of the research_directive at workspace init (draft)."""
    return {
        "research_question": "How do sovereign wealth funds allocate capital?",
        "restated": "Analyze capital allocation strategies across major sovereign wealth funds.",
        "language": "English",
        "status": "draft",
        "approved_at": None,
    }


def make_approved_directive():
    """Expected shape after user approval."""
    return {
        "research_question": "How do sovereign wealth funds allocate capital?",
        "restated": "Analyze capital allocation strategies across major sovereign wealth funds.",
        "language": "English",
        "status": "approved",
        "approved_at": "2026-04-16T12:00:00Z",
    }


def make_directive_with_constraints():
    """Expected shape when user has stated constraint preferences."""
    directive = make_approved_directive()
    directive["scope_in"] = "Public equity and fixed income allocations"
    directive["scope_out"] = "Private equity and real estate"
    directive["timeframe"] = "2020-present"
    directive["geography"] = "Norway, Singapore, UAE"
    directive["audience"] = "Policy analyst evaluating SWF governance models"
    return directive


def make_workflow_state(directive):
    """Minimal workflow_state.json with research_directive embedded."""
    return {
        "workflow_id": "sovereign-wealth-funds-20260416",
        "created_at": "2026-04-16T11:59:00Z",
        "convergence_script": "/abs/path/convergence_check.py",
        "known_unfillable_gaps": [],
        "research_directive": directive,
        "tasks": [],
    }


class TestDirectiveSchema:
    def test_draft_directive_has_required_fields(self):
        directive = make_draft_directive()
        assert set(directive.keys()) == REQUIRED_DIRECTIVE_FIELDS

    def test_approved_directive_has_required_fields(self):
        directive = make_approved_directive()
        assert set(directive.keys()) == REQUIRED_DIRECTIVE_FIELDS

    def test_constrained_directive_has_required_plus_optional(self):
        directive = make_directive_with_constraints()
        assert REQUIRED_DIRECTIVE_FIELDS.issubset(set(directive.keys()))
        optional_present = set(directive.keys()) - REQUIRED_DIRECTIVE_FIELDS
        assert optional_present == OPTIONAL_DIRECTIVE_FIELDS

    def test_draft_status_is_valid(self):
        directive = make_draft_directive()
        assert directive["status"] in VALID_STATUSES
        assert directive["status"] == "draft"
        assert directive["approved_at"] is None

    def test_approved_status_is_valid(self):
        directive = make_approved_directive()
        assert directive["status"] in VALID_STATUSES
        assert directive["status"] == "approved"
        assert directive["approved_at"] is not None
        assert isinstance(directive["approved_at"], str)

    def test_optional_fields_absent_in_draft(self):
        directive = make_draft_directive()
        for field in OPTIONAL_DIRECTIVE_FIELDS:
            assert field not in directive

    def test_optional_fields_are_strings_when_present(self):
        directive = make_directive_with_constraints()
        for field in OPTIONAL_DIRECTIVE_FIELDS:
            assert isinstance(directive[field], str)

    def test_workflow_state_roundtrips_as_json(self):
        ws = make_workflow_state(make_draft_directive())
        serialized = json.dumps(ws)
        parsed = json.loads(serialized)
        assert parsed["research_directive"]["status"] == "draft"
        assert parsed["tasks"] == []

    def test_tasks_empty_at_init(self):
        """Invariant: workflow_state.tasks is empty until directive is approved."""
        ws = make_workflow_state(make_draft_directive())
        assert ws["tasks"] == []

    def test_workflow_state_has_no_brief_key(self):
        """The old brief object must not be present."""
        ws = make_workflow_state(make_draft_directive())
        assert "brief" not in ws

    def test_workflow_state_has_no_top_level_research_question(self):
        """research_question lives inside research_directive, not at top level."""
        ws = make_workflow_state(make_draft_directive())
        assert "research_question" not in ws
        assert "research_question" in ws["research_directive"]

    def test_restated_is_string(self):
        directive = make_draft_directive()
        assert isinstance(directive["restated"], str)
        assert len(directive["restated"]) > 0

    def test_language_is_string(self):
        directive = make_draft_directive()
        assert isinstance(directive["language"], str)
        assert len(directive["language"]) > 0
