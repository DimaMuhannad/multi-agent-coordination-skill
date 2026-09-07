"""
test_instruction_templates.py - the AGENTS.md / CLAUDE.md template split.

Claude Code reads CLAUDE.md and does NOT read AGENTS.md. The split therefore only works if
CLAUDE.md.template actually imports the other file; drop that one line and every
vendor-neutral instruction silently stops reaching the session, with no error anywhere.
"""

import re
import subprocess
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parents[4]
AGENTS = _ASSETS_DIR / "AGENTS.md.template"
CLAUDE = _ASSETS_DIR / "CLAUDE.md.template"

LINE_TARGET = 200


def _read(path):
    with open(path, "r", encoding="utf-8", newline="") as handle:
        return handle.read()


def test_claude_template_imports_agents_on_its_first_line():
    """The import must not sit inside a code span or fence, where it is not parsed."""
    first = _read(CLAUDE).splitlines()[0].strip()
    assert first == "@AGENTS.md"


def test_both_templates_are_within_the_documented_line_target():
    """Claude Code targets under 200 lines per instruction file, and both load at launch."""
    for path in (AGENTS, CLAUDE):
        assert len(_read(path).splitlines()) <= LINE_TARGET, path.name


def test_claude_only_commands_stay_out_of_the_vendor_neutral_file():
    """A `claude` invocation in AGENTS.md is an instruction other agents cannot follow."""
    agents = _read(AGENTS)
    for token in ("claude agents", "claude -n", ".claude/rules", "/rename"):
        assert token not in agents, "%r belongs in CLAUDE.md.template" % token


def test_claude_template_carries_the_tool_specific_half():
    claude = _read(CLAUDE)
    for token in ("claude agents --json", ".claude/rules", "COORDINATION_ROLE"):
        assert token in claude


def test_templates_have_no_control_bytes_and_are_lf_only():
    for path in (AGENTS, CLAUDE):
        raw = _read(path)
        assert "\r" not in raw, path.name
        assert not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", raw), path.name


# ---------------------------------------------------------------------------------------
# Shipped files must not point at paths that only exist in the skill
# ---------------------------------------------------------------------------------------

_CITATION = re.compile(r"references/\w+\.md")


def _shipped_files():
    """Every file under assets/ that a project receives, tracked by git."""
    listed = subprocess.run(
        ["git", "ls-files", "assets/"], cwd=str(_ASSETS_DIR.parent),
        capture_output=True, text=True, check=True,
    ).stdout.split()
    return [_ASSETS_DIR.parent / name for name in listed]


def test_no_shipped_file_points_at_the_skills_references_as_if_local():
    """`references/` stays in the skill; `assets/` is what lands in a project.

    A shipped file citing one of those paths reads as project-relative and resolves to nothing
    there -- except for a session that happens to have the skill installed, which is the worst
    version: a pointer that works for some readers and silently fails for others. Naming the
    skill on the same line is the whole fix, and this keeps it from regressing.

    Matched as a real document path, so a fixture containing an escape like `\\references/y`
    is not mistaken for a citation.
    """
    offenders = []
    for path in _shipped_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if _CITATION.search(line) and "skill" not in line:
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, (
        "shipped files cite the skill's references/ without saying so:\n  "
        + "\n  ".join(offenders)
    )
