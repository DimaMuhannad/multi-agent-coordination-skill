"""
Multi-Agent Coordination Interactive Dashboard Package.
Provides line-preserving markdown parsers, surgical table/block mutators, and a git isolation
service.

Deliberately does NOT re-export .components or .dashboard: both import streamlit at module
scope, so re-exporting them here would make `import dashboard.anything` require streamlit --
including the parser and mutator, which are pure stdlib. Import the UI explicitly instead:

    from dashboard.components import render_kpi_bar
"""

from .parser import (
    split_table_row,
    parse_board,
    parse_questions,
    parse_handoffs,
    parse_index,
    parse_worktrees
)
from .mutator import (
    escape_pipe,
    format_table_row,
    mutate_table_cell,
    mutate_handoff_status,
    append_question,
    append_handoff
)
from .git_service import GitService

__all__ = [
    "split_table_row",
    "parse_board",
    "parse_questions",
    "parse_handoffs",
    "parse_index",
    "parse_worktrees",
    "escape_pipe",
    "format_table_row",
    "mutate_table_cell",
    "mutate_handoff_status",
    "append_question",
    "append_handoff",
    "GitService"
]
