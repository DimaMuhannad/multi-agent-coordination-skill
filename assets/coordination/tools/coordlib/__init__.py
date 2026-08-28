"""
coordlib - shared, stdlib-only core for the coordination tools.

Ships with the CORE scaffold. build_index.py and kpi_git.py depend on it; the optional
Streamlit dashboard depends on it too. The dependency runs one way only:

    coordlib  <--  build_index.py, kpi_git.py         (core, stdlib only)
    coordlib  <--  dashboard/parser.py, mutator.py    (optional add-on, still stdlib)
    coordlib  <--  dashboard/badges.py  <--  components.py, dashboard.py   (needs streamlit)

coordlib must never import from dashboard/, and nothing outside dashboard/ may import
streamlit. That is enforced by test_core_tools_do_not_import_dashboard_or_streamlit, not
merely documented -- a rule nobody checks is the failure mode references/rationale.md is
about.
"""

from .diagnostics import (
    CONTROL_CHARACTER,
    COLUMN_COUNT_MISMATCH,
    DUPLICATE_ID,
    Diagnostic,
    DiagnosticList,
    MALFORMED_STATUS_LINE,
    MISSING_STATUS,
    NO_HEADER_ROW,
    UNKNOWN_STATUS,
    UNKNOWN_TABLE_SCHEMA,
    UNKNOWN_TYPE,
    UNSAFE_TO_WRITE_CODES,
    record,
)
from .md_table import (
    SEP_RE,
    TableBlock,
    detect_line_ending,
    escape_pipe,
    format_row,
    is_separator_row,
    iter_table_blocks,
    scan_control_characters,
    split_table_row,
)
from .schema import (
    BOARD_STATUSES,
    BOARD_TABLE_SIGNATURE,
    HANDOFF_STATUSES,
    MISSING,
    QUESTION_STATUSES,
    QUESTION_TYPES,
    QUESTIONS_TABLE_SIGNATURE,
    classify_item_status,
    classify_question_type,
    classify_role_status,
    is_placeholder_text,
    matches_signature,
    normalise,
    resolve_column,
    resolve_headers,
    split_role_status_date,
    strip_decoration,
)
from .paths import find_coordination_dir, find_repo_root, is_within, worktrees_dir

__all__ = [
    # diagnostics
    "Diagnostic",
    "DiagnosticList",
    "record",
    "UNSAFE_TO_WRITE_CODES",
    "UNKNOWN_TABLE_SCHEMA",
    "NO_HEADER_ROW",
    "UNKNOWN_STATUS",
    "UNKNOWN_TYPE",
    "MISSING_STATUS",
    "MALFORMED_STATUS_LINE",
    "COLUMN_COUNT_MISMATCH",
    "CONTROL_CHARACTER",
    "DUPLICATE_ID",
    # md_table
    "SEP_RE",
    "TableBlock",
    "split_table_row",
    "escape_pipe",
    "format_row",
    "format_table_row",
    "is_separator_row",
    "detect_line_ending",
    "iter_table_blocks",
    "scan_control_characters",
    # schema
    "HANDOFF_STATUSES",
    "QUESTION_STATUSES",
    "QUESTION_TYPES",
    "BOARD_STATUSES",
    "MISSING",
    "normalise",
    "strip_decoration",
    "is_placeholder_text",
    "classify_item_status",
    "classify_role_status",
    "classify_question_type",
    "split_role_status_date",
    "resolve_column",
    "resolve_headers",
    "matches_signature",
    "QUESTIONS_TABLE_SIGNATURE",
    "BOARD_TABLE_SIGNATURE",
    # paths
    "find_repo_root",
    "find_coordination_dir",
    "worktrees_dir",
    "is_within",
]

#: Alias kept because dashboard/mutator.py exports a function of this name that callers and
#: tests import directly.
format_table_row = format_row
