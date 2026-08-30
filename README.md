# multi-agent-coordination-skill

A [Claude Code Skill](https://docs.claude.com/en/docs/claude-code/skills) that sets up a
coordination scaffold for projects where several agent sessions — each holding a distinct,
continuing role/zone — share one repository over an extended period.

The scaffold is platform-agnostic: a role is held by whatever session reads its file and makes
commits, so Claude Code, Gemini via Antigravity, Cursor or Aider can each hold one. See
[`docs/ru/CROSS_PLATFORM_BRIDGE.md`](docs/ru/CROSS_PLATFORM_BRIDGE.md).

That is enforced by the file layout rather than left to good intentions: the project's rules
live in **`AGENTS.md`**, the cross-vendor convention governed since December 2025 by the Linux
Foundation's [Agentic AI Foundation](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation),
and `CLAUDE.md` is a four-line adapter that imports it and adds the Claude Code specifics
(`claude -n <name>`, `claude agents --json`, `.claude/rules/` globs). Claude Code reads
`CLAUDE.md` and not `AGENTS.md`, which is exactly why the adapter exists.

It does not compete with a tool's own multi-agent features. Claude Code's agent teams keep
their shared task list in `~/.claude/`, scoped to one session and deleted when it ends; this
scaffold is the durable half — in git, on every machine, readable by any tool.

It's not a framework or a running service: there's no server, no live process registry, no
database. It's a set of markdown templates and two small stdlib-only Python scripts, distilled
from a real multi-role project that ran this paradigm for weeks and fixed the specific problems
it hit along the way. Those problems — and why the fix looks the way it does — are written up in
[`references/rationale.md`](references/rationale.md).

## What's in it

- **`coordination/` templates** — role zone files, an append-only decision journal
  (`QUESTIONS.md`), cross-role request log (`HANDOFFS.md`), project-wide activity journal
  (`ACTIVITY.md`), ownership map, charter of working rules, and a launch-prompt table.
- **`.claude/hooks/check-context-budget.py`** — a `SessionStart` hook that warns (never blocks)
  when a role's cold-start file grows past its byte budget, so "keep this file short" stays true
  without anyone having to remember to check.
- **`coordination/tools/coordlib/`** — the shared, stdlib-only core: one status vocabulary, one
  markdown-table tokenizer, and the diagnostics channel the tools use to say "this file's schema
  was not recognised" instead of quietly reporting zero.
- **`.claude/rules/`** — an example of Claude Code's path-scoped `paths:` rule files, for pushing
  domain knowledge out of the always-loaded `CLAUDE.md` and into context only when a session
  actually touches the relevant paths.
- **`coordination/tools/build_index.py`** — turns `QUESTIONS.md` + `HANDOFFS.md` into a short
  open/closed index, so nobody has to read either journal in full just to see what's outstanding.
- **`coordination/tools/kpi_git.py`** — per-role commit/line/active-day stats from `git log`
  alone (no external telemetry, no live process tracking) — with configurable exclusions for
  bulk-import commits and non-authored (data/generated) paths.

### Optional add-ons

Neither is part of the base scaffold; install one only when the project has actually hit the
problem it solves.

- **git/GitHub rails** (`assets/dot-github/`) — CODEOWNERS, CI checks. See
  [`references/git-github-rails.md`](references/git-github-rails.md).
- **`coordination/tools/dashboard/`** — a Streamlit dashboard over the journals. It is the only
  piece here that requires a third-party dependency, and the only one that **writes**. It is
  read-only by default; writing is enabled per session with
  `COORDINATION_DASHBOARD_WRITES=1`, and every write is previewed as a diff and confirmed
  before it is saved. The core scaffold stays markdown plus stdlib Python.

## Using it

Install as a Claude Code Skill (see Claude Code's skill docs for how skills are discovered in
your setup), then in a project that needs this, ask Claude something like "set up multi-agent
coordination for this project" — the skill interviews you for the project name, roles, and
guardrails, then instantiates the templates. See [`SKILL.md`](SKILL.md) for exactly what it does,
and [`references/setup.md`](references/setup.md) for the manual/mechanical version of the same
steps if you'd rather do it by hand.

Русская версия концепции (обязательный и необязательный слой, границы, human-интерфейс):
[`docs/ru/CONCEPT.md`](docs/ru/CONCEPT.md).

## License

MIT — see [`LICENSE`](LICENSE).
