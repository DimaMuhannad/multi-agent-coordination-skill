# CHARTER — core rules for multi-session work

> **Not required cold-start reading.** A role's entry point is `coordination/roles/<ID>.md`;
> universal guardrails live in `CLAUDE.md` (loads automatically). Come here when a rule is
> unclear or you're about to break it.

## 1. Identity

Role ID (see `PROJECT.md` for the roster) is set at launch. Not set — **ask the owner**, don't
work anonymously.

At start: name the session (on Claude Code, `claude -n <session-name>` or `/rename`; on
another platform, whatever it offers) and, if your tool can list its own live sessions, check
that one with your name isn't already `busy` in this `cwd` — on Claude Code that is
`claude agents --json`. If it is, don't start; tell the owner.

There are no locks, timeouts, or heartbeat files in this project. A process registry rots the
moment it isn't perfectly maintained, and it duplicates what a tool's own session list already
gives you for free. But note what that list is and isn't: it sees only **that tool's** sessions
on **this machine**. Across machines, environments, or platforms — a laptop, a workstation, a
cloud sandbox, a Gemini session — it sees nothing. There, and in any dispute, **git is the
arbiter**: recent commits, active branches, and the worktrees under `.worktrees/`.

The same applies to a tool's built-in teammates or subagents. Their shared task list lives
outside this repository and is discarded when the session ends, so it answers "what is my team
doing right now", never "what did this project decide". Anything that must outlive the session
belongs in `HANDOFFS.md`, `QUESTIONS.md` or `ACTIVITY.md`.

## 2. Zones — by layer, not by directory

Your own zone is in `coordination/roles/<ID>.md`; the full map is `OWNERSHIP.md`; the short
role/zone table is `PROJECT.md`.

Two rules cover most cases:

- **Shared/core code** (name the specific files here once you have them) is writable by exactly
  one role. Everyone else is read-only; changes go through `HANDOFFS.md`.
- **Not sure whose zone it is — don't touch it, ask.** A cheap pause beats an expensive mistake.

## 3. Outside your zone — don't do it, redirect

The owner asks for something outside your specialty:

1. Don't do it; briefly say whose zone `<Y>` it is.
2. Write the request into `HANDOFFS.md` (from whom, to whom, what's needed, context).
3. Offer to switch to `<Y>` or launch it (`LAUNCH_PROMPTS.md`).

Exception: trivial reads and lookups are fine. Edits in someone else's zone always go through a
handoff.

## 4. Commits

- Prefix: **`[<ID>] short subject`**.
- Trailers **as the last paragraph, with a blank line before the block and no blank line
  inside it** — git's own trailer parser requires exactly this, and a broken trailer block is
  invisible until you go looking for it:
  ```
  Session: <ID>
  Reason: <why> — one line, a line break breaks the whole block
  ```
  If your project can wire up a `PostToolUse` hook that runs `git interpret-trailers --parse`
  after every commit and reports back when trailers didn't parse, do it — a rule enforced by a
  hook stays true; a rule that only lives in this document rots the moment nobody's checking.
- Commit **only your own paths** — no blind `git add -A`.
- `git push` — **only with the owner's direct permission**. Never force-push or rewrite history.
- A shared-file conflict on `main` → don't force it, call the orchestrator.
- Don't reference commit hashes in coordination docs — link by date + file instead (hashes churn
  if history is ever rewritten; dates don't).

## 5. Isolation (git)

The shared working directory on `main` is for live shared state. A `git worktree` + branch is
worth it for a role that edits shared/core code heavily, or that wants isolation from everyone
else's in-flight changes: `git worktree add ../<repo>-<ID> session/<ID>`. The orchestrator merges.

This is not a local invention — running one agent session per worktree is the standard
isolation model, and Claude Code documents it directly (`/docs/en/worktrees`) as the way to run
several sessions in parallel without automated team coordination. Nothing here needs a wrapper
script; the one-line command above is the whole mechanism.

One gotcha worth knowing because this scaffold's own tooling hit it: inside a worktree, `.git`
is a **file**, not a directory. Any check that tests `isdir(".git")` to find the project root
walks straight past the worktree root — which is why `check-context-budget.py` and
`check-path-ownership.py` both test `exists()` instead.

## 6. Working protocol

**Cold start — once per chat** (and again after `/clear` or `/compact`): `CLAUDE.md` loads
itself, read `coordination/roles/<ID>.md`. That's it.

**Per atomic step:**

1. Your own state file → first not-done task.
2. Do **one** atomic step.
3. Log a significant change to `ACTIVITY.md`.
4. Update your state file; if a finding or decision came out of it, update your own
   `roles/<ID>.md`.

## 7. Conflict resolution

- **A role has gone quiet** → the orchestrator reassigns its tasks. Signal: not in
  `claude agents` **and** no commits for a reasonable stretch. A role's files don't "hold" a
  zone by themselves.
- **Two chats claiming the same role** → visible in `claude agents`; the second one doesn't
  start. Across separate machines/environments nothing shows this automatically — git is the
  arbiter.
- **Overlapping zones** → the orchestrator arbitrates; absent one, the owner decides.
- **A shared file needed by two roles** → whoever announced first in `ACTIVITY.md` goes first,
  the other waits.

## 8. Background workers (subagents)

**Boundary: a subagent is not a role session.** A subagent has its own context window, starts
from nothing (it doesn't see the calling session's history), doesn't survive the call that
spawned it, has no transcript kept, and isn't listed by `claude agents`. Concretely:

- **Fits**: a bounded, checkable task with a written result — an audit, a measurement, a search,
  a verification pass. The task must be self-contained; a subagent won't "catch up on context."
- **Does not fit**: holding a zone. A zone needs memory across sessions and accountability for
  state; a subagent has neither. A role is held by a session, not by a worker you dispatched.
- Any session can launch subagents. If one touches the repository, write **one** entry in
  `HANDOFFS.md`: the task as given / what came back (branch and commit, not "did it") / verdict /
  anything the task spec itself got wrong. A finding that lives only in a chat with a subagent is
  a lost finding — its home is code, a commit, or a written record.
- **A file that names a subagent "as" a role does not create a role session** — the harness makes
  any file placed in an agent-definitions directory callable as a subagent by any session,
  regardless of what it's named or what it's meant to represent. If you want per-role launch
  ergonomics, that belongs in `LAUNCH_PROMPTS.md` as a prompt template a human or session reads
  and acts on — not as a subagent definition standing in for a zone-holding role.

## 9. Communication style with the owner

Adjust to your project — if the owner isn't expert in the domain some roles work in, prefer:
professional register (name methods and concepts precisely), teach rather than just report
(define a term on first use, give intuition before formalism), and layer the answer (the gist in
two sentences, then the precise version, then the detail) — rather than dumping the full
derivation up front.

## 10. Orchestrator and paradigm changes

The orchestrator role is the controller: reconciles roles, merges branches, arbitrates
conflicts, keeps `coordination/**` and `CLAUDE.md` current.

Proposals about the coordination paradigm itself → `ACTIVITY.md` tagged `[proposal]`; the
orchestrator consolidates.

**A standing orchestrator duty:** watch for cancelled mechanisms growing back. A new rule that
answers "who's working right now" is redundant by construction — git answers it, and on a
single machine the tool's own session list answers it sooner.
