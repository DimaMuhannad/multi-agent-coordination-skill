"""
test_discover.py - repository reconnaissance.

The cases worth writing are the ones where a naive implementation is confidently wrong: a
target that is not a git repository, a git worktree (`.git` is a FILE), a repository with
no commits, and a language guess flipped by a single "Русская версия" link in an otherwise
English README. Each of those produced a wrong answer during development.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parents[1]
_ASSETS_DIR = _TESTS_DIR.parents[3]
_REPO_ROOT = _ASSETS_DIR.parent

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import discover as discover_cli  # noqa: E402


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True, check=True)


@pytest.fixture
def repo(tmp_path):
    """A small git repository with two authors touching different directories."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "a@example.com")
    _git(root, "config", "user.name", "Alice")

    _write(root / "src" / "core.py", "x = 1\n")
    _write(root / "README.md", "# Demo\n\nAn English readme.\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "alice: core")

    _git(root, "config", "user.email", "b@example.com")
    _git(root, "config", "user.name", "Bob")
    _write(root / "web" / "index.html", "<h1>hi</h1>\n" * 20)
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "bob: web")
    return root


# ---------------------------------------------------------------------------------------
# Degrading without git
# ---------------------------------------------------------------------------------------

def test_a_directory_that_is_not_a_repository_still_reports(tmp_path):
    """Not being a git repo is a finding, not a failure: the other probes still run."""
    plain = tmp_path / "plain"
    _write(plain / "src" / "a.py", "x = 1\n")
    _write(plain / "package.json", json.dumps({"scripts": {"test": "jest"}}))

    report = discover_cli.discover(plain)
    assert report["is_git_repo"] is False
    assert report["ownership_map"] == []
    assert "src" in report["top_level_directories"]
    assert report["verification_commands"]["package.json"] == ["test"]


def test_repository_with_no_commits_does_not_raise(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    _git(root, "init", "-q")
    report = discover_cli.discover(root)
    assert report["is_git_repo"] is True
    assert report["ownership_map"] == []


def test_worktree_is_handled(repo, tmp_path):
    """`.git` is a FILE inside a worktree; this scaffold's tooling has tripped on it twice."""
    worktree = tmp_path / "wt"
    _git(repo, "worktree", "add", "-q", str(worktree), "-b", "role/qa")
    assert (worktree / ".git").is_file(), "a worktree's .git must be a file for this test"

    report = discover_cli.discover(worktree)
    assert report["is_git_repo"] is True
    assert {zone["path"] for zone in report["ownership_map"]} >= {"src", "web"}


# ---------------------------------------------------------------------------------------
# The empirical ownership map
# ---------------------------------------------------------------------------------------

def test_ownership_map_attributes_directories_to_their_real_authors(repo):
    zones = {zone["path"]: zone for zone in discover_cli.discover(repo)["ownership_map"]}
    assert zones["src"]["top_author"] == "Alice"
    assert zones["web"]["top_author"] == "Bob"
    assert zones["web"]["dominance_pct"] == 100.0


def test_ownership_map_survives_a_binary_file(repo):
    """git numstat writes `-` for binary files, and int("-") raises."""
    with open(repo / "assets.bin", "wb") as handle:
        handle.write(bytes(range(256)))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "add binary")
    report = discover_cli.discover(repo)
    assert report["ownership_map"], "history became unreadable when a binary file appeared"


# ---------------------------------------------------------------------------------------
# Language: the guess that was wrong first time
# ---------------------------------------------------------------------------------------

def test_a_translation_link_does_not_flip_the_language_guess(tmp_path):
    """This repository's own README is English with one "Русская версия" link.

    Presence-based detection called the project Russian on the strength of 69 characters in
    about 5,000. The interview would then have been conducted in the wrong language.
    """
    root = tmp_path / "mostly-english"
    root.mkdir()
    _write(root / "README.md",
           "# Project\n\n" + ("An English sentence about the project. " * 60) +
           "\n\nРусская версия документации: docs/ru/README.md\n")
    language = discover_cli.documentation_language(root)
    assert language["guess"] == "english"
    assert language["counts"]["cyrillic"] > 0


def test_a_genuinely_russian_project_is_detected(tmp_path):
    root = tmp_path / "russian"
    root.mkdir()
    _write(root / "README.md", "# Проект\n\n" + ("Описание проекта на русском языке. " * 40))
    assert discover_cli.documentation_language(root)["guess"] == "russian"


def test_language_is_undetermined_without_any_text(tmp_path):
    root = tmp_path / "bare"
    root.mkdir()
    assert discover_cli.documentation_language(root)["guess"] is None


# ---------------------------------------------------------------------------------------
# The other probes
# ---------------------------------------------------------------------------------------

def test_existing_instruction_files_are_reported_for_import(tmp_path):
    """Found instruction files must be surfaced so the installer imports rather than clobbers."""
    root = tmp_path / "p"
    _write(root / "AGENTS.md", "# Agents\n")
    _write(root / ".cursorrules", "be nice\n")
    _write(root / ".cursor" / "rules" / "api.md", "---\npaths: []\n---\n")
    found = {item["path"] for item in discover_cli.existing_instructions(root)}
    assert {"AGENTS.md", ".cursorrules", ".cursor/rules"} <= found


def test_existing_codeowners_is_parsed(tmp_path):
    root = tmp_path / "p"
    _write(root / ".github" / "CODEOWNERS",
           "# comment\n\n*           @org/core\n/docs/      @writer\n")
    found = discover_cli.existing_codeowners(root)
    assert found["file"] == ".github/CODEOWNERS"
    assert [rule["pattern"] for rule in found["rules"]] == ["*", "/docs/"]
    assert found["rules"][0]["owners"] == ["@org/core"]


def test_malformed_package_json_does_not_crash(tmp_path):
    root = tmp_path / "p"
    _write(root / "package.json", "{ this is not json")
    assert discover_cli.verification_commands(root) == {}


def test_makefile_targets_are_found_but_not_recipe_lines(tmp_path):
    root = tmp_path / "p"
    _write(root / "Makefile", "test:\n\tpytest\n\nlint:\n\truff check .\n\nVAR := 1\n")
    assert discover_cli.verification_commands(root)["Makefile"] == ["lint", "test"]


def test_scaffold_state_detects_an_unstamped_install(tmp_path):
    """The pre-feature project: installed, no baseline, needs --adopt."""
    root = tmp_path / "p"
    _write(root / "coordination" / "OWNERSHIP.md", "# Ownership\n")
    state = discover_cli.scaffold_state(root)
    assert state["installed"] is True
    assert state["stamp"] is None
    assert "--adopt" in state["note"]


def test_scaffold_state_when_absent(tmp_path):
    root = tmp_path / "p"
    root.mkdir()
    assert discover_cli.scaffold_state(root)["installed"] is False


# ---------------------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------------------

def test_cli_json_is_valid_and_exit_is_zero(repo, capsys):
    assert discover_cli.main(["--root", str(repo), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["is_git_repo"] is True


def test_cli_human_output_names_what_it_could_not_answer(repo, capsys):
    """The report must hand the interview its remaining questions, not just findings."""
    discover_cli.main(["--root", str(repo)])
    out = capsys.readouterr().out
    for token in ("roles", "orchestrator", "guardrails"):
        assert token in out


def test_cli_on_a_missing_directory_does_not_fail_the_caller(tmp_path, capsys):
    assert discover_cli.main(["--root", str(tmp_path / "nope")]) == 0


# ---------------------------------------------------------------------------------------
# Against this repository
# ---------------------------------------------------------------------------------------

def test_discovery_of_this_repository(capsys):
    """The one repository we can always guarantee exists."""
    report = discover_cli.discover(_REPO_ROOT)
    assert report["is_git_repo"] is True
    paths = {zone["path"] for zone in report["ownership_map"]}
    assert {"assets", "references"} <= paths
    assert "pytest" in report["verification_commands"]
    # English despite docs/ru/ and the Russian link in the README.
    assert report["documentation_language"]["guess"] == "english"


def test_the_new_tools_are_covered_by_the_dependency_guard():
    """The guard globs `tools/*.py`; a future move into a subpackage would escape it.

    Both new tools must stay flat in `tools/` or the streamlit/dashboard import ban stops
    applying to them silently.
    """
    flat = {path.name for path in (_ASSETS_DIR / "coordination" / "tools").glob("*.py")}
    assert {"discover.py", "upgrade.py"} <= flat
