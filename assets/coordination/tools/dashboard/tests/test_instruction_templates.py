"""
test_instruction_templates.py - the AGENTS.md / CLAUDE.md template split.

Claude Code reads CLAUDE.md and does NOT read AGENTS.md. The split therefore only works if
CLAUDE.md.template actually imports the other file; drop that one line and every
vendor-neutral instruction silently stops reaching the session, with no error anywhere.
"""

import re
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
