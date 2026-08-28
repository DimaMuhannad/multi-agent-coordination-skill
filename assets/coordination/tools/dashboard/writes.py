"""
writes.py - the write gate. Stdlib only; deliberately no streamlit import.

docs/ru/CONCEPT.md §6.5 states the scaffold's invariant: the interface is a read-only
projection over git, and the files stay the source of truth. §6.4 warns specifically against
the drift that produced this module -- "first it shows status, then it seems convenient to
change it there too".

The dashboard does write. Rather than delete the warning because the code violated it, the
conditions under which writing does not violate the invariant are made explicit and
enforced here (CONCEPT.md §6.6):

  (a) every write lands in the same markdown, in the canonical format -- no second store;
  (b) every write is previewed as a diff and confirmed by a human;
  (c) every write is a git commit with CHARTER.md §4 trailers -- git stays the arbiter;
  (d) the UI refuses to write any file whose schema it did not recognise.

(d) is the one that connects the two halves of issue #6: a tool that could not read a file
correctly must not be trusted to write to it.

Writing is OFF by default. It is enabled per-session by the operator, not by the code:

    COORDINATION_DASHBOARD_WRITES=1 streamlit run dashboard.py
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from coordlib.diagnostics import UNSAFE_TO_WRITE_CODES as _UNSAFE_CODES  # noqa: E402

WRITES_ENV_VAR = "COORDINATION_DASHBOARD_WRITES"

_TRUTHY = {"1", "true", "yes", "on"}

READ_ONLY_NOTICE = (
    "Read-only. The dashboard shows state; it does not change it. To enable writing, "
    f"restart with `{WRITES_ENV_VAR}=1`. Every write is still previewed as a diff and "
    "confirmed before anything is saved."
)


def writes_enabled(environ=None) -> bool:
    """True only when the operator explicitly opted in for this session."""
    env = os.environ if environ is None else environ
    return str(env.get(WRITES_ENV_VAR, "")).strip().lower() in _TRUTHY


@dataclass
class WriteGate:
    """Whether a specific write may proceed, and why not when it may not."""

    allowed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.allowed


def gate(plan_ok: bool, file_diagnostics=None, environ=None) -> WriteGate:
    """Decide whether a write may proceed.

    Three independent reasons to refuse, checked in the order the operator would want to
    hear them: the session is read-only, the file could not be read, or the plan itself
    failed to resolve a target.
    """
    if not writes_enabled(environ):
        return WriteGate(False, READ_ONLY_NOTICE)

    blocking = [
        d for d in (file_diagnostics or [])
        if getattr(d, "code", None) in _UNSAFE_CODES
    ]
    if blocking:
        listed = "; ".join(str(d) for d in blocking[:3])
        return WriteGate(
            False,
            "This file's schema was not recognised, so its rows could not be located "
            f"reliably. Edit it by hand instead. {listed}",
        )

    if not plan_ok:
        return WriteGate(False, "The change could not be resolved to a specific line.")

    return WriteGate(True)



@dataclass
class PendingWrite:
    """A planned but unconfirmed write, held between the preview and the Apply click."""

    key: str
    plan: object
    commit_message: str
    trailers: dict = field(default_factory=dict)
    author_role: str = ""
    commit: bool = False

    @property
    def description(self) -> str:
        return getattr(self.plan, "target_description", "") or ""

    @property
    def diff(self) -> str:
        return self.plan.diff() if hasattr(self.plan, "diff") else ""


def roles_from_board(board_rows) -> List[str]:
    """Committer-role options, read from BOARD.md rather than hardcoded.

    dashboard.py shipped the source project's roster
    (["ORCH", "frontend", "physics", "qa_tester", "architect", "owner"]) baked into a
    template, so every project that installed the skill inherited another project's roles -
    and a role added through the dashboard never appeared in the list.
    """
    seen = []
    for row in board_rows or []:
        role = (row.get("role") or "").strip()
        if role and role not in seen:
            seen.append(role)
    return seen


def revert_hint(sha: Optional[str]) -> str:
    """What to show after a commit, in place of an undo the dashboard does not have.

    Honest and stateless: git already holds the history, so the recovery path is git's.
    """
    if not sha:
        return ""
    return f"git revert {sha}"
