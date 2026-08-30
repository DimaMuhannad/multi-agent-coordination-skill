---
name: multi-agent-coordination
description: Sets up a battle-tested multi-session/multi-role Claude Code coordination scaffold — role zones, an append-only decision journal, cold-start budget checks, cross-role handoffs, and a KPI-from-git script — for a project where several Claude Code sessions (or a human plus several sessions) work the same repository in parallel roles. Use this whenever the user wants to run multiple Claude Code sessions/agents on one project, coordinate parallel roles or "subagents as team members," avoid sessions stepping on each other's files, set up a coordination directory, or asks for something like "multi-agent workflow," "team of Claude sessions," "role-based coordination," or "how do I keep several Claude Code sessions from conflicting." Also use it to review or fix an EXISTING coordination setup that's showing the specific failure modes this skill was built to prevent (see references/rationale.md) — status-line phrasing drift, duplicated launch prompts going stale, an ever-growing orchestrator brief, or someone about to turn a role into a `.claude/agents/` subagent definition.
---

# Multi-Agent Coordination

This skill instantiates a coordination scaffold that a real multi-role Claude Code project
(several sessions, each holding a distinct specialty/zone, sharing one repository) evolved over
weeks of actual use — including the specific mistakes it made and fixed. `references/rationale.md`
documents those mistakes; read it before deciding to simplify or skip a piece of the scaffold, in
case the piece you're about to drop is exactly the fix for a failure mode you haven't hit yet.

## When this fits, and when it doesn't

This is for a project where **multiple agent sessions genuinely need to hold distinct,
continuing responsibilities** ("zones") in the same repository over an extended period — not a
single session doing one task, and not a one-off parallel fan-out you'd reach for the `Agent`
tool for instead. The giveaway questions: will more than one named, persistent session work this
repo over multiple sittings? Does each one own a distinct part of it well enough that "whose job
is this edit" is a real question? If the honest answer is "no, this is one session working
through a task list," this scaffold is overhead — say so and don't set it up.

## What to do

### 1. Run discovery, THEN interview

**First, read what the repository already knows** (`references/setup.md §0`):

```bash
python3 <this-skill>/assets/coordination/tools/discover.py --root . --json
```

It writes nothing and reports: candidate zones with who actually edits them (from git
history), any existing `CODEOWNERS`, instruction files another agent tool left behind, the
verification commands already defined, a language guess with its evidence, and whether the
scaffold is already installed.

In an empty repository this returns little and the interview below carries everything. In a
live one it changes what you ask: in a new project `CHARTER.md` is a statement of intent,
but in an existing one it is archaeological — the codebase already works some way and the
scaffold must describe that, not overwrite it.

**Present everything discovery found as a default to confirm, not as a question.** Asking
what directories exist when `git log` answers it teaches the owner that this questionnaire
is not worth reading, and then the questions that genuinely need them get skimmed too.

Two findings change what you DO, not what you ask: an existing `AGENTS.md` / `CLAUDE.md` /
`.cursorrules` is imported, never replaced; an existing `CODEOWNERS` seeds `OWNERSHIP.md`
instead of an empty table.

**Then ask what evidence cannot settle.** Don't guess these — they shape every template:

- **Project name and what it does** (a sentence or two — goes at the top of `CLAUDE.md`).
- **Documentation/commit language** — the source project used Russian throughout; yours might be
  English or something else. Every template here is written in English as the *scaffold*
  language, but the user's project content (zone descriptions, role names, actual entries) should
  be written in whatever language the user's project actually uses.
- **The roles** — how many, what each one's specialty and zone is, and a short session-name
  convention (the source project used `<letter>-<specialty>`, e.g. `a-model`, but that's a
  convention, not a requirement). Don't invent roles the user didn't ask for; a project with two
  roles doesn't need the same shape as one with seven.
- **Is there an orchestrator role** — a session that coordinates the others, merges branches,
  keeps `coordination/**` current? Many projects want one; some don't (a human filling that role
  directly is fine too — then skip `ORCH_BRIEF.md` and the orchestrator row in the templates).
- **Does work span multiple machines/environments** (a workstation, a laptop, an ephemeral cloud
  sandbox)? If so, `PROJECT.md`'s multi-environment section is worth filling in carefully — that's
  exactly where "which mechanism sees what" assumptions go wrong.
- **What are the actual hard guardrails** — read-only paths, a push-only-with-permission rule,
  domain-specific quality bars. These go in `CLAUDE.md`'s guardrails section; don't invent generic
  ones, ask what actually matters for this project.

### 2. Instantiate the templates

Read `references/setup.md` for the exact directory layout, file order, and hook-wiring steps —
follow it rather than improvising the layout, since later templates reference earlier ones by
exact path. In short: copy everything under this skill's `assets/` into the target project
(dropping the `.template` suffix where present, and `dot-claude/` becomes `.claude/`), then fill
in the placeholders (`<PROJECT NAME>`, `<ID>`, `<LANGUAGE>`, role tables, zone descriptions) from
the interview — one `roles/<ID>.md` per role the user named. Wire the `SessionStart` hook into
`.claude/settings.json` per `references/setup.md §2`, and verify it actually fires before calling
the setup done.

**Record the install stamp as the last step.** Once every placeholder is filled, run
`python3 coordination/tools/upgrade.py --adopt --from <this-skill>/assets`. It writes
`coordination/.scaffold-version`, which is what lets a later `upgrade.py` distinguish "the
project changed this" from "upstream changed this" without a network. Run it *after*
filling, not before: the stamp records the filled content as the baseline, which is what
keeps your own install from reading as drift forever. Skip it and the project is cut off
from every fix made upstream from that day on (`references/setup.md §10`).

**Both `AGENTS.md` and `CLAUDE.md` get created, and the split matters.** The project's actual
rules go in `AGENTS.md`; `CLAUDE.md` is a thin file whose first line is `@AGENTS.md` plus the
Claude Code specifics. Claude Code reads `CLAUDE.md` and does *not* read `AGENTS.md`, so if you
create only one of them, make sure it is `CLAUDE.md` — and if you drop the import line, every
shared rule silently stops reaching the session. `references/setup.md §1` has the reasoning.

**Keep every `roles/<ID>.md` within its cold-start budget from the very first version.** It's
tempting to write a thorough first draft with lots of context — resist it. The budget hook will
catch growth later, but a file that starts oversized normalizes staying oversized.

### 3. Don't over-fill speculative content

Several templates (`QUESTIONS.md`, `ACTIVITY.md`, `HANDOFFS.md`, `kpi_config.json`) are meant to
start nearly empty and grow from real use, not be pre-populated with guessed content. Filling
`OWNERSHIP.md`'s "conflict hot spots" section with hypothetical conflicts nobody's hit yet, for
instance, produces noise a real conflict later will be buried under. Populate what the interview
actually established; leave placeholders as placeholders where the project doesn't have an answer
yet, and say so to the user rather than inventing one.

### 4. Explain what you set up, briefly

After instantiating, tell the user in a few sentences: where the role entry points are, how to
launch a session, and where the guardrails live — not a full walkthrough of every file, since the
templates themselves are meant to be self-explanatory reading. Point them at
`references/rationale.md` if they ask *why* something is shaped a particular way, and at
`references/agent-tooling.md` for which platform capabilities (planning, structured questions,
subagent use, verification, isolation) a role is expected to reach for and when — that file
covers a role's own conduct, not the scaffold's file layout.

### 5. Not Claude-Code-only

A role is held by whatever session reads `coordination/roles/<ID>.md` and makes commits, so the
scaffold works for Claude Code, Gemini via Antigravity, Cursor, Aider or a human. The file split
in §2 is what keeps that true in practice rather than only in principle: everything a
non-Claude session needs is in `AGENTS.md`, which is the cross-vendor convention for exactly
this and has been governed by the Linux Foundation's Agentic AI Foundation since December 2025.

Claude Code conveniences that belong in `CLAUDE.md`, never in `AGENTS.md`: `claude -n <name>`
for naming a session, `claude agents --json` for "who is working right now", `.claude/rules/`
globs, and the hook wiring. On another platform, skip them — git is the arbiter there, which
`CHARTER.md` already says for the cross-machine case. Do NOT add a replacement liveness
registry; `CONCEPT.md §3.5` explains why that was deliberately excluded.

**Where the scaffold sits next to a tool's own multi-agent features.** Several tools now ship
in-session parallelism with a shared task list and inter-agent messaging (Claude Code's
subagents and agent teams, for instance). Those are *working* memory: their state lives outside
the repository, is scoped to one session, and is discarded when it ends. The journals are
*durable* memory. The two are complements, not alternatives — use the tool's teammates freely,
and write anything that must outlive the session into `HANDOFFS.md`, `QUESTIONS.md` or
`ACTIVITY.md`. If a user asks whether agent teams replace this scaffold, that is the answer.

### 6. Optional: git/GitHub rails

Not part of the interview above, and not something to set up by default — only reach for it when
the user explicitly asks about GitHub-side enforcement (CI, required reviewers, branch protection)
or the project has actually hit a failure mode this addresses (a commit landed broken because a
session skipped the local hook; a shared "hot spot" file keeps colliding). Read
`references/git-github-rails.md` first — it covers what's genuinely documented as native Claude
Code behavior versus a GitHub feature the project adds, which of `assets/dot-github/*` to copy in,
and an explicit warning against moving `QUESTIONS.md`/`HANDOFFS.md` onto GitHub Issues. Same
principle as step 3: don't pre-install this speculatively.

### 7. Optional: the Streamlit dashboard

Same rule as the rails: not part of the interview, not installed by default. It is the only
piece of the scaffold that needs a third-party dependency, and the only one that **writes** to
the journals. Reach for it when a human wants to see project state without reading four files,
and say plainly what it does and does not do:

- read-only by default; writing requires `COORDINATION_DASHBOARD_WRITES=1` for that session;
- every write is previewed as a diff, names its destination table, and is confirmed by a human;
- it refuses to write to any file whose schema it could not read;
- git remains the arbiter — each write is a commit with `CHARTER.md §4` trailers.

Those four conditions are what keep it compatible with `docs/ru/CONCEPT.md §6.5`'s invariant
("the interface is a read-only projection over git") rather than a second source of truth; they
are written up as §6.6 there. If a project only wants the read-only view, `build_index.py` gives
it with no dependencies at all.

## Found a bug in the scaffold itself, not just this project's setup

Distinct from the section below: if what a role hits is a defect in a template, hook, or tool
this skill ships — not a drift in how this particular project configured it — read
`references/upstream-feedback.md` before quietly patching it locally and moving on. A local patch
that never leaves the project either gets silently lost on the next re-copy of the scaffold, or
leaves every other project built from it to rediscover the same bug independently.

## Reviewing or fixing an existing setup

If the user already has a coordination directory (theirs or one this skill set up before) and
wants it reviewed or fixed, check specifically for the failure modes in `references/rationale.md`
— status-line phrasing that's drifted from one exact string, a launch-prompts file that's grown
to duplicate role files, an orchestrator brief mixing durable goals with dated snapshots, or a
role that's been turned into (or is about to be turned into) a `.claude/agents/*.md` subagent
definition. Fix the specific thing found rather than replacing their whole setup with this
skill's templates — their setup has presumably diverged for reasons specific to their project.

## Reference files

- `references/setup.md` — the mechanical instantiation steps: directory layout, hook wiring, fill
  order, how to run `build_index.py` / `kpi_git.py`.
- `references/rationale.md` — the failure modes this scaffold's specific shapes were built to
  prevent, and why the fix looks the way it does. Read before removing or simplifying a piece of
  the scaffold.
- `references/agent-tooling.md` — which capabilities of the agentic system running a role
  (planning, structured questions, subagent use, verification, isolation) that role is expected
  to reach for, and in which situations — a role's own conduct, distinct from the scaffold's file
  layout.
- `references/upstream-feedback.md` — how to report a defect in the scaffold itself back to this
  skill instead of only patching it locally: distinguishing scaffold bugs from project-specific
  drift, marking a local patch until it's accepted upstream, and the report shape that has
  actually gotten fixes merged.
- `references/git-github-rails.md` — optional server-side layer (CODEOWNERS, CI checks, when to
  use a real PR instead of a `HANDOFFS.md` entry) for a project that's outgrown pure client-side
  enforcement. Read only when step 5 above applies.
- `docs/ru/CROSS_PLATFORM_BRIDGE.md` — LLM agnosticism, per-role isolation via `git worktree`,
  and the soft context limit. Russian.

For a read-only view of project state with no dependencies, run `build_index.py`: it writes
`INDEX.md` with the open items from `QUESTIONS.md`/`HANDOFFS.md` and a separate section for
anything it could not interpret.
