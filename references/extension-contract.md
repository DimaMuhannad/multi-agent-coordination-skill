# The extension contract

For anyone building a tool **outside** this repository that reads a project's coordination
layer — a monitoring view, an effectiveness report, a project-health console.

Such tools belong in their own repositories, not here and not in a fork. A fork exists to
converge back; an extension that consumes the layer never will. That only works if this
repository states what an extension may rely on, which is what this file does.

It is deliberately short, and it **points at code rather than restating it**. Every rule
below that has an executable definition names the module instead of paraphrasing it — a
paraphrase is a second copy, and copies desync.

---

## 1. Read at a committed revision, and say which one

```
git show <ref>:coordination/QUESTIONS.md
```

Not the working tree. **No writer in this scaffold is atomic** — every tool that writes opens
its target with `"w"` and truncates. A console polling the working tree while a session edits a
journal can read a half-written file, and a half-written table produces `no-header-row` or
`unknown-table-schema` — indistinguishable from a genuine defect in the journal. The consumer
would then report a real problem that does not exist, which is worse than reporting nothing.

Reading at a commit is race-free, needs no lock, and adds no state.

**Which ref is a separate choice, and it must be declared to whoever reads the output.** The
working tree, `HEAD`, `origin/main` (which requires a fetch first — `CHARTER.md §4`) and a PR
head give different answers to "how many blocking questions are open", and all four are
legitimate. What is not legitimate is leaving the reader to guess.

## 2. Three states, never two

Every classifier in `coordlib.schema` returns `None` for *not recognised*, and never `False`.
`False` means *understood, and it is closed*.

The obligation this places on a consumer:

> **An unrecognised row is displayed as unrecognised.** Never folded into a count, never
> rounded to zero, never collapsed to `False`.

The reason is on the record and is the incident this whole scaffold's diagnostics channel
exists to prevent: a parser that matched English status words classified a Russian `открыт` as
closed, and an operator read `Open Questions: 0` and believed it. See
`references/rationale.md`.

A consumer that cannot show a third state should show the raw word and no count at all. A
number that silently excludes what the tool failed to read is worse than an error, because it
gets believed.

## 3. Sources and projections

**Sources** — written by people and sessions, and the only files that mean anything on their
own:

`QUESTIONS.md` · `HANDOFFS.md` · `BOARD.md` · `ACTIVITY.md` · `OWNERSHIP.md`

**Projections** — generated, possibly stale, never hand-edited:

`INDEX.md` · `.github/CODEOWNERS`

A projection is a convenience, not a source. `INDEX.md` in particular carries counts, a
BLOCKING section and line numbers that are all only as fresh as the last run of
`build_index.py`; the shipped CI template has a job that fails when it has drifted, so on a
green `main` it can be trusted and otherwise it cannot.

The protocol tokens stay English in a project written in any language, because tooling parses
them. The prose around them does not.

## 4. Read a row by pointer, not by copy

- A table is recognised by its **header signature**, never by its position in the file.
  Questions need `{id, question, status}`, board `{role, status}`, ownership `{path, owner}`.
  Anything else is skipped and reported rather than guessed at.
- Header spellings resolve through an alias table; placeholder rows are skipped; a cell's
  escaped pipes are unescaped when it becomes a value.

The normative definition of all of that is **`coordlib.schema`** — `resolve_headers`,
`matches_signature`, `classify_item_status`, `classify_question_type`, `is_placeholder_text`,
and the vocabulary tuples — together with `coordlib.md_table.split_table_row` and
`unescape_pipe`.

This document does not restate the alias table, the normalisation algorithm or the placeholder
forms. Read them from the module. If you reimplement rather than import, that module is what
your implementation must agree with, and disagreeing with it silently is the failure mode this
scaffold has hit most often.

## 5. What is promised, and what is not

| Promised | May change without notice |
|---|---|
| `coordlib.schema` — vocabularies, classifiers, signatures, header resolution | `coordlib.md_table` tokenizer internals |
| `coordlib.diagnostics` — the code strings, `Diagnostic`'s five fields, `UNSAFE_TO_WRITE_CODES` | `coordlib.ownership`, `coordlib.manifest`, `coordlib.paths` |
| The on-disk shapes described in §3 and §4 | everything under `tools/dashboard/` |
| `coordination/.scaffold-version` existing, and its `format` field | the `--json` shapes of the CLI tools |

The same statement lives in each module's own docstring, because that is what travels with a
vendored copy — this file does not.

**One trap worth naming.** `format` in the stamp is published; the fact that nothing currently
branches on it is **not**. That field exists precisely so a future reader can branch on it, and
promising outsiders it never affects behaviour would make the first real bump a breaking change.

## 6. Getting `coordlib`

There is no pip package, and its absence is a decision rather than an oversight — the scaffold
is copied into projects and stays stdlib-only so adopting it adds nothing to install.

So an extension has four routes, and this contract does not pick one:

1. **Vendor a copy** of `coordination/tools/coordlib/`. Supported, and the reason the stability
   statement lives in the docstrings. Note the tests do **not** come with it: you get the code,
   not the evidence it works.
2. **A git submodule** on the project, if you want upgrades to be a visible commit.
3. **Reimplement the parse** against `coordlib.schema` as the specification. Legitimate for a
   non-Python extension, and the thing most likely to drift.
4. **Subprocess the CLI tools** and read their `--json`. Convenient, and the least stable of
   the four: those shapes are not promised (see §5), and today they are not even consistent
   with each other.

---

## What this contract deliberately does not cover

Each of these is a real gap. Each is left open on purpose, and the reason matters more than the
gap.

**Writing.** No rules here for a tool that modifies a journal. The scaffold had a writer once —
it satisfied all four of the conditions that justified it, and it was deleted because a
measurement across three installed projects found 47 journal commits and not one made through
it. Publishing a writer's contract before a writer exists would repeat that at documentation
scale. When one exists, the conditions are recorded in `docs/ru/CONCEPT.md §6.6` and
`coordlib.diagnostics.UNSAFE_TO_WRITE_CODES` is the machine-readable half of the fourth.

**A version number for the formats.** `FORMAT_VERSION` already exists and nothing reads it.
Adding a second version while the first has no consumer is duplicating an unused fact. Versioning
also needs two things this repository does not have — a deprecation policy and a channel that
tells extension authors a format moved — and inventing all three for a consumer count of zero is
the kind of thing this project refuses on principle.

**Machine-readable diagnostics, and `--json` for every tool.** Four inconsistent JSON shapes
already exist. A fifth should not be added before one real consumer says which it needs.

**Thresholds** for staleness, escalation or "gone quiet". That is state added to a project on
behalf of a tool that does not live in it. Thresholds belong to the consumer.

**Timestamps and ages** — how long a blocker has waited, when a handoff was taken. Deriving
these needs a format change to files people are actively writing, which is a doctrine decision
and not a contract clause.

## The invariant underneath all of this

> The interface is a **read-only projection over git**. The source of truth stays in the files.

What that forbids is a **second store of state** — not editing as such. A screen becomes a
competing scaffold at the moment something exists *only there*; a tool that writes into the same
markdown files, in the canonical format, has not crossed that line.

This distinction is the single most load-bearing sentence for an extension author, and until
this file existed it was stated only in `docs/ru/CONCEPT.md` — a document that itself declares
the English sources authoritative in any disagreement. It lives here now, and §6.5 there points
at this file rather than keeping a second copy.
