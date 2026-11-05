"""Drift guards for counts, skip labels, and honesty claims in the docs."""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from eval_meta import inventory
from eval_meta.siblings import BENCH_SKIP, P1_LABEL, P1_SKIP

ROOT = Path(__file__).resolve().parents[1]

_AUTHOR_PATH = re.compile(r"/Users/|/home/[^/\s]+/|C:\\Users\\")
_BADGE = ("shields.io", "pypi.org", "img.shields", "badge/")


def _collect(extra: list[str]) -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *extra],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return [line.strip() for line in proc.stdout.splitlines() if line.startswith("tests/")]


def _problem_lines(text: str) -> list[str]:
    lines = text.splitlines()
    assert lines and lines[0].startswith("# ")
    body: list[str] = []
    started = False
    for line in lines[1:]:
        if not started:
            if line.strip():
                started = True
                body.append(line)
            continue
        if not line.strip():
            break
        body.append(line)
    return body


def test_collected_node_ids_match_inventory():
    """The tree, the marker split, and the summary checker share one inventory."""
    collected = _collect([])
    sibling = _collect(["-m", "sibling_repo"])
    offline = _collect(["-m", "not sibling_repo"])
    assert sorted(collected) == sorted(inventory.OFFLINE_NODE_IDS + inventory.SIBLING_NODE_IDS)
    assert sorted(sibling) == sorted(inventory.SIBLING_NODE_IDS)
    assert sorted(offline) == sorted(inventory.OFFLINE_NODE_IDS)
    assert inventory.COLLECTED == len(collected)
    assert inventory.SIBLING_SKIP == len(sibling)
    assert inventory.OFFLINE_PASS == len(offline)
    assert set(sibling).isdisjoint(offline)
    inventory.check_pytest_summary(
        f"{inventory.OFFLINE_PASS} passed, {inventory.SIBLING_SKIP} skipped in 0.01s"
    )
    with pytest.raises(SystemExit):
        inventory.check_pytest_summary(f"{inventory.COLLECTED} passed in 0.01s")


def test_readme_states_problem_counts_and_split():
    """Problem statement stays short, and skips are not written up as passes."""
    readme = (ROOT / "README.md").read_text()
    problem = _problem_lines(readme)
    assert 1 <= len(problem) <= 3
    assert "In-repo" in readme
    assert "Sibling-repo" in readme
    assert inventory.CLEAN_CLONE_SUMMARY in readme
    assert P1_LABEL in readme
    assert "mmlu,gsm8k,humaneval,mt_bench" in readme
    assert "not a pass" in readme
    assert "not coverage" in readme
    for banned in ("59 passed", "全绿", "全部实现并测试通过", "7 模块全 PASS", "全部测试（59"):
        assert banned not in readme

    modes = (ROOT / "FAILURE_MODES.md").read_text()
    for required in (
        "tau_below_floor",
        "caller_supplied_calibration",
        "preference_leakage",
        "scripted_demo",
        "is_self_family",
        "SCRIPTED",
    ):
        assert required in modes
    assert "not a judge certificate" in modes.lower() or "not a judge pass" in modes.lower()


def test_sibling_tests_skip_without_absolute_paths(tmp_path):
    """With an empty sibling root, the ten dependent tests skip and name relative labels."""
    env = os.environ.copy()
    env["EVAL_META_SIBLING_ROOT"] = str(tmp_path)
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "tests/test_integration_p1.py",
            "tests/test_integration_benchmarks.py",
            "-q", "-rs", "--tb=no",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"{inventory.SIBLING_SKIP} skipped" in proc.stdout
    assert "passed" not in proc.stdout
    assert P1_SKIP in proc.stdout
    assert BENCH_SKIP in proc.stdout
    assert _AUTHOR_PATH.search(proc.stdout) is None
    assert _AUTHOR_PATH.search(proc.stderr) is None


def test_tree_has_no_badges_pypi_or_author_paths():
    """No install badge, no PyPI URL, no absolute home path of an author."""
    roots = [ROOT / "README.md", ROOT / "ARCHITECTURE.md", ROOT / "FAILURE_MODES.md",
             ROOT / "pyproject.toml", ROOT / "eval_meta", ROOT / "tests",
             ROOT / "fixtures", ROOT / ".github"]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(p for p in root.rglob("*") if p.is_file())
    offenders: list[str] = []
    for path in files:
        if path.name == "test_inventory.py":
            # This file names the needles it searches for.
            continue
        if path.suffix in {".pyc"} or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in _BADGE:
            if needle in text:
                offenders.append(f"{path}: {needle}")
        if _AUTHOR_PATH.search(text):
            offenders.append(f"{path}: author path")
    assert offenders == []
