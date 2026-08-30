"""
dashboard.py - Interactive Streamlit Dashboard for Multi-Agent Coordination.
Visualizes and manages Roles Board, Decision Queue, Cross-Role Handoffs, Git Worktrees, and Backlog Index.
Safely mutates markdown journals preserving exact formatting and executes isolated git commits with trailers.
"""

from datetime import datetime
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, List, Optional
import streamlit as st

_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
import build_index  # noqa: E402

# Add parent directories to sys.path to allow running standalone or as package
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

try:
    from .parser import (
        parse_board,
        parse_questions,
        parse_handoffs,
        parse_index,
        parse_worktrees
    )
    from .mutator import (
        mutate_table_cell,
        mutate_handoff_status,
        append_question,
        append_handoff
    )
    from .git_service import GitService
    from .components import render_kpi_bar
    from .badges import render_status_badge, render_type_badge, render_role_badge
    from . import writes as write_gate
    from .mutator import apply_plan, plan_append_board_row
except (ImportError, ValueError):
    from parser import (
        parse_board,
        parse_questions,
        parse_handoffs,
        parse_index,
        parse_worktrees
    )
    from mutator import (
        mutate_table_cell,
        mutate_handoff_status,
        append_question,
        append_handoff
    )
    from git_service import GitService
    from components import render_kpi_bar
    from badges import render_status_badge, render_type_badge, render_role_badge
    import writes as write_gate
    from mutator import apply_plan, plan_append_board_row


def discover_coordination_dir(start_path: Optional[Path] = None) -> Path:
    """Discovers the coordination folder in the repository."""
    start = start_path or Path.cwd()
    repo_root = GitService.get_repo_root(start)
    if repo_root:
        candidate_assets = repo_root / "assets" / "coordination"
        if candidate_assets.exists() and (candidate_assets / "BOARD.md").exists():
            return candidate_assets
        candidate_coord = repo_root / "coordination"
        if candidate_coord.exists() and (candidate_coord / "BOARD.md").exists():
            return candidate_coord

    # Search local parents
    curr = (start if start.is_dir() else start.parent).resolve()
    for p in [curr] + list(curr.parents):
        if (p / "BOARD.md").exists():
            return p
        if (p / "assets" / "coordination" / "BOARD.md").exists():
            return p / "assets" / "coordination"
        if (p / "coordination" / "BOARD.md").exists():
            return p / "coordination"

    # Default fallback
    return curr


def rebuild_index_file(coord_dir: Path) -> Path:
    """Rebuild INDEX.md by calling the core generator.

    This used to be a second, divergent implementation: it emitted
    `| # | Status | Role | Line | Summary |` where build_index.py emits `... | To | ...`,
    and it had a template concept build_index.py lacked. Same filename, two formats, two
    sets of counts, depending on which tool last wrote it.
    """
    index_file = coord_dir / "INDEX.md"
    text, _q_count, _h_count = build_index.build_index_text(str(coord_dir))
    with open(index_file, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return index_file


def handle_mutation_and_commit(
    success: bool,
    msg: str,
    target_file: Path,
    commit_msg: str,
    trailers: Dict[str, str],
    author_role: str,
    enable_git: bool,
    repo_root: Optional[Path]
) -> None:
    """Report the outcome of an applied mutation, optionally committing it.

    Kept for callers that already applied a change. New code should go through
    request_write()/render_pending_write() so the operator sees a diff first.
    """
    if not success:
        st.error(f"Mutation failed: {msg}")
        return

    st.success(msg)

    if enable_git and repo_root:
        res = GitService.auto_commit_file(
            file_path=target_file,
            message=commit_msg,
            trailers=trailers,
            author_role=author_role,
            repo_root=repo_root
        )
        if res["status"] == "success":
            st.toast(f"Committed `{res['sha']}`: {commit_msg}", icon="✅")
            hint = write_gate.revert_hint(res.get("sha"))
            if hint:
                # No undo: git already holds the history, so the recovery path is git's.
                st.caption(f"To undo: `{hint}`")
        elif res["status"] == "noop":
            st.toast("No file diff detected for git commit.", icon="ℹ️")
        else:
            st.warning(f"Commit warning: {res.get('message') or res.get('stderr')}")

    st.rerun()


def request_write(key: str, plan, commit_msg: str, trailers: Dict[str, str],
                  author_role: str, diagnostics=None) -> None:
    """Stage a planned write for confirmation. Writes nothing.

    Nothing reaches disk between here and the operator pressing Apply, and the diff shown
    is rendered from this same plan - so what is confirmed is exactly what is written.
    """
    decision = write_gate.gate(getattr(plan, "ok", False), diagnostics)
    if not decision:
        st.error(decision.reason)
        if getattr(plan, "ok", False) is False and getattr(plan, "message", ""):
            st.caption(plan.message)
        return

    st.session_state["pending_write"] = write_gate.PendingWrite(
        key=key, plan=plan, commit_message=commit_msg,
        trailers=trailers, author_role=author_role,
    )


def render_pending_write(enable_git: bool, repo_root: Optional[Path]) -> None:
    """Show the staged diff and require an explicit confirmation before writing."""
    pending = st.session_state.get("pending_write")
    if pending is None:
        return

    with st.container(border=True):
        st.subheader("Confirm this change")
        # Naming the destination is the mitigation the reporter actually needed: a new
        # question used to land in whatever table came last in the file.
        st.caption(pending.description or "(target not described)")
        diff = pending.diff
        if diff:
            st.code(diff, language="diff")
        else:
            st.info("No textual change.")

        commit_this = st.toggle(
            "Also commit this change to git",
            value=enable_git,
            key="confirm_commit_toggle",
            help="Shown here so the git consequence is visible at the moment of decision.",
        )
        reviewed = st.checkbox("I have reviewed the diff above", key="confirm_reviewed")

        col_apply, col_cancel = st.columns(2)
        with col_apply:
            if st.button("Apply", type="primary", disabled=not reviewed,
                         use_container_width=True, key="confirm_apply"):
                ok, msg = apply_plan(pending.plan)
                st.session_state.pop("pending_write", None)
                handle_mutation_and_commit(
                    ok, msg, pending.plan.path, pending.commit_message,
                    pending.trailers, pending.author_role,
                    commit_this, repo_root,
                )
        with col_cancel:
            if st.button("Cancel", use_container_width=True, key="confirm_cancel"):
                st.session_state.pop("pending_write", None)
                st.rerun()


def render_diagnostics(diagnostics) -> None:
    """Surface everything the parsers could not interpret, above the numbers.

    A count that silently excludes rows the tool failed to read is worse than an error,
    because it gets believed.
    """
    if not diagnostics:
        return
    st.error(
        f"⚠ {len(diagnostics)} item(s) in the coordination files could not be interpreted. "
        "They are shown as unclassified, NOT as resolved. Writing to an affected file is "
        "disabled until it is fixed."
    )
    with st.expander(f"Schema diagnostics ({len(diagnostics)})"):
        for item in diagnostics:
            st.text(str(item))


def main():
    st.set_page_config(
        page_title="Multi-Agent Coordination Dashboard",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # 1. Settings, in the MAIN column.
    #
    # These lived in st.sidebar, which does not render at all under some Streamlit versions
    # (verified by the issue reporter on 1.62). An unreachable control is strictly worse
    # than a visible one, and the git auto-commit toggle was both hidden AND defaulted to
    # on. Nothing here is navigation, so nothing is lost by moving it.
    st.title("🤖 Multi-Agent Coordination")

    writes_on = write_gate.writes_enabled()
    if not writes_on:
        st.caption("🔒 " + write_gate.READ_ONLY_NOTICE)

    default_coord_dir = discover_coordination_dir()
    with st.expander("⚙️ Settings", expanded=False):
        coord_path_str = st.text_input(
            "📁 Coordination directory",
            value=str(default_coord_dir),
            help="Path containing BOARD.md, QUESTIONS.md, HANDOFFS.md",
        )
        coord_dir = Path(coord_path_str).resolve()
        repo_root = GitService.get_repo_root(coord_dir)

        board_preview = parse_board(coord_dir / "BOARD.md")
        # Roles come from BOARD.md. The previous hardcoded list was the source project's
        # roster shipped inside a template, and a role added through this dashboard never
        # appeared in it.
        role_options = write_gate.roles_from_board(board_preview) or ["ORCH"]
        author_role = st.selectbox(
            "🎭 Committer role", options=role_options, index=0,
            help="The role recorded in the commit trailers (CHARTER.md §4)",
        )

        enable_git = st.toggle(
            "⚡ Commit changes to git",
            value=False,
            disabled=not writes_on,
            help="Off by default. Each write also asks again at confirmation time.",
        )

        if repo_root:
            st.success(f"Git root: `{repo_root.name}`")
        else:
            st.warning("No git repository detected")

        if st.button("🔄 Refresh data"):
            st.rerun()

    # 2. File Paths
    board_file = coord_dir / "BOARD.md"
    questions_file = coord_dir / "QUESTIONS.md"
    handoffs_file = coord_dir / "HANDOFFS.md"
    index_file = coord_dir / "INDEX.md"

    # 3. Parse Active Coordination State
    diagnostics: List[Any] = []
    board_data = parse_board(board_file, diagnostics=diagnostics)
    questions_data = parse_questions(questions_file, diagnostics=diagnostics)
    handoffs_data = parse_handoffs(handoffs_file, diagnostics=diagnostics)
    render_diagnostics(diagnostics)
    render_pending_write(enable_git, repo_root)
    index_data = parse_index(index_file)
    worktrees_data = parse_worktrees(repo_root)

    # 4. Top Header & KPI Bar
    st.title("🎛️ Multi-Agent Coordination Dashboard")
    st.caption(f"Active Workspace: `{coord_dir}`")
    render_kpi_bar(board_data, questions_data, handoffs_data, worktrees_data)
    st.markdown("---")

    # 5. Main 5 Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 Roles Board",
        "❓ Decision Queue",
        "🤝 Handoffs",
        "🌳 Git Worktrees",
        "📑 Backlog Index"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Roles Board
    # -------------------------------------------------------------------------
    with tab1:
        st.subheader("📋 Roles Board (`BOARD.md`)")
        st.write("Live operational status for each agent role in the project.")

        if not board_data:
            st.info(f"No active roles found in `{board_file.name}`.")
        else:
            # Display Roles Cards / Table
            cols_per_row = 3
            for i in range(0, len(board_data), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, role_info in enumerate(board_data[i : i + cols_per_row]):
                    with cols[j]:
                        with st.container(border=True):
                            badge = render_role_badge(role_info["status"])
                            st.markdown(f"### `{role_info['role']}` {badge}")
                            st.caption(f"📅 Last updated: **{role_info['date'] or 'N/A'}**")
                            st.markdown(f"**Summary:** {role_info['summary'] or '—'}")

        st.markdown("---")
        with st.expander("✏️ Update Role Status & Summary", expanded=False):
            # Roles come from BOARD.md. The old fallback listed the source project's own
            # roles, so a project with an empty board was offered someone else's roster.
            existing_roles = write_gate.roles_from_board(board_data) or ["ORCH"]
            target_role = st.selectbox("Select Role to Update", options=existing_roles)
            new_role_status = st.selectbox("Status", options=["active", "idle", "stale", "blocked"], index=0)
            today_str = datetime.now().strftime("%Y-%m-%d")
            status_date_input = st.text_input("Status Date", value=today_str)
            new_summary = st.text_input("One-line Summary", placeholder="What this role is doing right now...")

            if st.button("💾 Update Role & Commit", key="btn_update_role", disabled=not writes_on):
                combined_status = f"{new_role_status} ({status_date_input})"
                ok, msg = mutate_table_cell(
                    file_path=board_file,
                    key_col="Role",
                    key_val=target_role,
                    target_col="Status (date)",
                    new_val=combined_status
                )
                if ok and new_summary.strip():
                    # The result of this second write used to be discarded, so a summary
                    # column that was renamed or missing failed silently while the UI
                    # reported the first write's success.
                    ok_summary, msg_summary = mutate_table_cell(
                        file_path=board_file,
                        key_col="Role",
                        key_val=target_role,
                        target_col="One-line summary",
                        new_val=new_summary.strip()
                    )
                    if not ok_summary:
                        ok, msg = False, f"status updated but summary failed: {msg_summary}"

                commit_subject = f"[{target_role}] update status: {new_role_status}"
                trailers = {
                    "Session": "dashboard",
                    "Reason": f"Updated role status in BOARD.md via dashboard"
                }
                handle_mutation_and_commit(
                    success=ok,
                    msg=msg,
                    target_file=board_file,
                    commit_msg=commit_subject,
                    trailers=trailers,
                    author_role=author_role,
                    enable_git=enable_git,
                    repo_root=repo_root
                )

        with st.expander("➕ Register New Role in BOARD.md", expanded=False):
            new_role_id = st.text_input("New Role ID (e.g. documentation, devops)")
            new_role_initial_status = st.selectbox("Initial Status", options=["active", "idle"], key="new_role_status")
            new_role_summary = st.text_input("Initial Summary", key="new_role_summary")
            if st.button("➕ Add Role to Board", key="btn_add_role", disabled=not writes_on):
                if new_role_id.strip():
                    # Through the mutator, which inserts INSIDE the board table. The
                    # previous raw append put the row at end-of-file - after the prose that
                    # follows the table in BOARD.md - where the parser's header tracking
                    # resets and the row is dropped. Write and commit both succeeded and
                    # the role never appeared.
                    plan = plan_append_board_row(
                        board_file,
                        role=new_role_id.strip(),
                        status=new_role_initial_status,
                        summary=new_role_summary.strip() or "Initial registration",
                    )
                    request_write(
                        key="add_role",
                        plan=plan,
                        commit_msg=f"[{author_role}] Register new role {new_role_id.strip()}",
                        trailers={"Session": "dashboard", "Reason": "Registered role in BOARD.md"},
                        author_role=author_role,
                        diagnostics=diagnostics,
                    )
                    st.rerun()

    # -------------------------------------------------------------------------
    # TAB 2: Decision Queue / Questions
    # -------------------------------------------------------------------------
    with tab2:
        st.subheader("❓ Decision Queue & Owner Decisions (`QUESTIONS.md`)")
        st.write("Append-only durable decision record across all agent sessions.")

        # Filters
        f_col1, f_col2, f_col3 = st.columns([1, 1, 2])
        with f_col1:
            status_filter = st.selectbox("Filter Status", options=["All", "Open / In Progress", "Resolved / Closed"])
        with f_col2:
            type_filter = st.selectbox("Filter Type", options=["All", "Blocking Only", "Non-blocking Only"])
        with f_col3:
            search_query = st.text_input("🔍 Search Questions", placeholder="Keywords in question or answer...")

        # Apply filtering
        filtered_q = []
        for q in questions_data:
            if status_filter == "Open / In Progress" and not q.get("is_open"):
                continue
            if status_filter == "Resolved / Closed" and q.get("is_open"):
                continue
            if type_filter == "Blocking Only" and not q.get("is_blocking"):
                continue
            if type_filter == "Non-blocking Only" and q.get("is_blocking"):
                continue
            if search_query:
                sq = search_query.lower()
                if sq not in q["question"].lower() and sq not in q["answer"].lower() and sq not in q["id"].lower():
                    continue
            filtered_q.append(q)

        st.caption(f"Showing **{len(filtered_q)}** of **{len(questions_data)}** questions")

        if not filtered_q:
            st.info("No questions matching the selected filter.")
        else:
            for q in filtered_q:
                with st.container(border=True):
                    q_header_col1, q_header_col2, q_header_col3 = st.columns([2, 1, 1])
                    with q_header_col1:
                        st.markdown(f"#### `{q['id']}`: {q['question']}")
                    with q_header_col2:
                        st.markdown(f"{render_type_badge(q['type'])}")
                    with q_header_col3:
                        st.markdown(f"{render_status_badge(q['status'])}")

                    if q["answer"] and q["answer"] != "—":
                        st.markdown(f"**Owner's Answer:** `{q['answer']}`")

                    # If open, provide resolution form
                    if q.get("is_open"):
                        with st.expander(f"💡 Resolve `{q['id']}`", expanded=False):
                            ans_text = st.text_area(f"Owner's Answer for {q['id']}", value=q["answer"] if q["answer"] != "—" else "")
                            q_new_status = st.selectbox(
                                f"Update Status for {q['id']}",
                                options=["resolved", "closed", "open"],
                                index=0
                            )
                            if st.button(f"💾 Record Decision for {q['id']}", key=f"btn_res_{q['id']}", disabled=not writes_on):
                                ok1, m1 = mutate_table_cell(
                                    file_path=questions_file,
                                    key_col="#",
                                    key_val=q["id"],
                                    target_col="Status",
                                    new_val=q_new_status
                                )
                                if ok1 and ans_text.strip():
                                    # Result checked: a renamed or missing answer column
                                    # used to fail silently while the UI reported success
                                    # from the status write above.
                                    ok2, m2 = mutate_table_cell(
                                        file_path=questions_file,
                                        key_col="#",
                                        key_val=q["id"],
                                        target_col="Owner's answer",
                                        new_val=ans_text.strip()
                                    )
                                    if not ok2:
                                        ok1, m1 = False, f"status updated but answer failed: {m2}"
                                commit_subject = f"[{author_role}] Resolve {q['id']}: {q['question'][:50]}"
                                trailers = {
                                    "Session": "dashboard",
                                    "Reason": f"Recorded owner decision for {q['id']}"
                                }
                                handle_mutation_and_commit(
                                    success=ok1,
                                    msg=m1,
                                    target_file=questions_file,
                                    commit_msg=commit_subject,
                                    trailers=trailers,
                                    author_role=author_role,
                                    enable_git=enable_git,
                                    repo_root=repo_root
                                )

        st.markdown("---")
        with st.expander("➕ Post New Question to QUESTIONS.md", expanded=False):
            new_q_text = st.text_area("Question Text", placeholder="What decision is needed from the owner/orchestrator?")
            new_q_type = st.radio("Question Type", options=["blocking", "non-blocking"], horizontal=True)
            new_q_default = st.text_input("Default / Recommendation (if non-blocking)", placeholder="e.g. Default to Canvas2D")

            if st.button("➕ Submit Question & Commit", key="btn_post_q", disabled=not writes_on):
                if new_q_text.strip():
                    ans_initial = f"Took default: {new_q_default.strip()}" if (new_q_type == "non-blocking" and new_q_default.strip()) else "—"
                    ok, msg = append_question(
                        file_path=questions_file,
                        question=new_q_text.strip(),
                        q_type=new_q_type,
                        status="open",
                        answer=ans_initial
                    )
                    commit_subject = f"[{author_role}] Post question: {new_q_text[:50]}"
                    trailers = {
                        "Session": "dashboard",
                        "Reason": "Submitted new coordination question via dashboard"
                    }
                    handle_mutation_and_commit(
                        success=ok,
                        msg=msg,
                        target_file=questions_file,
                        commit_msg=commit_subject,
                        trailers=trailers,
                        author_role=author_role,
                        enable_git=enable_git,
                        repo_root=repo_root
                    )

    # -------------------------------------------------------------------------
    # TAB 3: Handoffs
    # -------------------------------------------------------------------------
    with tab3:
        st.subheader("🤝 Cross-Role Handoffs (`HANDOFFS.md`)")
        st.write("Manage cross-layer delegation requests across agent zone boundaries.")

        active_handoffs = [h for h in handoffs_data if h.get("is_open") and not h.get("is_template")]
        completed_handoffs = [h for h in handoffs_data if not h.get("is_open") and not h.get("is_template")]

        h_col1, h_col2 = st.columns(2)

        with h_col1:
            st.markdown(f"### 🚀 Active Requests ({len(active_handoffs)})")
            if not active_handoffs:
                st.info("No active handoff requests.")
            for h in active_handoffs:
                with st.container(border=True):
                    st.markdown(f"**[{h['date']}]** FROM `{h['from_role']}` ➔ TO `{h['to_role']}`")
                    st.markdown(f"#### {h['title']}")
                    st.markdown(f"**Status:** {render_status_badge(h['status'])}")
                    st.markdown(f"- **What:** {h['what']}")
                    st.markdown(f"- **Context:** {h['context']}")
                    st.markdown(f"- **Done when:** {h['done_when']}")

                    act_col1, act_col2 = st.columns(2)
                    with act_col1:
                        if h["status"] == "open":
                            if st.button("🚀 Take Handoff", key=f"btn_take_{h['start_line']}", disabled=not writes_on):
                                ok, msg = mutate_handoff_status(
                                    file_path=handoffs_file,
                                    date=h["date"],
                                    title=h["title"],
                                    new_status="taken"
                                )
                                commit_subject = f"[{author_role}] Take handoff: {h['title'][:50]}"
                                trailers = {"Session": "dashboard", "Reason": "Marked handoff taken"}
                                handle_mutation_and_commit(
                                    success=ok,
                                    msg=msg,
                                    target_file=handoffs_file,
                                    commit_msg=commit_subject,
                                    trailers=trailers,
                                    author_role=author_role,
                                    enable_git=enable_git,
                                    repo_root=repo_root
                                )
                    with act_col2:
                        if st.button("✅ Mark Done", key=f"btn_done_{h['start_line']}", disabled=not writes_on):
                            ok, msg = mutate_handoff_status(
                                file_path=handoffs_file,
                                date=h["date"],
                                title=h["title"],
                                new_status="done"
                            )
                            commit_subject = f"[{author_role}] Done handoff: {h['title'][:50]}"
                            trailers = {"Session": "dashboard", "Reason": "Marked handoff completed"}
                            handle_mutation_and_commit(
                                success=ok,
                                msg=msg,
                                target_file=handoffs_file,
                                commit_msg=commit_subject,
                                trailers=trailers,
                                author_role=author_role,
                                enable_git=enable_git,
                                repo_root=repo_root
                            )

        with h_col2:
            st.markdown(f"### ✅ Completed Handoffs ({len(completed_handoffs)})")
            if not completed_handoffs:
                st.info("No completed handoffs yet.")
            for h in completed_handoffs:
                with st.container(border=True):
                    st.markdown(f"**[{h['date']}]** FROM `{h['from_role']}` ➔ TO `{h['to_role']}`")
                    st.markdown(f"#### {h['title']}")
                    st.markdown(f"**Status:** {render_status_badge(h['status'])}")
                    st.caption(f"Done criterion: {h['done_when']}")

                    if st.button("↩️ Reopen", key=f"btn_reopen_{h['start_line']}", disabled=not writes_on):
                        ok, msg = mutate_handoff_status(
                            file_path=handoffs_file,
                            date=h["date"],
                            title=h["title"],
                            new_status="open"
                        )
                        commit_subject = f"[{author_role}] Reopen handoff: {h['title'][:50]}"
                        trailers = {"Session": "dashboard", "Reason": "Reopened handoff"}
                        handle_mutation_and_commit(
                            success=ok,
                            msg=msg,
                            target_file=handoffs_file,
                            commit_msg=commit_subject,
                            trailers=trailers,
                            author_role=author_role,
                            enable_git=enable_git,
                            repo_root=repo_root
                        )

        st.markdown("---")
        with st.expander("➕ Create New Cross-Role Handoff", expanded=False):
            h_fcol1, h_fcol2 = st.columns(2)
            with h_fcol1:
                new_h_from = st.text_input("From Role", value=author_role)
            with h_fcol2:
                new_h_to = st.text_input("To Role", placeholder="e.g. frontend, physics, qa_tester")
            new_h_title = st.text_input("Handoff Title", placeholder="Short descriptive title of the change needed")
            new_h_what = st.text_area("What", placeholder="Describe the specific change needed in the other role's zone")
            new_h_context = st.text_area("Context", placeholder="Why this role can't do it (zone boundary), relevant links")
            new_h_done_when = st.text_input("Done When", placeholder="Concrete, checkable criterion (e.g. test passes)")

            if st.button("➕ Submit Handoff & Commit", key="btn_create_handoff", disabled=not writes_on):
                if new_h_title.strip() and new_h_to.strip():
                    ok, msg = append_handoff(
                        file_path=handoffs_file,
                        from_role=new_h_from.strip(),
                        to_role=new_h_to.strip(),
                        title=new_h_title.strip(),
                        what=new_h_what.strip(),
                        context=new_h_context.strip(),
                        done_when=new_h_done_when.strip(),
                        status="open"
                    )
                    commit_subject = f"[{new_h_from.strip()}] Handoff to {new_h_to.strip()}: {new_h_title.strip()[:50]}"
                    trailers = {
                        "Session": "dashboard",
                        "Reason": f"Delegated task to {new_h_to.strip()}"
                    }
                    handle_mutation_and_commit(
                        success=ok,
                        msg=msg,
                        target_file=handoffs_file,
                        commit_msg=commit_subject,
                        trailers=trailers,
                        author_role=author_role,
                        enable_git=enable_git,
                        repo_root=repo_root
                    )

    # -------------------------------------------------------------------------
    # TAB 4: Git Worktrees
    # -------------------------------------------------------------------------
    with tab4:
        st.subheader("🌳 Active Git Worktrees (`git worktree list`)")
        st.write("Isolated per-role git working trees enabling concurrent agent execution without file contention.")

        if not worktrees_data:
            st.info("No active git worktrees found.")
        else:
            for wt in worktrees_data:
                with st.container(border=True):
                    wt_c1, wt_c2, wt_c3 = st.columns([3, 2, 1])
                    with wt_c1:
                        st.markdown(f"**Path:** `{wt['path']}`")
                        if wt.get("is_main"):
                            st.caption("⭐️ **Primary Repository Root**")
                    with wt_c2:
                        # .get(): a bare worktree's porcelain block carries no branch or
                        # HEAD line, and subscripting raised KeyError on it.
                        st.markdown(f"**Branch:** `{wt.get('branch') or '(detached)'}`")
                        head = wt.get("head") or ""
                        st.caption(f"HEAD: `{head[:7] or '-'}`")
                    with wt_c3:
                        if wt.get("role"):
                            st.markdown(f"Role: `{wt['role']}`")
                        if wt.get("prunable"):
                            st.warning("Prunable")

        st.markdown("---")
        with st.expander("🚀 Launch Worktree for Agent Role", expanded=False):
            wt_role_input = st.text_input("Role to launch (e.g. qa_tester, physics, frontend)")
            if st.button("🚀 Create Worktree", key="btn_create_wt", disabled=not writes_on):
                if wt_role_input.strip():
                    res = GitService.create_worktree(wt_role_input.strip(), repo_root=repo_root)
                    if res["status"] == "success":
                        st.success(f"Worktree created at `{res['path']}` for branch `{res['branch']}`")
                        # Show the resolved path git actually created, not a guess. The
                        # previous hint hardcoded assets/.worktrees/, which only exists in
                        # this skill repo's own layout.
                        st.info(f"Terminal command: `cd {res['path']} && claude`")
                    elif res["status"] == "noop":
                        st.info(res["message"])
                    else:
                        st.error(res["message"])
                    st.rerun()

    # -------------------------------------------------------------------------
    # TAB 5: Backlog & Index
    # -------------------------------------------------------------------------
    with tab5:
        st.subheader("📑 Backlog & Index (`INDEX.md`)")
        st.write("Aggregated index of open and closed items across all journals.")

        i_col1, i_col2 = st.columns([3, 1])
        with i_col2:
            if st.button("⚡ Rebuild INDEX.md", key="btn_rebuild_index", disabled=not writes_on, use_container_width=True):
                rebuilt_file = rebuild_index_file(coord_dir)
                commit_subject = f"[{author_role}] Rebuild INDEX.md"
                trailers = {"Session": "dashboard", "Reason": "Rebuilt backlog index"}
                handle_mutation_and_commit(
                    success=True,
                    msg=f"Rebuilt {rebuilt_file.name}",
                    target_file=rebuilt_file,
                    commit_msg=commit_subject,
                    trailers=trailers,
                    author_role=author_role,
                    enable_git=enable_git,
                    repo_root=repo_root
                )

        with i_col1:
            if index_file.exists():
                with open(index_file, "r", encoding="utf-8") as f:
                    index_content = f.read()
                st.markdown(index_content)
            else:
                st.info("INDEX.md not generated yet. Click '⚡ Rebuild INDEX.md' to generate.")


if __name__ == "__main__":
    main()
