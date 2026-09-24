#!/usr/bin/env python3
"""probe_settings_local_env.py - does `.claude/settings.local.json` `env` reach a PreToolUse hook?

Question from #65: a session launched from the desktop app has no place to set
COORDINATION_ROLE, so the ownership barrier allows everything there. If a per-worktree
`.claude/settings.local.json` `{"env": {"COORDINATION_ROLE": ...}}` reaches hook processes,
that already solves it and no new identity file is needed.

What this does, stdlib only, on any OS:

  1. Takes the LATEST scaffold from the skill repository's `origin/main` via `git archive` --
     the local working tree is not touched, however old it is.
  2. Builds a throwaway project at --dest: coordination/ and .claude/ as installed, the
     ownership hook registered in .claude/settings.json, and settings.local.json setting the
     role to B. B does not own coordination/BOARD.md (ORCH does), so an edit there must be denied.
  3. Checks the hook script alone with synthetic stdin (proves the barrier itself works).
  4. If the `claude` CLI is on PATH, runs two headless sessions that try to edit BOARD.md:
       A  with settings.local.json   -> the edit should be DENIED if env reaches the hook
       B  without it (control)       -> the edit should go THROUGH
     and judges by whether the file actually changed, not by what the model says.
  5. Writes REPORT.md in --dest and prints it.

Caveat: step 4 launches sessions from a CLI, not from the desktop app. It answers "does the
harness pass settings.local.json env to hooks at all" -- which is most of the question. The
desktop-launch case is one manual repeat of probe A from the app in the same folder.

    python3 probe_settings_local_env.py --skill-repo ~/src/multi-agent-coordination-skill
    python3 probe_settings_local_env.py --skill-repo ... --dest ~/coord-probe --no-cli
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROLE = "B"
TARGET = "coordination/BOARD.md"
PROMPT = (
    "Use the Edit tool (not Bash) to append the line `probe` at the end of "
    "coordination/BOARD.md. If the edit is refused, stop and report the reason verbatim."
)


def run(cmd, cwd=None, check=True, **kw):
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def latest_assets(skill_repo, workdir):
    run(["git", "-C", str(skill_repo), "fetch", "-q", "origin", "main"])
    sha = run(["git", "-C", str(skill_repo), "rev-parse", "--short", "origin/main"]).stdout.strip()
    blob = subprocess.run(["git", "-C", str(skill_repo), "archive", "origin/main", "assets"],
                          check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(blob)) as tar:
        tar.extractall(workdir)
    return Path(workdir) / "assets", sha


def build_project(assets, dest):
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    sys.path.insert(0, str(assets / "coordination" / "tools"))
    from coordlib.manifest import hash_tree, installed_path_for
    for rel in hash_tree(str(assets)):
        target = dest / installed_path_for(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(assets / rel, target)

    hook = '"%s" "$CLAUDE_PROJECT_DIR/.claude/hooks/check-path-ownership.py"' % sys.executable
    settings = {"hooks": {"PreToolUse": [{
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [{"type": "command", "command": hook}]}]}}
    (dest / ".claude" / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")
    (dest / ".gitignore").write_text(".claude/settings.local.json\n", encoding="utf-8")
    run(["git", "init", "-q"], cwd=dest)
    run(["git", "add", "-A"], cwd=dest)
    run(["git", "-c", "user.name=probe", "-c", "user.email=probe@localhost",
         "commit", "-q", "-m", "probe baseline"], cwd=dest)


def write_local_env(dest, present):
    path = dest / ".claude" / "settings.local.json"
    if present:
        path.write_text(json.dumps({"env": {"COORDINATION_ROLE": ROLE}}, indent=2), encoding="utf-8")
    elif path.exists():
        path.unlink()


def hook_alone(dest):
    payload = json.dumps({"tool_name": "Edit", "cwd": str(dest),
                          "tool_input": {"file_path": str(dest / TARGET)}})
    env = dict(os.environ, COORDINATION_ROLE=ROLE, CLAUDE_PROJECT_DIR=str(dest))
    env.pop("COORDINATION_ROLE_ID", None)
    out = run([sys.executable, "-B", str(dest / ".claude/hooks/check-path-ownership.py")],
              cwd=dest, input=payload, env=env, check=False).stdout
    return "deny" if '"deny"' in out else "allow"


def board_changed(dest):
    return bool(run(["git", "diff", "--name-only", "--", TARGET], cwd=dest).stdout.strip())


def cli_probe(dest, with_env):
    write_local_env(dest, with_env)
    run(["git", "checkout", "-q", "--", TARGET], cwd=dest)
    env = dict(os.environ)
    env.pop("COORDINATION_ROLE", None)      # the variable must come from settings, nowhere else
    env.pop("COORDINATION_ROLE_ID", None)
    try:
        res = run(["claude", "-p", PROMPT, "--permission-mode", "acceptEdits",
                   "--output-format", "text"], cwd=dest, check=False, env=env, timeout=300)
        said = (res.stdout or res.stderr).strip()
    except subprocess.TimeoutExpired:
        said = "(timed out after 300s)"
    return board_changed(dest), said


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skill-repo", required=True, help="local clone of multi-agent-coordination-skill")
    ap.add_argument("--dest", default=str(Path.home() / "coord-probe"), help="throwaway project dir")
    ap.add_argument("--no-cli", action="store_true", help="build and self-check only; no claude runs")
    args = ap.parse_args()
    dest = Path(args.dest).expanduser().resolve()

    with tempfile.TemporaryDirectory() as tmp:
        assets, sha = latest_assets(Path(args.skill_repo).expanduser(), tmp)
        build_project(assets, dest)

    lines = ["# settings.local.json env -> hook probe (#65)", "",
             "- scaffold: origin/main `%s`" % sha, "- project: `%s`" % dest,
             "- python: `%s` on %s" % (sys.executable, sys.platform), ""]
    alone = hook_alone(dest)
    lines.append("- hook alone, COORDINATION_ROLE=B on %s: **%s** (expected deny)" % (TARGET, alone))

    have_cli = shutil.which("claude") is not None
    if args.no_cli or not have_cli:
        write_local_env(dest, True)          # ready for the manual desktop-app run
        lines.append("- CLI probes skipped (%s)" % ("--no-cli" if args.no_cli else "claude not on PATH"))
        verdict = "not run"
    else:
        a_changed, a_said = cli_probe(dest, with_env=True)
        b_changed, b_said = cli_probe(dest, with_env=False)
        lines += ["- A with settings.local.json: BOARD.md %s" % ("CHANGED" if a_changed else "unchanged"),
                  "  > " + a_said.replace("\n", "\n  > ")[:1500],
                  "- B without it (control): BOARD.md %s" % ("CHANGED" if b_changed else "unchanged"),
                  "  > " + b_said.replace("\n", "\n  > ")[:1500]]
        if not a_changed and b_changed:
            verdict = "YES - settings.local.json env reaches the hook (A denied, control allowed)"
        elif a_changed and b_changed:
            verdict = "NO - the edit went through with the env set; the variable does not reach the hook"
        elif not b_changed:
            verdict = ("INCONCLUSIVE - the control edit did not happen either (permissions, model "
                       "refusal, or the hook not registered); read the quotes above")
        else:
            verdict = "INCONCLUSIVE - unexpected combination; read the quotes above"
        write_local_env(dest, True)          # leave the project ready for the manual desktop-app repeat
        run(["git", "checkout", "-q", "--", TARGET], cwd=dest)
    lines += ["", "**Verdict:** %s" % verdict, "",
              "Manual desktop-app repeat: open `%s` in the app, new session, ask it to append a line "
              "to `%s`. settings.local.json (role B) is in place. Denied = env reaches hooks from a "
              "GUI launch too." % (dest, TARGET)]
    report = "\n".join(lines) + "\n"
    (dest / "REPORT.md").write_text(report, encoding="utf-8")
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
