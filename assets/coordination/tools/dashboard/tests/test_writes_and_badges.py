"""
test_writes_and_badges.py - the write gate and the badge vocabulary.

Both modules are stdlib-only by design, so this whole file runs without streamlit. That is
deliberate: the read-only default and the "refuse to write what you could not read" rule
are safety properties, and a safety property that can only be tested with an optional
heavyweight dependency installed will not be tested.
"""

import pytest

import badges
import writes
from coordlib import diagnostics as diag
from coordlib.diagnostics import Diagnostic


# ======================================================================================
# The write gate
# ======================================================================================


def test_writes_are_disabled_by_default():
    """docs/ru/CONCEPT.md §6.5: the interface is a read-only projection over git.

    That invariant now holds out of the box; writing is a deliberate per-session choice.
    """
    assert writes.writes_enabled({}) is False
    assert writes.gate(True, [], {}).allowed is False


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_writes_can_be_enabled_explicitly(value):
    assert writes.writes_enabled({writes.WRITES_ENV_VAR: value}) is True


@pytest.mark.parametrize("value", ["0", "false", "no", "", "  ", "maybe"])
def test_only_explicit_opt_in_enables_writes(value):
    assert writes.writes_enabled({writes.WRITES_ENV_VAR: value}) is False


def test_read_only_refusal_says_how_to_enable_writing():
    reason = writes.gate(True, [], {}).reason
    assert writes.WRITES_ENV_VAR in reason


ENABLED = {writes.WRITES_ENV_VAR: "1"}


def test_a_file_whose_schema_was_not_recognised_is_never_written():
    """The coupling between the two halves of issue #6.

    A tool that could not read a file correctly must not be trusted to write to it - and
    the old dashboard would happily write to a table it had just failed to parse.
    """
    unreadable = [Diagnostic(code=diag.UNKNOWN_TABLE_SCHEMA, path="QUESTIONS.md", line=3,
                             detail="not a questions table", observed="Sample | Value")]
    result = writes.gate(True, unreadable, ENABLED)
    assert result.allowed is False
    assert "schema was not recognised" in result.reason


def test_control_characters_also_block_writes():
    """A bare CR shifts every later line number - the mutator's write target."""
    damaged = [Diagnostic(code=diag.CONTROL_CHARACTER, path="HANDOFFS.md", line=42,
                          detail="bare carriage return")]
    assert writes.gate(True, damaged, ENABLED).allowed is False


def test_value_level_diagnostics_do_not_block_writes():
    """An unrecognised status word is a reporting problem, not a locating problem.

    The rows are still found reliably, so editing a *different* row stays safe. Blocking on
    this would make the file impossible to fix through the tool that reported it.
    """
    value_only = [Diagnostic(code=diag.UNKNOWN_STATUS, path="QUESTIONS.md", line=5,
                             detail="outside the vocabulary", observed="открыт")]
    assert writes.gate(True, value_only, ENABLED).allowed is True


def test_a_failed_plan_is_refused_even_when_writing_is_enabled():
    assert writes.gate(False, [], ENABLED).allowed is False


# ======================================================================================
# Committer roles come from the board
# ======================================================================================


def test_roles_are_read_from_the_board_not_hardcoded():
    """dashboard.py shipped the source project's roster baked into a template."""
    rows = [{"role": "ORCH"}, {"role": "qa"}, {"role": ""}, {"role": "ORCH"}]
    assert writes.roles_from_board(rows) == ["ORCH", "qa"]


def test_roles_from_an_empty_board_is_empty():
    assert writes.roles_from_board([]) == []
    assert writes.roles_from_board(None) == []


def test_revert_hint_is_offered_instead_of_an_undo_the_tool_does_not_have():
    assert writes.revert_hint("abc1234") == "git revert abc1234"
    assert writes.revert_hint(None) == ""


# ======================================================================================
# Badges agree with the parser
# ======================================================================================


def test_badges_carry_a_text_label_not_only_an_emoji():
    """Colour and emoji alone are not a usable encoding.

    The same glyph also meant different things across the two badge sets: ⚪ was CLOSED in
    one and Idle in the other, 🟢 was DONE in one and Active in the other.
    """
    for rendered in (
        badges.render_status_badge("open"),
        badges.render_status_badge("done"),
        badges.render_role_badge("active"),
        badges.render_type_badge("blocking"),
    ):
        assert any(char.isalpha() for char in rendered), rendered


def test_unrecognised_status_renders_as_unclassified_not_as_a_real_state():
    """components.py used to render `открыт` as a red OPEN badge beside a row that
    parser.py had already classified as closed."""
    rendered = badges.render_status_badge("открыт")
    assert "UNCLASSIFIED" in rendered
    assert "открыт" in rendered


def test_unrecognised_type_is_not_silently_non_blocking():
    rendered = badges.render_type_badge("блокирующий")
    assert "UNCLASSIFIED" in rendered
    assert "Non-blocking" not in rendered


def test_unrecognised_role_status_is_not_rendered_as_a_documented_one():
    assert "UNCLASSIFIED" in badges.render_role_badge("активен (2026-08-27)")


def test_question_partition_has_three_buckets():
    questions = [
        {"is_open": True}, {"is_open": True},
        {"is_open": False},
        {"is_open": None},
    ]
    opened, closed, unclassified = badges.partition_questions(questions)
    assert (len(opened), len(closed), len(unclassified)) == (2, 1, 1)


def test_role_partition_keeps_unclassified_separate_from_inactive():
    roles = [
        {"status_known": "active"},
        {"status_known": "idle"},
        {"status_known": None},
    ]
    active, other, unclassified = badges.partition_roles(roles)
    assert (len(active), len(other), len(unclassified)) == (1, 1, 1)
