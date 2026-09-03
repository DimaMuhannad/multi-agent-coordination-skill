"""
test_blocking_visibility.py - a blocking question must be impossible to walk past.

`PROJECT.md`'s question protocol says a `blocking` question means the role STOPS and makes
no changes until it is answered. So an unanswered one is not an item on a list -- it is a
halted session, and the owner is the only one who can restart it.

Before this, the `Type` column was not parsed at all: "blocking" was a word in a markdown
table that no tool read, and a stopped session looked exactly like a working one.
"""

import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parents[1]
_ASSETS_DIR = _TESTS_DIR.parents[3]

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import build_index  # noqa: E402
from coordlib import diagnostics as diag  # noqa: E402

WORKFLOW = _ASSETS_DIR / "dot-github" / "workflows" / "coordination-checks.yml.template"

QUESTIONS = """# QUESTIONS

| # | Question | Owner's answer | Type | Status |
|---|---|---|---|---|
| Q-1 | Which database do we commit to? |  | blocking | open |
| Q-2 | Tabs or spaces? | took the default | non-blocking | resolved |
| Q-3 | Rename the module? |  | non-blocking | open |
| Q-4 | Already answered blocker | yes | blocking | resolved |
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


@pytest.fixture
def coord(tmp_path):
    _write(tmp_path / "QUESTIONS.md", QUESTIONS)
    _write(tmp_path / "HANDOFFS.md", "# HANDOFFS\n")
    return tmp_path


def test_the_type_column_is_actually_parsed(coord):
    """It was not, which is why nothing could act on it."""
    rows = build_index.parse_questions(str(coord / "QUESTIONS.md"))
    by_id = {row["id"]: row for row in rows}
    assert by_id["Q-1"]["type"] == "blocking"
    assert by_id["Q-3"]["type"] == "non-blocking"


def test_only_OPEN_blocking_questions_count(coord):
    """An answered blocker is not a stopped session, and must not keep the check red."""
    text, _, _, blocking = build_index.build_index_text(str(coord))
    assert blocking == 1
    assert "Q-1" in text


def test_blocking_section_comes_before_everything_else(coord):
    """A section below three tables is a section nobody scrolls to."""
    text, _, _, _ = build_index.build_index_text(str(coord))
    assert text.index("BLOCKING") < text.index("QUESTIONS.md — open")


def test_no_blocking_section_when_nothing_is_blocked(tmp_path):
    """A banner that is always present stops carrying information."""
    _write(tmp_path / "QUESTIONS.md",
           "# Q\n\n| # | Question | Owner's answer | Type | Status |\n"
           "|---|---|---|---|---|\n| Q-1 | x |  | non-blocking | open |\n")
    _write(tmp_path / "HANDOFFS.md", "# H\n")
    text, _, _, blocking = build_index.build_index_text(str(tmp_path))
    assert blocking == 0
    assert "BLOCKING" not in text


def test_an_unrecognised_type_is_reported_not_guessed(tmp_path):
    """The None-means-unrecognised rule: a translated word is never assumed non-blocking."""
    _write(tmp_path / "QUESTIONS.md",
           "# Q\n\n| # | Question | Owner's answer | Type | Status |\n"
           "|---|---|---|---|---|\n| Q-1 | x |  | блокирующий | open |\n")
    _write(tmp_path / "HANDOFFS.md", "# H\n")
    sink = diag.DiagnosticList()
    rows = build_index.parse_questions(str(tmp_path / "QUESTIONS.md"), sink)
    assert rows[0]["type"] is None
    assert diag.UNKNOWN_TYPE in sink.codes()


def _run(coord, out, *args):
    return subprocess.run(
        [sys.executable, "-B", str(_TOOLS_DIR / "build_index.py"),
         "--coordination-dir", str(coord), "--out", str(out), *args],
        capture_output=True, text=True,
    )


def test_cli_exits_1_only_with_the_flag(coord, tmp_path):
    """Default stays exit 0: an index build is not a gate unless asked to be one."""
    out = tmp_path / "INDEX.md"
    assert _run(coord, out).returncode == 0
    assert _run(coord, out, "--fail-on-blocking").returncode == 1


def test_cli_names_the_blockage_on_stderr(coord, tmp_path):
    result = _run(coord, tmp_path / "INDEX.md", "--fail-on-blocking")
    assert "BLOCKING" in result.stderr
    assert "waiting on the owner" in result.stderr


def test_cli_is_green_once_the_blocker_is_answered(tmp_path):
    _write(tmp_path / "QUESTIONS.md",
           "# Q\n\n| # | Question | Owner's answer | Type | Status |\n"
           "|---|---|---|---|---|\n| Q-1 | x | yes | blocking | resolved |\n")
    _write(tmp_path / "HANDOFFS.md", "# H\n")
    assert _run(tmp_path, tmp_path / "INDEX.md", "--fail-on-blocking").returncode == 0


def test_the_shipped_workflow_wires_the_check_up():
    """A flag no template uses is a flag nobody runs."""
    with open(WORKFLOW, "r", encoding="utf-8") as handle:
        text = handle.read()
    assert "blocking-questions:" in text
    assert "--fail-on-blocking" in text


def test_the_shipped_questions_template_has_no_open_blocker():
    """The scaffold must not ship a project into a red CI check on day one."""
    _, _, _, blocking = build_index.build_index_text(str(_ASSETS_DIR / "coordination"))
    assert blocking == 0
