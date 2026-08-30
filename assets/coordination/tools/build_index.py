#!/usr/bin/env python3
"""Build coordination/INDEX.md — an open/closed summary of QUESTIONS.md and HANDOFFS.md.

Why this exists: once QUESTIONS.md and HANDOFFS.md grow past a few hundred lines, nobody should
read them in full just to answer "what's still open?" — that's what grep is for, except grep
doesn't give you the shape of the backlog either. This script builds a short index: number/date/
status/line-to-jump-to, open items first. It is NOT a replacement for the journals — the actual
question text and decision text stay there; this is a filter on top.

This version assumes the CANONICAL format the bundled templates define — no drift tolerance:
  - QUESTIONS.md: one or more markdown tables, each with a `Status` column.
  - HANDOFFS.md: entries start with `## [ISO-date] ...` and end with a line reading exactly
    `- **Status:** open|taken|done` (see the HANDOFFS.md template for why this is mandatory).

If your project's journals drift from this format over time (they will, eventually — see
references/rationale.md for the THz project's experience with 8 different status-phrasing
variants), extend the regexes below rather than special-casing every historical entry; keep this
script simple and let format drift be a signal that the templates need reinforcing, not a reason
to make the parser permissive.

Usage (from repo root):
    python coordination/tools/build_index.py --out coordination/INDEX.md
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from coordlib import diagnostics as diag  # noqa: E402
from coordlib import md_table, schema  # noqa: E402
from coordlib.md_table import SEP_RE, split_table_row  # noqa: E402,F401

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
COORD = os.path.join(ROOT, "coordination")
if not os.path.isdir(COORD):
    # Authoring layout: this repository keeps the scaffold under assets/.
    COORD = os.path.join(ROOT, "assets", "coordination")

STATUS_RE = re.compile(r"\*\*Status:?\*\*:?\s*`?([^`\n().]*)", re.IGNORECASE)
HEADER_RE = re.compile(r"^##\s+\[([^\]]+)\]\s*(.*)$")

#: Hoisted out of the f-strings below: an f-string expression part may not contain a
#: backslash before Python 3.12, and the project's floor is 3.9.
EM_DASH = "\u2014"
ELLIPSIS = "\u2026"
WARNING_SIGN = "\u26a0"

#: Kept as a module-level name because callers and tests import it. Now one shared rule
#: instead of this file's own substring copy, which disagreed with the dashboard's two.
def is_open(status):
    return schema.classify_item_status(status) == "open"


#: Historic alias: this file's own tokenizer used line.strip("|"), which eats cells from
#: doubled borders and ignored backtick code spans. coordlib's is the careful one.
split_row = split_table_row


def parse_questions(path, diagnostics=None):
    """Read every canonical questions table in the file.

    A table qualifies by header signature (#, Question, Status), not by position, so an
    unrelated table -- measurements attached to a decision, say -- is reported rather than
    silently read as questions.
    """
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        lines = fh.readlines()

    rows = []
    for block in md_table.iter_table_blocks(lines):
        resolved = schema.resolve_headers(block.headers)
        if not schema.matches_signature(resolved, schema.QUESTIONS_TABLE_SIGNATURE):
            diag.record(
                diagnostics, diag.UNKNOWN_TABLE_SCHEMA, path, block.header_index + 1,
                f"not a questions table; skipped {len(block.row_indices)} row(s)",
                " | ".join(block.headers),
            )
            continue
        for row_index in block.row_indices:
            cells = split_table_row(lines[row_index].strip())

            def cell(key):
                index = resolved.get(key)
                return cells[index] if index is not None and index < len(cells) else ""

            rid = schema.strip_decoration(cell("id"))
            if schema.is_placeholder_text(rid):
                continue
            question = cell("question").replace("**", "")
            if len(question) > 110:
                question = question[:107] + ELLIPSIS
            raw_status = schema.strip_decoration(cell("status"))
            state = schema.classify_item_status(raw_status)
            if state is None:
                diag.record(
                    diagnostics, diag.UNKNOWN_STATUS, path, row_index + 1,
                    "status is outside the documented vocabulary "
                    f"({'|'.join(schema.QUESTION_STATUSES)})",
                    raw_status,
                )
            rows.append({
                "id": rid,
                "line": row_index + 1,
                "text": question,
                "status": raw_status,
                "state": state,
                "who": cell("role"),
            })
    return rows


def parse_handoffs(path, diagnostics=None):
    """Read handoff entries, skipping the fenced format example the template documents."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        lines = fh.readlines()

    entries = []
    cur = None
    in_fence = False
    fence_marker = ""

    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if in_fence:
            if stripped.startswith(fence_marker):
                in_fence = False
            continue
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = True
            fence_marker = stripped[:3]
            continue

        m = HEADER_RE.match(raw)
        if m:
            if cur:
                entries.append(cur)
            date = m.group(1).strip()
            cur = {
                "date": date,
                "text": m.group(2).strip(),
                "line": i,
                "status": None,
                "is_template": schema.is_placeholder_text(date) or "template" in date.lower(),
            }
            continue
        if cur is not None and cur["status"] is None:
            sm = STATUS_RE.search(raw)
            if sm:
                cur["status"] = schema.normalise(sm.group(1))
    if cur:
        entries.append(cur)

    for e in entries:
        if e["status"] is None:
            e["status"] = schema.MISSING
            if not e["is_template"]:
                diag.record(
                    diagnostics, diag.MISSING_STATUS, path, e["line"],
                    "entry has no `- **Status:**` line",
                )
        e["state"] = schema.classify_item_status(e["status"])
        if e["state"] is None and not e["is_template"]:
            diag.record(
                diagnostics, diag.UNKNOWN_STATUS, path, e["line"],
                "status is outside the documented vocabulary "
                f"({'|'.join(schema.HANDOFF_STATUSES)})",
                e["status"],
            )
    return entries


def render_table(rows, id_key, extra_key=None, extra_label=None):
    head = f"| # | Status | {extra_label + ' | ' if extra_label else ''}Line | Summary |\n"
    head += f"|---|---|{'---|' if extra_label else ''}---|---|\n"
    body = []
    for r in rows:
        extra = f"{r.get(extra_key, '')} | " if extra_label else ""
        body.append(f"| `{r[id_key]}` | {r['status'] or EM_DASH} | {extra}[line {r['line']}] | {r['text']} |")
    return head + "\n".join(body) + "\n"


def build_index_text(coord_dir=None, diagnostics=None):
    """Render INDEX.md as a string.

    Exposed as a function so the optional dashboard can call it instead of keeping a second
    generator: dashboard.py used to emit its own INDEX.md with a different column set and a
    different template rule, so the same filename meant two things depending on who wrote it.
    """
    coord_dir = coord_dir or COORD
    q_rows = parse_questions(os.path.join(coord_dir, "QUESTIONS.md"), diagnostics)
    h_rows = parse_handoffs(os.path.join(coord_dir, "HANDOFFS.md"), diagnostics)

    q_open = [r for r in q_rows if r["state"] == "open"]
    q_closed = [r for r in q_rows if r["state"] == "closed"]
    q_unknown = [r for r in q_rows if r["state"] is None]
    h_live = [r for r in h_rows if not r["is_template"]]
    h_open = [r for r in h_live if r["state"] == "open"]
    h_closed = [r for r in h_live if r["state"] == "closed"]
    h_unknown = [r for r in h_live if r["state"] is None]

    out = []
    out.append("# INDEX " + EM_DASH + " open items in `QUESTIONS.md` and `HANDOFFS.md`\n")
    out.append(
        "Built by `coordination/tools/build_index.py` " + EM_DASH + " the question/decision text itself is "
        "NOT duplicated here, only number/status/line to jump to. Rebuild after editing the "
        "journals: `python coordination/tools/build_index.py --out coordination/INDEX.md`.\n"
    )
    out.append(f"## QUESTIONS.md {EM_DASH} open ({len(q_open)} of {len(q_rows)})\n")
    out.append(render_table(q_open, "id", "who", "To"))
    out.append(f"\n## HANDOFFS.md {EM_DASH} open or missing status ({len(h_open)} of {len(h_live)})\n")
    out.append(render_table(h_open, "date"))

    # Unrecognised rows get their own section rather than being folded into either side.
    # An operator reading INDEX.md must see that some rows could not be classified; a
    # warning printed to a terminal nobody watched is how "Open Questions: 0" got believed.
    if q_unknown or h_unknown:
        out.append(
            f"\n## {WARNING_SIGN} Unrecognised ({len(q_unknown) + len(h_unknown)})\n"
            "\nThese rows use a status outside the documented vocabulary, so they are counted "
            "in NEITHER the open nor the closed totals above. Fix the files; the tools "
            "deliberately do not guess at a translation.\n"
        )
        if q_unknown:
            out.append(render_table(q_unknown, "id", "who", "To"))
        if h_unknown:
            out.append(render_table(h_unknown, "date"))

    out.append(f"\n<details><summary>QUESTIONS.md {EM_DASH} closed ({len(q_closed)})</summary>\n\n")
    out.append(render_table(q_closed, "id", "who", "To"))
    out.append("\n</details>\n")
    out.append(f"\n<details><summary>HANDOFFS.md {EM_DASH} closed ({len(h_closed)})</summary>\n\n")
    out.append(render_table(h_closed, "date"))
    out.append("\n</details>\n")

    return "\n".join(out), len(q_rows), len(h_rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True, help="where to write INDEX.md")
    ap.add_argument(
        "--coordination-dir", default=None,
        help="directory holding QUESTIONS.md and HANDOFFS.md "
             "(default: the coordination/ directory next to this script)",
    )
    ap.add_argument(
        "--strict", action="store_true",
        help="exit 2 if anything could not be interpreted (default: warn on stderr, exit 0)",
    )
    args = ap.parse_args()

    diagnostics = []
    text, q_count, h_count = build_index_text(args.coordination_dir or COORD, diagnostics)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"written: {args.out} ({q_count} questions, {h_count} handoffs)")

    for d in diagnostics:
        print(f"WARN {d}", file=sys.stderr)
    if diagnostics:
        print(
            f"WARN {len(diagnostics)} item(s) could not be interpreted; they are listed under "
            "'Unrecognised' in the index and counted in neither total.",
            file=sys.stderr,
        )
        if args.strict:
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
