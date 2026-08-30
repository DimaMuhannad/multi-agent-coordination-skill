# Periodic Review

Run this prompt on an infrequent, deliberate schedule — not automated, not on every session.
It exists to catch the kind of staleness nobody's job is otherwise to notice: a scaffold that was
installed once and never checked against what changed since. Optional; only worth having once the
project has been running long enough that "is this still current" is a real question. See
`references/rationale.md`'s closing section on why undocumented rules decay — this prompt is the
mechanical check that keeps the five items below from silently rotting the same way.

Whoever runs this (`ORCH`, or the owner) works through all five items in one sitting and records
the result — **every** item, including "checked, no changes" — as one dated entry in
`ACTIVITY.md`. A missing entry for an item is indistinguishable from "never reviewed"; write it
down even when nothing changed, or the next review can't tell the difference between "still true"
and "nobody looked."

This prompt only produces a written record and, where relevant, entries in `QUESTIONS.md` for the
owner to decide on. It does not itself update anything — a review that quietly applies its own
findings removes the human decision point this scaffold otherwise insists on everywhere else
(see `references/rationale.md`).

## 1. Upstream scaffold comparison and local patch reconciliation

Search the project for `LOCAL PATCH` markers (the format `references/upstream-feedback.md`
defines). For each one found: is the linked upstream issue/PR merged yet? If so, remove the patch
and its marker now — a merged fix left in place is exactly the kind of drift
`references/rationale.md` warns about. If not, does the marker still accurately describe what
it's working around? If the project's copy of this scaffold predates a since-added scaffold
feature that would replace something built locally, note it as a candidate to adopt.

## 2. New agent-system capabilities

Check `references/agent-tooling.md` against what the agentic system actually running roles'
sessions currently supports. Has a capability been added or changed since the file was last
touched? Has a role been reaching for something not covered there that's become common enough to
document? Update the file directly if the answer is a small factual correction; log a
`QUESTIONS.md` entry if it's a real behavior change worth the owner weighing in on first.

## 3. Multi-agent development practices and thematic resources

Freeform: has anything worth knowing changed in how multi-role/multi-session agentic development
is generally done — practices, write-ups, tools other projects in this space have converged on?
Not a mandate to chase every trend; a "checked, nothing worth adopting" verdict is a legitimate
and expected outcome most cycles.

## 4. Relevant GitHub tooling — strict selection only

Don't add a GitHub-side tool or integration on the strength of "it might help." Apply the same bar
`references/git-github-rails.md` already sets for that whole optional layer: only worth adopting
once it solves a problem this project has *actually hit*, not a hypothetical one, and only if it
doesn't reintroduce something that file explicitly warns against (e.g. moving `QUESTIONS.md` /
`HANDOFFS.md` onto GitHub Issues). Most cycles, the right verdict here is also "checked, nothing
adopted."

## 5. Feedback suitable for upstream contribution

Cross-check against item 1: any `LOCAL PATCH` marker whose issue field is still empty is a fix
that exists but hasn't been reported. Work through `references/upstream-feedback.md`'s process for
each one found, rather than leaving it as a standing local divergence indefinitely.
