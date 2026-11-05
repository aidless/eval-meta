"""Optional sibling checkouts.

Skip messages name the missing files with a repo-relative label.
They never include the resolved path, so a local username or home
directory is not written into pytest output.
"""

from __future__ import annotations

import os
from pathlib import Path

P1_LABEL = "agi-research-program/p1/claims.json+recompute_receipts.json"
BENCH_LABEL = (
    "llm-agent-projects/20-llm-eval-benchmark/data/"
    "{mmlu,gsm8k,humaneval,mt_bench}_sample.json"
)
P1_SKIP = f"sibling-repo data not in tree: {P1_LABEL}"
BENCH_SKIP = f"sibling-repo data not in tree: {BENCH_LABEL}"


def sibling_root() -> Path:
    """Directory that would contain sibling clones, if the caller has them.

    ``EVAL_META_SIBLING_ROOT`` overrides the default (the parent of this repo).
    This package does not vendor those clones.
    """
    env = os.environ.get("EVAL_META_SIBLING_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1].parent


def p1_files() -> tuple[Path, Path]:
    root = sibling_root() / "agi-research-program" / "p1"
    return root / "claims.json", root / "recompute_receipts.json"


def bench_file(name: str) -> Path:
    return (
        sibling_root()
        / "llm-agent-projects"
        / "20-llm-eval-benchmark"
        / "data"
        / f"{name}_sample.json"
    )
