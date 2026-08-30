"""
test_dashboard_module.py - import-level checks for dashboard.py against a stub streamlit.

The UI cannot be driven headlessly here, but the things that went wrong in issue #6 are not
rendering bugs: they are a hidden control, a default, a hardcoded path and a second INDEX.md
generator. All of those are visible in the module source and in its pure helpers, so they
are checked rather than left to a manual pass.
"""

import re
import sys
import types
from pathlib import Path

import pytest

DASHBOARD_PY = Path(__file__).resolve().parent.parent / "dashboard.py"
SOURCE = DASHBOARD_PY.read_text(encoding="utf-8")


@pytest.fixture
def stub_streamlit(monkeypatch):
    """A streamlit stand-in that records nothing and tolerates any call.

    Enough to let dashboard.py import; not enough to render. Only import-time behaviour and
    module-level structure are asserted against it.
    """
    module = types.ModuleType("streamlit")

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def _any_call(*args, **kwargs):
        return _Ctx()

    module.__getattr__ = lambda name: _any_call  # type: ignore[attr-defined]
    module.session_state = {}
    module.columns = lambda spec, **kw: [_Ctx() for _ in (range(spec) if isinstance(spec, int) else spec)]
    monkeypatch.setitem(sys.modules, "streamlit", module)
    return module


def test_dashboard_imports_with_streamlit_present(stub_streamlit):
    import importlib

    spec = importlib.util.spec_from_file_location("dashboard_under_test", DASHBOARD_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert hasattr(module, "request_write")
    assert hasattr(module, "render_pending_write")
    assert hasattr(module, "render_diagnostics")


def test_the_sidebar_is_gone():
    """st.sidebar does not render under some Streamlit versions (reporter saw 1.62).

    The git auto-commit toggle lived there AND defaulted to on, so it was an unreachable
    control that was enabled by default.
    """
    code = re.sub(r"#.*", "", SOURCE)
    assert "st.sidebar" not in code


def test_git_commit_defaults_to_off():
    toggle = re.search(r'st\.toggle\(\s*"⚡ Commit changes to git",\s*value=(\w+)', SOURCE)
    assert toggle is not None, "the git toggle must exist in the main column"
    assert toggle.group(1) == "False"


def test_every_write_button_is_gated_on_the_read_only_flag():
    """The outer of two gates; request_write() checks again before staging anything."""
    write_keys = re.findall(r'key=f?"(btn_[a-z_]+)[^"]*"([^)]*)', SOURCE)
    ungated = [
        key for key, tail in write_keys
        if key not in ("btn_rebuild_index",) or "disabled" not in tail
    ]
    for key, tail in write_keys:
        if key.startswith("btn_") and "disabled=not writes_on" not in tail:
            pytest.fail(f"{key} is not gated on writes_on")
    assert write_keys, "expected to find write buttons"


def test_the_hardcoded_role_roster_is_gone():
    """The source project's roster was baked into a template."""
    for leaked in ("qa_tester", "physics"):
        assert f'"{leaked}"' not in SOURCE, f"{leaked} is another project's role"


def test_the_worktree_cd_hint_is_not_hardcoded():
    assert "cd assets/.worktrees/" not in SOURCE


def test_index_is_generated_by_the_core_tool_not_a_second_implementation():
    """Two generators wrote the same filename in different formats."""
    assert "build_index.build_index_text" in SOURCE
    assert "## QUESTIONS.md — open" not in SOURCE, (
        "dashboard.py must not render INDEX.md sections itself"
    )
