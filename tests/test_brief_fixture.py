"""Fixture tests documenting the expected brief-object shape.

The brief object's shape is *documented* in:
- skills/deep-research/SKILL.md (§2 First turn)
- skills/deep-research/references/clarification.md (Approval sequence)

This file encodes the same shape in runnable form so schema assumptions made
by downstream code (or future director implementations) can be pinned.

This test does NOT parse the markdown documents — it cannot automatically
detect drift if SKILL.md changes the schema. When SKILL.md's schema changes,
update this file in the same commit.
"""

import json


REQUIRED_BRIEF_FIELDS = {
    "status",
    "path",
    "approved_at",
    "revision_count",
    "revision_cap_overridden",
}

VALID_STATUSES = {"draft", "approved"}


def make_draft_brief():
    """Expected shape of the brief object at workspace init (draft)."""
    return {
        "status": "draft",
        "path": ".deep-research/test-slug/workspace/brief.md",
        "approved_at": None,
        "revision_count": 0,
        "revision_cap_overridden": False,
    }


def make_approved_brief():
    """Expected shape after user approval."""
    return {
        "status": "approved",
        "path": ".deep-research/test-slug/workspace/brief.md",
        "approved_at": "2026-04-13T12:00:00Z",
        "revision_count": 1,
        "revision_cap_overridden": False,
    }


def make_workflow_state(brief):
    """Minimal workflow_state.json with brief object embedded."""
    return {
        "workflow_id": "test-slug-20260413",
        "created_at": "2026-04-13T11:59:00Z",
        "research_question": "Test question",
        "language": "English",
        "convergence_script": "/abs/path/convergence_check.py",
        "known_unfillable_gaps": [],
        "brief": brief,
        "tasks": [],
    }


class TestBriefSchema:
    def test_draft_brief_has_required_fields(self):
        brief = make_draft_brief()
        assert set(brief.keys()) == REQUIRED_BRIEF_FIELDS

    def test_approved_brief_has_required_fields(self):
        brief = make_approved_brief()
        assert set(brief.keys()) == REQUIRED_BRIEF_FIELDS

    def test_draft_status_is_valid(self):
        brief = make_draft_brief()
        assert brief["status"] in VALID_STATUSES
        assert brief["status"] == "draft"
        assert brief["approved_at"] is None
        assert brief["revision_count"] == 0
        assert brief["revision_cap_overridden"] is False

    def test_approved_status_is_valid(self):
        brief = make_approved_brief()
        assert brief["status"] in VALID_STATUSES
        assert brief["status"] == "approved"
        assert brief["approved_at"] is not None
        assert isinstance(brief["approved_at"], str)

    def test_workflow_state_roundtrips_as_json(self):
        ws = make_workflow_state(make_draft_brief())
        serialized = json.dumps(ws)
        parsed = json.loads(serialized)
        assert parsed["brief"]["status"] == "draft"
        assert parsed["tasks"] == []

    def test_tasks_empty_at_init(self):
        """Invariant: workflow_state.tasks is empty until brief is approved."""
        ws = make_workflow_state(make_draft_brief())
        assert ws["tasks"] == []

    def test_revision_count_is_integer(self):
        brief = make_draft_brief()
        brief["revision_count"] = 5
        assert isinstance(brief["revision_count"], int)

    def test_cap_overridden_is_boolean(self):
        brief = make_draft_brief()
        brief["revision_cap_overridden"] = True
        assert isinstance(brief["revision_cap_overridden"], bool)
