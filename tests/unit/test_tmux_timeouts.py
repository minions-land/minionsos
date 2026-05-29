"""Regression test: supervision-critical tmux subprocess calls carry a timeout.

A wedged tmux server must not be able to block a Gru watchdog thread (or the
role launcher) forever. Every ``subprocess.run`` whose argv starts with
``tmux`` in the supervision hot-path modules must pass an explicit ``timeout=``.
This guards against a future edit silently reintroducing an unbounded call.
"""

from __future__ import annotations

import ast
from pathlib import Path

from minions.paths import MINIONS_ROOT

SUPERVISION_MODULES = [
    MINIONS_ROOT / "minions" / "gru" / "loop.py",
    MINIONS_ROOT / "minions" / "lifecycle" / "role_launcher.py",
]


def _tmux_runs_without_timeout(path: Path) -> list[int]:
    """Return line numbers of `subprocess.run(["tmux", ...], ...)` lacking timeout=."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # match subprocess.run(...)
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "run"
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
        ):
            continue
        # first positional arg must be a list literal starting with "tmux"
        if not node.args:
            continue
        first = node.args[0]
        is_tmux = (
            isinstance(first, ast.List)
            and first.elts
            and isinstance(first.elts[0], ast.Constant)
            and first.elts[0].value == "tmux"
        )
        if not is_tmux:
            continue
        has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
        if not has_timeout:
            offenders.append(node.lineno)
    return offenders


def test_supervision_tmux_calls_have_timeouts():
    problems: dict[str, list[int]] = {}
    for mod in SUPERVISION_MODULES:
        offenders = _tmux_runs_without_timeout(mod)
        if offenders:
            problems[str(mod.relative_to(MINIONS_ROOT))] = offenders
    assert not problems, (
        "tmux subprocess.run calls missing timeout= (a wedged tmux server would "
        f"hang the calling thread forever): {problems}"
    )
