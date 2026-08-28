"""
test_coordlib.py - the shared core: vocabulary, tokenizer, table blocks, and the two
structural invariants (import direction, and the shipped templates parsing cleanly).

Every test here fails against the pre-coordlib code, either because the behaviour was wrong
or because the API did not exist.
"""

import ast
from pathlib import Path

import pytest

import coordlib
from coordlib import md_table, schema

TOOLS_DIR = Path(__file__).resolve().parent.parent.parent
ASSETS_COORDINATION = TOOLS_DIR.parent


# ======================================================================================
# Vocabulary: None means "unrecognised", never "no"
# ======================================================================================


@pytest.mark.parametrize("value", ["open", "OPEN", " open ", "**open**", "`open`"])
def test_open_statuses_classify_as_open_regardless_of_decoration(value):
    assert schema.classify_item_status(value) == "open"


@pytest.mark.parametrize("value", ["done", "resolved", "closed"])
def test_closed_statuses_classify_as_closed(value):
    assert schema.classify_item_status(value) == "closed"


@pytest.mark.parametrize("value", ["открыт", "в работе", "решён", "erledigt", "abierto"])
def test_non_english_status_is_unrecognised_not_closed(value):
    """The core of issue #6.

    The old rule was `"open" in status`, so a Russian `открыт` returned False -- indis-
    tinguishable from a genuinely closed item, and the operator saw "Open Questions: 0"
    with no error. None forces callers to handle it as a third case.
    """
    assert schema.classify_item_status(value) is None


@pytest.mark.parametrize("value", ["reopened", "not open", "open-ended"])
def test_substring_lookalikes_are_not_classified_as_open(value):
    """The old substring test matched all three of these as open."""
    assert schema.classify_item_status(value) != "open"


def test_in_progress_is_not_a_documented_status():
    """`in_progress` appeared in parser.py:226 and nowhere in any template.

    components.py accepted `in progress` (space) while parser.py accepted `in_progress`
    (underscore), so one rendered TAKEN while the other filed it as closed.
    """
    assert schema.classify_item_status("in_progress") is None
    assert schema.classify_item_status("in progress") is None


def test_role_status_accepts_documented_words_and_ignores_the_date():
    assert schema.classify_role_status("active (2026-08-27)") == "active"
    assert schema.classify_role_status("**active** (2026-08-27)") == "active"
    for value in schema.BOARD_STATUSES:
        assert schema.classify_role_status(value) == value


def test_non_english_role_status_is_unrecognised():
    assert schema.classify_role_status("активен (2026-08-27)") is None


def test_question_type_unrecognised_is_not_silently_non_blocking():
    """The old rule labelled everything unrecognised as non-blocking.

    An urgent question phrased any other way silently lost its urgency, which is why the
    red "N blocking" highlight never fired.
    """
    assert schema.classify_question_type("blocking") == "blocking"
    assert schema.classify_question_type("non-blocking") == "non-blocking"
    assert schema.classify_question_type("блокирующий") is None
    assert schema.classify_question_type("urgent") is None


# ======================================================================================
# Placeholders
# ======================================================================================


@pytest.mark.parametrize("value", ["<ID>", r"\<ID\>", r"\<PROJECT NAME\>", "YYYY-MM-DD", "ISO-date", ""])
def test_placeholders_are_recognised_including_backslash_escaped(value):
    """`\\<ID\\>` is the one that mattered.

    BOARD.md ships `| \\<ID\\> | active (YYYY-MM-DD) | ... |`. The old guard was
    `startswith("<")`, which the leading backslash defeats, so the template row rendered as
    a live role and was counted active in the KPI bar.
    """
    assert schema.is_placeholder_text(value) is True


@pytest.mark.parametrize("value", ["ORCH", "a-model", "frontend"])
def test_real_role_names_are_not_placeholders(value):
    assert schema.is_placeholder_text(value) is False


# ======================================================================================
# Column resolution: exact, never substring
# ======================================================================================


def test_documented_header_spellings_resolve():
    assert schema.resolve_column("Status (date)") == "status"
    assert schema.resolve_column("Status") == "status"
    assert schema.resolve_column("One-line summary") == "summary"
    assert schema.resolve_column("#") == "id"
    assert schema.resolve_column("Owner's answer") == "answer"


def test_empty_header_cell_resolves_to_nothing():
    """`"" in anything` is True, so the old bidirectional substring match made an empty
    header cell match every column and silently rewrite the wrong one."""
    assert schema.resolve_column("") is None
    assert schema.resolve_column("   ") is None


def test_non_english_header_resolves_to_nothing_rather_than_guessing():
    assert schema.resolve_column("Статус") is None
    assert schema.resolve_column("Роль") is None


def test_resolve_headers_keeps_first_occurrence_of_a_duplicate():
    resolved = schema.resolve_headers(["Role", "Status", "Status"])
    assert resolved["status"] == 1


def test_signature_matching_identifies_a_questions_table():
    questions = schema.resolve_headers(["#", "Question", "Owner's answer", "Type", "Status"])
    assert schema.matches_signature(questions, schema.QUESTIONS_TABLE_SIGNATURE)

    measurements = schema.resolve_headers(["Sample", "Value", "Unit"])
    assert not schema.matches_signature(measurements, schema.QUESTIONS_TABLE_SIGNATURE)


# ======================================================================================
# Tokenizer
# ======================================================================================


def test_split_row_preserves_escaped_pipes_and_code_spans():
    assert md_table.split_table_row(r"| a \| b | c |") == [r"a \| b", "c"]
    assert md_table.split_table_row("| `x | y` | z |") == ["`x | y`", "z"]


def test_split_row_does_not_eat_cells_from_doubled_borders():
    """build_index.py used `line.strip("|")`, which removes every leading/trailing pipe."""
    assert md_table.split_table_row("|| a | b ||") == ["", "a", "b", ""]


def test_escape_pipe_is_idempotent():
    assert md_table.escape_pipe("a|b") == r"a\|b"
    assert md_table.escape_pipe(r"a\|b") == r"a\|b"


def test_format_row_flattens_newlines_so_a_value_cannot_shatter_the_table():
    assert "\n" not in md_table.format_row(["a\nb", "c"]).rstrip("\n")


# ======================================================================================
# Table blocks
# ======================================================================================


SAMPLE_TWO_TABLES = """# Questions

## Batch 1

| # | Question | Owner's answer | Type | Status |
|---|---|---|---|---|
| Q-1 | First? | yes | blocking | resolved |

Some prose in between.

## Measurements attached to Q-1

| Sample | Value | Unit |
|---|---|---|
| A | 1.5 | THz |
""".splitlines(keepends=True)


def test_iter_table_blocks_finds_both_tables_with_their_headings():
    blocks = list(md_table.iter_table_blocks(SAMPLE_TWO_TABLES))
    assert len(blocks) == 2
    assert blocks[0].preceding_heading == "## Batch 1"
    assert blocks[1].preceding_heading == "## Measurements attached to Q-1"


def test_only_the_questions_table_matches_the_questions_signature():
    """This is the reporter's corruption case, at the level of table identification."""
    blocks = list(md_table.iter_table_blocks(SAMPLE_TWO_TABLES))
    matching = [
        b for b in blocks
        if schema.matches_signature(schema.resolve_headers(b.headers), schema.QUESTIONS_TABLE_SIGNATURE)
    ]
    assert len(matching) == 1
    assert matching[0].preceding_heading == "## Batch 1"


def test_table_blocks_skip_fenced_code():
    """The templates document their format inside a ``` fence.

    Without fence tracking every reader treats the *example* as real data -- which is what
    parse_handoffs does today with the HANDOFFS.md format block.
    """
    lines = """# Doc

```
| # | Question | Status |
|---|---|---|
| Q-1 | example | open |
```

| # | Question | Status |
|---|---|---|
| Q-2 | real | open |
""".splitlines(keepends=True)
    blocks = list(md_table.iter_table_blocks(lines))
    assert len(blocks) == 1
    assert blocks[0].row_indices  # the real table, not the fenced example


def test_separator_row_is_not_counted_as_data():
    blocks = list(md_table.iter_table_blocks(SAMPLE_TWO_TABLES))
    first = blocks[0]
    assert first.separator_index == first.header_index + 1
    assert first.row_indices == [first.header_index + 2]


# ======================================================================================
# Control-character scanning
# ======================================================================================


def test_scan_detects_the_handoffs_corruption_signature():
    """`\\a` in `\\assets` became 0x07 and `\\r` in `\\references` became a bare CR.

    The CR is the damaging one: it splits the line for every reader, so every later line
    number is off by one -- and those line numbers are the mutator's write target.
    """
    text = "- What: Create \x07ssets/x and update \references/y\n"
    findings = list(md_table.scan_control_characters(text))
    assert any("0x07" in detail for _, detail in findings)
    assert any("carriage return" in detail for _, detail in findings)


def test_scan_is_quiet_on_clean_text():
    assert list(md_table.scan_control_characters("| a | b |\n- **Status:** open\n")) == []


# ======================================================================================
# Structural invariants
# ======================================================================================


def _module_paths_outside_dashboard():
    for path in TOOLS_DIR.glob("*.py"):
        yield path
    for path in (TOOLS_DIR / "coordlib").glob("*.py"):
        yield path


def test_core_tools_do_not_import_dashboard_or_streamlit():
    """The core/optional boundary, enforced rather than documented.

    README.md promises the core scaffold is stdlib-only. Nothing outside dashboard/ may
    import streamlit, and coordlib may not import the optional package it serves.
    """
    offenders = []
    for path in _module_paths_outside_dashboard():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                root = name.split(".")[0]
                if root in {"streamlit", "dashboard"}:
                    offenders.append(f"{path.name}:{node.lineno} imports {name}")
    assert offenders == [], "core tools must stay stdlib-only: " + "; ".join(offenders)


def _shipped_markdown_files():
    return sorted(ASSETS_COORDINATION.glob("**/*.md"))


def test_shipped_templates_have_no_control_bytes():
    """The scaffold must not ship the corruption it teaches people to avoid."""
    problems = []
    for path in _shipped_markdown_files():
        # newline="" so line endings reach the scanner untranslated; Path.read_text only
        # grew a newline argument in 3.13, and this must run on the project's 3.9 floor.
        with open(path, "r", encoding="utf-8", newline="") as handle:
            text = handle.read()
        for line_no, detail in md_table.scan_control_characters(text):
            problems.append(f"{path.name}:{line_no} {detail}")
    assert problems == [], "; ".join(problems)


def test_shipped_templates_have_consistent_line_endings():
    problems = []
    for path in _shipped_markdown_files():
        raw = path.read_bytes()
        crlf = raw.count(b"\r\n")
        lf = raw.count(b"\n") - crlf
        if crlf and lf:
            problems.append(f"{path.name}: {crlf} CRLF and {lf} LF lines")
    assert problems == [], "; ".join(problems)
