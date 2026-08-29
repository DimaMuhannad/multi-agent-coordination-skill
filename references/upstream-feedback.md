# Upstream feedback — returning scaffold-level findings, not just fixing them locally

A project using this scaffold will eventually hit a real defect in the scaffold itself — not a
project-specific customization gone wrong, but a bug in a template, hook, or tool this skill
ships. Left alone, the natural path is a quiet local patch: fast, unblocks the project, and
easy to forget about. Two things go wrong from there. Either the patch gets silently lost the
next time someone re-copies the scaffold's templates into the project, or it never leaves the
project at all, so every other project built from this scaffold keeps re-discovering and
re-fixing the same bug independently. This file is the pathway that avoids both.

## 1. Is this actually a scaffold bug?

Only worth reporting upstream if it would reproduce in a different project built from the same
scaffold — not something specific to this project's own zone content, role names, or domain data.
A parser that mishandles a status word regardless of project, a hook that measures file size
wrong on a given OS, a template whose placeholder the instantiation steps don't actually fill in
— these are scaffold bugs. A role's zone boundary being wrong for *this* project's directory
layout is not; that's a local configuration fact, not a defect in the scaffold.

## 2. Mark the local patch while it's still local

Until a fix is accepted upstream, the project is carrying a real, live divergence from the
scaffold — make that visible in the code itself, not just in memory or a chat transcript. Put a
one-line marker next to the patch:

```
<!-- LOCAL PATCH 2026-08-29: works around <short bug description>; reported upstream as
     <repo>#<issue-number>; remove this patch once that lands -->
```

(or the language's own comment syntax for non-Markdown files). The marker needs a date, what
it's working around, and where the upstream report lives — without the issue reference, a future
reviewer can't tell whether the patch is still needed or already superseded. This is what
`coordination/prompts/REVIEW.md`'s upstream-comparison pass (see `references/setup.md`'s
templates) greps for when reconciling local patches against upstream.

## 3. Write the report the way that has actually gotten fixes merged

This scaffold's own upstream already has one worked example of the shape that works: a bug
report with a `Summary`, a short paragraph on *why it's worth fixing rather than tolerating*
(not just that it's technically wrong), a minimal, runnable reproduction, explicit `Expected` vs.
`Actual`, a concrete suggested fix, and the environment it was observed in. That's not a
convention invented for this file — it's the format that got a real fix reviewed and merged
promptly upstream. Reuse it rather than improvising a shorter report; the reproduction step in
particular is what lets the maintainer confirm the bug without first reconstructing your project.

## 4. Test both sides before calling the fix done

A fix for a false positive that's confirmed only by no longer seeing the false positive isn't
fully tested — confirm the *true* case still fires too. For a check that's supposed to catch real
problems (a budget hook, a validator, a parser), verify both that the case which shouldn't fire
now stays silent, and that a case which should still fire still does. A fix that only silences
the check has just moved the failure mode from "too noisy" to "misses real problems," which is
worse.

## 5. Remove the local patch once upstream has it

Once the upstream fix is merged, delete the local patch and its marker entirely rather than
leaving it in "just in case" — a merged upstream fix arriving via the scaffold's own update path
makes the local one redundant, and a dead patch left in place is exactly the kind of drift
`references/rationale.md` warns about: two things describing the same fact, only one of which is
still true. If the local patch predates the marker convention above, add the marker first so its
removal is a deliberate, greppable step rather than something that has to be remembered.
