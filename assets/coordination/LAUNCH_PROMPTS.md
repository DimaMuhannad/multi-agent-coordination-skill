# LAUNCH_PROMPTS — how to start each role's session

Keep this file **short**. Its only two jobs are: (1) the launch-command table, and (2) one
universal nudge-to-start template. Resist the urge to duplicate each role's zone, task list, or
guardrails here — that content already lives in `coordination/roles/<ID>.md`, which every role
reads at cold start anyway. A prompt block per role that repeats that content is pure
duplication, and duplication drifts: the day someone updates a role's zone in `roles/<ID>.md`
and forgets this file has a stale copy, a session launched from here starts with wrong
information it has no reason to distrust. If you want richer per-role launch ergonomics later,
put them in the prompt text itself (below), not in a separate file per role — see
`CHARTER.md §8` for why a `.claude/agents/*.md` file is the wrong tool for this even though it
looks tempting (it silently turns a role into a callable subagent for every session in the
project, which conflicts with a role needing continuity/state ownership).

## Launch table

| Role | Session name | Launch |
|---|---|---|
| \<ID\> | `<id>-<specialty>` | `claude -n <id>-<specialty>` |
| ORCH | `orch` | `claude -n orch` |

## Universal start nudge

Once a session is named and running, send:

```
Start: read coordination/roles/<ID>.md, then continue the first open item there.
```

If you want the session to keep working autonomously across multiple steps rather than stopping
after one, wrap it with your tool's looping mechanism (e.g. Claude Code's `/loop`) instead of
writing a separate always-keep-going prompt variant here.

### Two things to keep OUT of the nudge

**Don't tell the session to `git clone` the project.** When the repository is already attached to
the session — the normal case for a cloud or container session started against a repo — a clone
just re-downloads what is already on disk. Measured: **+157 MB, +3.4 s**, and no information the
checkout did not already have. An explicit clone earns its place only when a from-scratch
checkout is the thing being tested (timing a cold provision, verifying container setup), not as a
default "to be safe".

**Do fetch before trusting `origin`.** If the session needs to know whether work is pushed, the
answer is `git fetch origin <branch>` on the checkout it already has — cheap, and it is the only
thing the clone was really providing. `CHARTER.md §4` has the rule and the failure it prevents:
a stale remote-tracking ref once produced a confident "53 commits at risk of being lost", which
is precisely the kind of belief that provokes a force-push against a problem that never existed.

## If your project also uses a different tool/agent (no session names, no `/loop`, etc.)

Note the genuinely different mechanics briefly rather than duplicating the whole table — e.g. "no
persistent named sessions, so paste the same cold-start nudge above at the start of each new
conversation."
