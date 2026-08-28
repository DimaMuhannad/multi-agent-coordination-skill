"""
mutator.py - line-preserving, non-destructive edits to markdown tables and handoff entries.

Structured as plan/apply. Every operation computes a MutationPlan -- the exact new file
contents -- without touching disk; apply_plan writes it. Two reasons:

  - the diff a human confirms is *guaranteed* to be what gets written, because it is
    rendered from the same plan that gets applied;
  - the interesting logic becomes testable without temporary files.

The legacy names (mutate_table_cell, append_question, ...) survive as thin wrappers
returning (bool, str), so existing callers and tests keep working.

WHAT WENT WRONG BEFORE, and what prevents it now:

  append_question scanned for "the last pipe-prefixed line in the whole file", with no
  notion of which table it belonged to. In the reporter's QUESTIONS.md the last table held
  physical measurements attached to a decision; a new question was inserted into it and
  corrupted it. Tables are now selected by header signature, and a file with no qualifying
  table is refused rather than guessed at.

  Column matching was a bidirectional substring test (`k == x or x in k or k in x`). An
  empty header cell made `"" in x` unconditionally true, so it matched every column and
  silently rewrote the wrong one. Matching is now exact against coordlib's alias table.

  mutate_handoff_status rebuilt the whole status line from scratch, destroying anything
  after the keyword: `- **Status:** done (2026-08-27, see ACTIVITY)` became
  `- **Status:** done`. The edit is now surgical on the status token's span.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import difflib
import sys
from typing import List, Optional, Sequence, Tuple

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from coordlib import diagnostics as diag  # noqa: E402
from coordlib import md_table, schema  # noqa: E402
from coordlib.md_table import escape_pipe, format_row  # noqa: E402,F401

try:
    from .parser import HEADER_RE, SEP_RE, STATUS_RE, split_table_row  # noqa: F401
except (ImportError, ValueError):
    from parser import HEADER_RE, SEP_RE, STATUS_RE, split_table_row  # noqa: F401


def format_table_row(cells: List[str], line_ending: str = "\n") -> str:
    """Kept as a module-level name: callers and tests import it directly."""
    return format_row([c.strip() for c in cells], line_ending=line_ending)


# ======================================================================================
# Plan
# ======================================================================================


@dataclass
class MutationPlan:
    """A computed but unapplied edit.

    `target_description` is written for a human deciding whether to allow the write -- it
    names the file, the table (by its heading) and the line. That is the mitigation for the
    corruption above: the operator can see *which* table was chosen before anything happens.
    """

    ok: bool
    message: str
    path: Optional[Path] = None
    original_lines: List[str] = field(default_factory=list)
    new_lines: List[str] = field(default_factory=list)
    target_description: str = ""
    diagnostics: List[object] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.ok and self.original_lines != self.new_lines

    def diff(self) -> str:
        """Unified diff of exactly what apply_plan would write."""
        if not self.ok:
            return ""
        name = self.path.name if self.path else "file"
        return "".join(
            difflib.unified_diff(
                self.original_lines, self.new_lines,
                fromfile=f"a/{name}", tofile=f"b/{name}", n=3,
            )
        )


def apply_plan(plan: MutationPlan) -> Tuple[bool, str]:
    """Write a plan to disk. A refused or no-op plan writes nothing."""
    if not plan.ok:
        return False, plan.message
    if not plan.changed:
        return True, f"No change needed: {plan.message}"
    with open(plan.path, "w", encoding="utf-8", newline="") as handle:
        handle.writelines(plan.new_lines)
    return True, plan.message


def _read(path: Path) -> Optional[List[str]]:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.readlines()


def _qualifying_blocks(lines: Sequence[str], signature):
    """Table blocks whose headers cover `signature`, paired with their resolved header map."""
    found = []
    for block in md_table.iter_table_blocks(lines):
        resolved = schema.resolve_headers(block.headers)
        if schema.matches_signature(resolved, signature):
            found.append((block, resolved))
    return found


def _describe(path: Path, block, line_number: int, what: str) -> str:
    where = block.preceding_heading or "(no heading)"
    return f"{path.name} -> table under {where} -> {what} line {line_number}"


# ======================================================================================
# Table cell edit
# ======================================================================================


def plan_table_cell_edit(
    file_path: Path,
    key_col: str,
    key_val: str,
    target_col: str,
    new_val: str,
) -> MutationPlan:
    """Plan an edit to one cell, located by canonical column rather than by guesswork."""
    path = Path(file_path)
    lines = _read(path)
    if lines is None:
        return MutationPlan(False, f"File not found: {path}")

    key_key = schema.resolve_column(key_col)
    target_key = schema.resolve_column(target_col)
    if key_key is None or target_key is None:
        unknown = key_col if key_key is None else target_col
        return MutationPlan(
            False,
            f"'{unknown}' is not a recognised column name. Recognised columns are the ones "
            "the templates document (#/ID, Role, Status, Type, Question, Owner's answer, "
            "One-line summary).",
            path=path,
        )

    key_wanted = schema.normalise(key_val)
    seen_headers: List[str] = []

    for block in md_table.iter_table_blocks(lines):
        resolved = schema.resolve_headers(block.headers)
        seen_headers.append(" | ".join(block.headers))
        if key_key not in resolved or target_key not in resolved:
            continue

        key_index = resolved[key_key]
        target_index = resolved[target_key]
        for row_index in block.row_indices:
            original = lines[row_index]
            cells = split_table_row(original.strip())
            if len(cells) <= max(key_index, target_index):
                continue
            if schema.normalise(cells[key_index]) != key_wanted:
                continue

            line_ending = "\r\n" if original.endswith("\r\n") else "\n"
            cells[target_index] = new_val.strip()
            new_lines = list(lines)
            new_lines[row_index] = format_row(cells, line_ending=line_ending)
            return MutationPlan(
                True,
                f"Updated row '{key_val}' column '{target_col}' in {path.name}",
                path=path,
                original_lines=lines,
                new_lines=new_lines,
                target_description=_describe(path, block, row_index + 1, "row at"),
            )

    detail = f"; headers seen: {' / '.join(seen_headers)}" if seen_headers else ""
    return MutationPlan(
        False,
        f"Row with {key_col}='{key_val}' and column '{target_col}' not found in {path.name}{detail}",
        path=path,
    )


def mutate_table_cell(file_path: Path, key_col: str, key_val: str, target_col: str, new_val: str):
    return apply_plan(plan_table_cell_edit(file_path, key_col, key_val, target_col, new_val))


# ======================================================================================
# Handoff status
# ======================================================================================


def plan_handoff_status(file_path: Path, date: str, title: str, new_status: str) -> MutationPlan:
    """Plan a status change that replaces ONLY the status token.

    The previous implementation rebuilt the line as
    f"{indent}- **Status:** {new_status}", discarding whatever followed -- a date, a
    cross-reference, a note. Splicing the matched span keeps all of it.
    """
    path = Path(file_path)
    lines = _read(path)
    if lines is None:
        return MutationPlan(False, f"File not found: {path}")

    date_wanted = date.strip().lower()
    title_wanted = title.strip().lower()
    diagnostics: List[object] = []

    entry_start: Optional[int] = None
    entry_title = ""
    in_fence = False
    fence_marker = ""

    for idx, raw in enumerate(lines):
        stripped = raw.strip()
        if in_fence:
            if stripped.startswith(fence_marker):
                in_fence = False
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = True
            fence_marker = stripped[:3]
            continue

        line = raw.rstrip("\r\n")
        match = HEADER_RE.match(line)
        if match:
            found_date = match.group(1).strip().lower()
            found_title = (match.group(4) or "").strip().lower()
            if found_date == date_wanted and (
                not title_wanted or title_wanted in found_title or found_title in title_wanted
            ):
                entry_start = idx
                entry_title = found_title
            else:
                entry_start = None
            continue

        if entry_start is None:
            continue

        status_match = STATUS_RE.search(line)
        if not status_match:
            continue

        # Replace exactly the keyword's span. Everything after it -- including the
        # whitespace the regex happened to capture, and any trailing note -- is carried
        # over untouched by line[end:].
        keyword = status_match.group(1)
        start = status_match.start(1)
        end = start + len(keyword.rstrip())

        if schema.classify_item_status(keyword) is None:
            diag.record(
                diagnostics, diag.MALFORMED_STATUS_LINE, path, idx + 1,
                "existing status is outside the documented vocabulary; replacing the "
                "keyword and leaving the rest of the line intact",
                schema.strip_decoration(keyword),
            )

        new_lines = list(lines)
        new_lines[idx] = line[:start] + new_status.strip().lower() + line[end:] + (
            "\r\n" if raw.endswith("\r\n") else ("\n" if raw.endswith("\n") else "")
        )
        return MutationPlan(
            True,
            f"Updated handoff '{title}' status to '{new_status}' in {path.name}",
            path=path,
            original_lines=lines,
            new_lines=new_lines,
            target_description=f"{path.name} -> entry [{date}] {entry_title} -> status line {idx + 1}",
            diagnostics=diagnostics,
        )

    return MutationPlan(
        False,
        f"Handoff entry '{date}' - '{title}' status line not found in {path.name}",
        path=path,
    )


def mutate_handoff_status(file_path: Path, date: str, title: str, new_status: str):
    return apply_plan(plan_handoff_status(file_path, date, title, new_status))


# ======================================================================================
# Append a question
# ======================================================================================

_CANONICAL_QUESTION_HEADER = ["#", "Question", "Owner's answer", "Type", "Status"]


def plan_append_question(
    file_path: Path,
    question: str,
    q_type: str = "blocking",
    status: str = "open",
    qid: Optional[str] = None,
    answer: str = "—",
    table_heading: Optional[str] = None,
) -> MutationPlan:
    """Plan a new question row, inserted into a table that is actually a questions table.

    Refuses rather than guessing when the file has tables but none of them qualify. That is
    the reporter's case: their last table held measurements, and the old code appended into
    it.
    """
    path = Path(file_path)
    lines = _read(path)
    if lines is None:
        return MutationPlan(False, f"File not found: {path}")

    all_blocks = list(md_table.iter_table_blocks(lines))
    qualifying = _qualifying_blocks(lines, schema.QUESTIONS_TABLE_SIGNATURE)

    if not qualifying:
        if all_blocks:
            seen = " / ".join(" | ".join(b.headers) for b in all_blocks)
            return MutationPlan(
                False,
                f"{path.name} contains {len(all_blocks)} table(s) but none match the "
                "canonical questions schema (#, Question, Status), so there is nowhere safe "
                f"to add a row. Headers found: {seen}",
                path=path,
            )
        # Genuinely empty template: create the canonical table.
        line_ending = md_table.detect_line_ending(lines)
        new_lines = list(lines)
        if new_lines and not new_lines[-1].endswith(("\n", "\r\n")):
            new_lines[-1] = new_lines[-1] + line_ending
        assigned = qid or "Q-1"
        new_lines.append(line_ending)
        new_lines.append(format_row(_CANONICAL_QUESTION_HEADER, line_ending))
        new_lines.append("|" + "---|" * len(_CANONICAL_QUESTION_HEADER) + line_ending)
        new_lines.append(
            format_row([assigned, question, answer, q_type, status], line_ending)
        )
        return MutationPlan(
            True,
            f"Created a questions table and appended {assigned} in {path.name}",
            path=path,
            original_lines=lines,
            new_lines=new_lines,
            target_description=f"{path.name} -> new questions table at end of file",
        )

    if table_heading:
        wanted = table_heading.strip().lower()
        chosen = next(
            ((b, r) for b, r in qualifying if b.preceding_heading.strip().lower() == wanted),
            None,
        )
        if chosen is None:
            headings = " / ".join(b.preceding_heading or "(no heading)" for b, _ in qualifying)
            return MutationPlan(
                False,
                f"No questions table under heading '{table_heading}' in {path.name}. "
                f"Qualifying tables: {headings}",
                path=path,
            )
    else:
        # Several qualifying tables: the last one, preserving the "newest batch" intent.
        chosen = qualifying[-1]

    block, resolved = chosen

    # Scan IDs across qualifying tables only, so an unrelated table cannot influence
    # numbering, and the header row cannot be mistaken for data.
    max_id = 0
    for candidate_block, candidate_resolved in qualifying:
        id_index = candidate_resolved["id"]
        for row_index in candidate_block.row_indices:
            cells = split_table_row(lines[row_index].strip())
            if id_index >= len(cells):
                continue
            found = schema.strip_decoration(cells[id_index])
            if found.upper().startswith("Q-") and found[2:].isdigit():
                max_id = max(max_id, int(found[2:]))
    assigned = qid or f"Q-{max_id + 1}"

    # Build the row FROM THE DESTINATION HEADER, not from a hardcoded positional list, so a
    # table with reordered or extra columns still receives a well-formed row.
    values = {
        "id": assigned,
        "question": question,
        "answer": answer,
        "type": q_type,
        "status": status,
    }
    cells = []
    for header in block.headers:
        key = schema.resolve_column(header)
        if key is None:
            return MutationPlan(
                False,
                f"Cannot build a row for {path.name}: column '{header}' is not recognised, "
                "so the value that belongs in it is unknown.",
                path=path,
            )
        cells.append(values.get(key, "—"))

    insert_at = block.insert_after_index + 1
    new_lines = list(lines)
    new_lines.insert(insert_at, format_row(cells, block.line_ending))

    return MutationPlan(
        True,
        f"Appended question {assigned} in {path.name}",
        path=path,
        original_lines=lines,
        new_lines=new_lines,
        target_description=_describe(path, block, insert_at + 1, "insert at"),
    )


def append_question(
    file_path: Path,
    question: str,
    q_type: str = "blocking",
    status: str = "open",
    qid: Optional[str] = None,
    answer: str = "—",
):
    return apply_plan(plan_append_question(file_path, question, q_type, status, qid, answer))


# ======================================================================================
# Append a board row
# ======================================================================================


def plan_append_board_row(
    file_path: Path,
    role: str,
    status: str = "active",
    summary: str = "",
    date: Optional[str] = None,
) -> MutationPlan:
    """Plan a new role row INSIDE the board table.

    dashboard.py used to append this at end-of-file, bypassing the mutator. BOARD.md ends
    with a prose paragraph after the table, so the row landed after the prose -- where the
    parser's header tracking resets and the row is dropped. The write and the commit both
    succeeded and the role never appeared.
    """
    path = Path(file_path)
    lines = _read(path)
    if lines is None:
        return MutationPlan(False, f"File not found: {path}")

    qualifying = _qualifying_blocks(lines, schema.BOARD_TABLE_SIGNATURE)
    if not qualifying:
        return MutationPlan(
            False,
            f"{path.name} has no table with Role and Status columns, so there is nowhere "
            "safe to add a role.",
            path=path,
        )

    block, _resolved = qualifying[-1]
    stamp = date or datetime.now().strftime("%Y-%m-%d")
    values = {
        "role": role.strip(),
        "status": f"{status.strip()} ({stamp})",
        "summary": summary.strip(),
    }
    cells = []
    for header in block.headers:
        key = schema.resolve_column(header)
        if key is None:
            return MutationPlan(
                False,
                f"Cannot build a row for {path.name}: column '{header}' is not recognised.",
                path=path,
            )
        cells.append(values.get(key, "—"))

    insert_at = block.insert_after_index + 1
    new_lines = list(lines)
    new_lines.insert(insert_at, format_row(cells, block.line_ending))

    return MutationPlan(
        True,
        f"Added role '{role}' to {path.name}",
        path=path,
        original_lines=lines,
        new_lines=new_lines,
        target_description=_describe(path, block, insert_at + 1, "insert at"),
    )


def append_board_row(file_path: Path, role: str, status: str = "active", summary: str = ""):
    return apply_plan(plan_append_board_row(file_path, role, status, summary))


# ======================================================================================
# Append a handoff
# ======================================================================================


def plan_append_handoff(
    file_path: Path,
    from_role: str,
    to_role: str,
    title: str,
    what: str,
    context: str = "",
    done_when: str = "",
    status: str = "open",
    date: Optional[str] = None,
) -> MutationPlan:
    """Plan a new handoff block appended at end of file.

    Handoff entries are chronological blocks rather than table rows, so end-of-file is the
    correct position. Newlines in the free-text fields are flattened: a multi-line value
    written verbatim would break the `- What:` / `- Context:` block structure the parser and
    the mandated `- **Status:**` line depend on.
    """
    path = Path(file_path)
    lines = _read(path)
    if lines is None:
        return MutationPlan(False, f"File not found: {path}")

    line_ending = md_table.detect_line_ending(lines)
    stamp = date or datetime.now().strftime("%Y-%m-%d")

    def one_line(text: str) -> str:
        return " ".join((text or "").split())

    block_lines = [
        line_ending,
        f"## [{stamp}] FROM {from_role.strip()} TO {to_role.strip()} — {one_line(title)}{line_ending}",
        f"- What: {one_line(what)}{line_ending}",
        f"- Context: {one_line(context)}{line_ending}",
        f"- Done when: {one_line(done_when)}{line_ending}",
        f"- **Status:** {status.strip().lower()}{line_ending}",
    ]

    new_lines = list(lines)
    if new_lines and not new_lines[-1].endswith(("\n", "\r\n")):
        new_lines[-1] = new_lines[-1] + line_ending
    new_lines.extend(block_lines)

    return MutationPlan(
        True,
        f"Appended handoff '{title}' to {path.name}",
        path=path,
        original_lines=lines,
        new_lines=new_lines,
        target_description=f"{path.name} -> new entry appended at end of file",
    )


def append_handoff(
    file_path: Path,
    from_role: str,
    to_role: str,
    title: str,
    what: str,
    context: str = "",
    done_when: str = "",
    status: str = "open",
    date: Optional[str] = None,
):
    return apply_plan(
        plan_append_handoff(
            file_path, from_role, to_role, title, what, context, done_when, status, date
        )
    )
