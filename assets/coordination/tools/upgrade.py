#!/usr/bin/env python3
"""upgrade.py - what changed upstream, what you changed, and where those overlap.

The scaffold is copied into a project and the link is severed. Fixes made upstream --
including ones for defects that corrupt files or make a journal report zero open questions
and be believed -- never reach any project already running it. This is the delivery
direction that `references/upstream-feedback.md` does not cover.

**This reports; it does not merge.** Three-way auto-merge of markdown that humans have
edited cannot be done without lying about the result, and a wrong merge of CHARTER.md is
worse than no upgrade channel at all. What a human actually needs is the short list of
places where a decision is required, and that is what this prints.

It works offline. `.scaffold-version` records the pristine hash of every installed file, so
"did you change this?" is answerable without contacting anything; `--from` points at a newer
checkout of the skill, which is on disk already because that is how the skill is used.

    python3 coordination/tools/upgrade.py --from /path/to/skill/assets
    python3 coordination/tools/upgrade.py --from /path/to/skill/assets --json
    python3 coordination/tools/upgrade.py --adopt --from /path/to/skill/assets
"""

import argparse
import json
import os
import sys
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from coordlib import manifest  # noqa: E402
from coordlib.paths import find_coordination_dir, find_repo_root  # noqa: E402

#: Categories, in the order a reader should work through them.
UNCHANGED = "unchanged"
UPSTREAM_ONLY = "upstream-only"
LOCAL_ONLY = "local-only"
BOTH = "both"
DELETED_LOCALLY = "deleted-locally"
NEW_UPSTREAM = "new-upstream"
SEED_CHANGED = "seed-changed"

#: Only these classes have a local file whose content is supposed to equal the source, so
#: only these can meaningfully be called "locally modified". Project-owned files grow by
#: design -- ACTIVITY.md is longer every day, and reporting that as drift every run is how
#: a report earns being ignored.
COMPARABLE_CLASSES = (manifest.TOOL, manifest.DOCTRINE)


def project_root_for(coordination_dir):
    """The directory the manifest's paths are relative to: the parent of coordination/."""
    return Path(coordination_dir).resolve().parent


def hash_upstream(assets_dir):
    """{installed_path: (sha256, asset_path)} for a newer scaffold checkout."""
    assets_dir = Path(assets_dir)
    upstream = {}
    for asset_path, digest in manifest.hash_tree(assets_dir).items():
        upstream[manifest.installed_path_for(asset_path)] = (digest, asset_path)
    return upstream


def compare(stamp, project_root, upstream):
    """Classify every file into exactly one category.

    Three inputs, per the plan: the pristine hash recorded at install time, the file on
    disk now, and the same file in a newer scaffold. `both` is the only category that
    requires a human, and keeping it small is the whole design goal.
    """
    project_root = Path(project_root)
    recorded = stamp.get("files", {})
    rows = []
    seen = set()

    for installed_path, entry in sorted(recorded.items()):
        seen.add(installed_path)
        file_class = entry.get("class", manifest.DOCTRINE)
        installed_baseline = entry.get("sha256")
        upstream_baseline = entry.get("upstream_sha256", installed_baseline)
        upstream_digest, asset_path = upstream.get(installed_path, (None, entry.get("source")))

        row = {
            "path": installed_path,
            "class": file_class,
            "source": asset_path,
            # Compared against the UPSTREAM baseline, never the installed one: a file the
            # installer filled in differs from its source by design, and measuring upstream
            # movement against the filled copy would report a change nobody made.
            "upstream_changed": (upstream_digest is not None
                                 and upstream_digest != upstream_baseline),
        }

        if file_class not in COMPARABLE_CLASSES:
            # The local file is meant to differ; only the upstream side is comparable.
            row["local_changed"] = None
            row["category"] = SEED_CHANGED if row["upstream_changed"] else UNCHANGED
            rows.append(row)
            continue

        local_digest = manifest.hash_file(project_root / installed_path)
        if local_digest is None:
            row["local_changed"] = None
            row["category"] = DELETED_LOCALLY
            rows.append(row)
            continue

        local_changed = local_digest != installed_baseline
        row["local_changed"] = local_changed
        if local_changed and row["upstream_changed"]:
            row["category"] = BOTH
        elif row["upstream_changed"]:
            row["category"] = UPSTREAM_ONLY
        elif local_changed:
            row["category"] = LOCAL_ONLY
        else:
            row["category"] = UNCHANGED
        rows.append(row)

    for installed_path, (digest, asset_path) in sorted(upstream.items()):
        if installed_path in seen:
            continue
        rows.append({
            "path": installed_path,
            "class": manifest.classify(installed_path),
            "source": asset_path,
            "upstream_changed": True,
            "local_changed": None,
            "category": NEW_UPSTREAM,
        })

    return rows


def group(rows):
    grouped = {}
    for row in rows:
        grouped.setdefault(row["category"], []).append(row)
    return grouped


_EXPLANATIONS = (
    (BOTH, "CHANGED ON BOTH SIDES - the only rows that need you",
     "Upstream changed these and so did you. Read both diffs and decide; nothing else here "
     "requires a judgement call."),
    (UPSTREAM_ONLY, "Safe to take - upstream changed, your copy is untouched",
     "These carry the fixes. Copy them across."),
    (NEW_UPSTREAM, "New upstream - did not exist when you installed",
     "Review and install the ones you want."),
    (DELETED_LOCALLY, "Missing locally",
     "Removed on purpose, or lost. Reinstall or confirm the removal."),
    (SEED_CHANGED, "Seed or template changed upstream",
     "Your filled-in copy is yours; compare against the new seed and port what applies."),
    (LOCAL_ONLY, "Yours alone - upstream unchanged",
     "Nothing to do. Listed so you can see what you have customised."),
)


def render(rows, stamp, upstream_ref=""):
    grouped = group(rows)
    lines = []

    installed_at = stamp.get("installed_at", "unknown")
    source = stamp.get("source_commit", "") or stamp.get("source_ref", "") or "unrecorded"
    lines.append("Scaffold drift report")
    lines.append("  installed %s from %s" % (installed_at, source))
    if upstream_ref:
        lines.append("  compared against %s" % upstream_ref)
    if stamp.get("adopted"):
        lines.append("  ! baseline was ADOPTED from files already on disk: any edits made")
        lines.append("    before adoption are invisible to this comparison")
    lines.append("")

    actionable = 0
    for category, title, explanation in _EXPLANATIONS:
        items = grouped.get(category)
        if not items:
            continue
        if category != LOCAL_ONLY:
            actionable += len(items)
        lines.append("%s (%d)" % (title, len(items)))
        lines.append("  %s" % explanation)
        for row in items:
            lines.append("    %-52s [%s]" % (row["path"], row["class"]))
        lines.append("")

    unchanged = len(grouped.get(UNCHANGED, []))
    lines.append("%d file(s) unchanged." % unchanged)
    if not actionable:
        lines.append("Nothing to do.")
    return "\n".join(lines)


def pre_existing_divergence(assets_dir, project_root):
    """Files that already differ from `assets_dir` before a baseline is frozen.

    Adoption blesses whatever is on disk, which necessarily hides every edit made before
    it. Printing this list once, at the moment of adoption, is the difference between a
    documented limitation and a silent one -- afterwards no tool can recover it.

    Only classes whose installed content is supposed to equal the source are listed;
    a filled-in template differing from its seed is the installer working, not divergence.
    """
    assets_dir = Path(assets_dir)
    project_root = Path(project_root)
    diverged = []
    for asset_path, upstream_digest in sorted(manifest.hash_tree(assets_dir).items()):
        installed = manifest.installed_path_for(asset_path)
        if manifest.classify(installed) not in COMPARABLE_CLASSES:
            continue
        local_digest = manifest.hash_file(project_root / installed)
        if local_digest is not None and local_digest != upstream_digest:
            diverged.append(installed)
    return diverged


def build_adopted(coordination_dir, assets_dir):
    """Baseline for a project installed before stamping existed.

    Hashes what is ON DISK now for the local side, so the first report reads "no drift"
    rather than flagging every local customisation as a conflict on day one.
    """
    return manifest.build_stamp(
        Path(assets_dir), project_root_for(coordination_dir), adopted=True)


def looks_like_the_skill_itself(coordination_dir):
    """True when the discovered coordination/ is this skill's own authoring copy.

    `find_coordination_dir` falls back to `<root>/assets/coordination`, so running this
    tool inside the skill repository resolves to the templates rather than to an installed
    project. Comparing the skill against itself produces a confusing empty report instead
    of an error, which is a bad first experience for whoever maintains it.
    """
    return "assets" in Path(coordination_dir).resolve().parts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from", dest="upstream", required=True,
                        help="path to a newer checkout of the skill's assets/ directory")
    parser.add_argument("--coordination-dir", help="path to coordination/ (default: discover)")
    parser.add_argument("--adopt", action="store_true",
                        help="write a baseline from the files currently on disk, for a "
                             "project installed before stamping existed")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    upstream_dir = Path(args.upstream)
    if not upstream_dir.is_dir():
        print("upgrade: --from %s is not a directory" % upstream_dir, file=sys.stderr)
        return 2

    explicit_dir = bool(args.coordination_dir)
    if explicit_dir:
        coordination = Path(args.coordination_dir).resolve()
    else:
        coordination = find_coordination_dir()
    if coordination is None or not Path(coordination).is_dir():
        print("upgrade: no coordination/ directory found", file=sys.stderr)
        return 2

    if not explicit_dir and looks_like_the_skill_itself(coordination):
        print("upgrade: %s is the skill's own template tree, not an installed project.\n"
              "         Run this inside a project that installed the scaffold, or pass\n"
              "         --coordination-dir explicitly if you really mean this directory."
              % coordination, file=sys.stderr)
        return 2

    if args.adopt:
        diverged = pre_existing_divergence(upstream_dir, project_root_for(coordination))
        payload = build_adopted(coordination, upstream_dir)
        target = manifest.write_stamp(coordination, payload)
        print("upgrade: adopted a baseline of %d file(s) into %s"
              % (len(payload["files"]), target))
        if diverged:
            print("", file=sys.stderr)
            print("These %d file(s) ALREADY differ from %s and are now frozen into the"
                  % (len(diverged), upstream_dir), file=sys.stderr)
            print("baseline as if they were pristine. This is your only chance to see them:",
                  file=sys.stderr)
            for path in diverged:
                print("    %s" % path, file=sys.stderr)
        print("         Edits made before now are indistinguishable from pristine content;")
        print("         every future report says so.")
        return 0

    stamp = manifest.read_stamp(coordination)
    if stamp is None:
        print("upgrade: no usable %s in %s.\n"
              "         This project was installed before stamping existed, or the stamp is\n"
              "         unreadable. Run with --adopt to record a baseline from what is on\n"
              "         disk now; drift becomes measurable from that point forward."
              % (manifest.STAMP_NAME, coordination), file=sys.stderr)
        return 2

    upstream = hash_upstream(upstream_dir)
    rows = compare(stamp, project_root_for(coordination), upstream)

    if args.json:
        print(json.dumps({"stamp": {k: stamp.get(k) for k in
                                    ("source_commit", "source_ref", "installed_at", "adopted")},
                          "upstream": str(upstream_dir),
                          "rows": rows}, indent=2, ensure_ascii=False))
    else:
        print(render(rows, stamp, upstream_ref=str(upstream_dir)))

    return 1 if any(row["category"] == BOTH for row in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
