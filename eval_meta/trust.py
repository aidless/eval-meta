"""per-edit 信任度打分器（P4）——回答「哪类 harness 改动值得信」。

输入：evoagent 的 `.evo/verdicts.jsonl`（change_manifest 每次对账的逐编辑
判定，append-only 信任账本）。输出：按 edit kind（`prompt`/`tool`/
`middleware`/`memory`/...）给出 L1 可信 / L2 观察 / L3 不可信 / NOT_ASSESSED
证据不足四态，以及 campaign 级总判决。

为什么需要它：arXiv:2604.25850（AHE）实测 fix 预测 precision 仅 33.7%
（随机基线 6.5%），regression 预测更是 11.8%/11.1% 的盲区；「这轮改完分数
涨了」不等于「这类改动可信」。arXiv:2605.27276（SIA）进一步指出两杠杆共用
固定 verifier 会产生 Coupled co-evolutionary Goodhart。因此本模块的门槛只从
可复算的 per-edit 证据来，不读成功率、不读自我声明的置信度。

三态纪律（AGENTS.md 第 8/21 条）：样本不足一律 NOT_ASSESSED，绝不静默判
可信；`_run_selftest()` 内置违规注入，必须能红才算门有效。
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

MIN_EDITS = 5                    # 少于 5 次有效编辑不下结论（功效门槛）
REGRESSION_BLOCK_RATE = 0.30     # 回归率 >30% → L3
PRECISION_TRUST_FLOOR = 0.50     # 平均预测精度 >=50% 才可能 L1
PRECISION_BLIND_FLOOR = 0.20     # <20% 接近随机基线（AHE 随机基线 6.5%）
REGRESSION_TRUST_CEIL = 0.10     # L1 允许至多 10% 回归


@dataclass(frozen=True)
class TrustScore:
    """一个 edit kind 的信任度读数。"""

    kind: str
    n_edits: int
    invalid: int
    mean_precision: float | None
    regression_rate: float
    level: str
    reasons: tuple[str, ...]
    basis: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "n_edits": self.n_edits,
            "invalid": self.invalid,
            "mean_precision": (round(self.mean_precision, 6)
                               if self.mean_precision is not None else None),
            "regression_rate": round(self.regression_rate, 6),
            "level": self.level,
            "reasons": list(self.reasons),
            "basis": self.basis,
        }


def load_verdicts(path: str | Path) -> list[dict[str, Any]]:
    """读 JSONL 信任账本；坏行跳过（append-only 账本不因一行损坏整体作废）。

    文件不存在返回 []，由 score_history 判 NOT_ASSESSED 第三态。
    """
    p = Path(path)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _kinds(rows: Sequence[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for row in rows:
        if not row.get("valid", True):
            continue
        for edit in row.get("edits") or ():
            if not isinstance(edit, dict):
                continue
            kind = str(edit.get("kind") or "unknown")
            if kind not in out:
                out.append(kind)
    return out


def score_kind(rows: Sequence[dict[str, Any]], kind: str,
               min_edits: int = MIN_EDITS) -> TrustScore:
    """给单个 edit kind 打分；证据不足返回 NOT_ASSESSED（不是可信）。"""
    precisions: list[float] = []
    verdicts: list[str] = []
    invalid = 0
    for row in rows:
        if not row.get("valid", True):
            invalid += 1
            continue
        for edit in row.get("edits") or ():
            if not isinstance(edit, dict) or str(edit.get("kind") or "unknown") != kind:
                continue
            verdicts.append(str(edit.get("verdict") or "unknown"))
            precision = edit.get("prediction_precision")
            if isinstance(precision, (int, float)) and not isinstance(precision, bool):
                precisions.append(float(precision))
    n_edits = len(verdicts)
    regressions = sum(1 for v in verdicts if v == "regression")
    regression_rate = regressions / n_edits if n_edits else 0.0
    mean_precision = sum(precisions) / len(precisions) if precisions else None
    basis = (f"n_edits={n_edits}, invalid={invalid}, "
             f"regressions={regressions}, precision_carriers={len(precisions)}")

    if n_edits < min_edits:
        return TrustScore(kind, n_edits, invalid, mean_precision, regression_rate,
                          "NOT_ASSESSED", ("insufficient_evidence",), basis)

    reasons: list[str] = []
    if regression_rate > REGRESSION_BLOCK_RATE:
        reasons.append("regression_rate_high")
    if mean_precision is not None and mean_precision < PRECISION_TRUST_FLOOR:
        reasons.append("low_prediction_precision")
    if mean_precision is None:
        reasons.append("missing_precision_carriers")
    if not precisions or len(precisions) < n_edits:
        reasons.append("incomplete_precision_coverage")

    if "regression_rate_high" in reasons:
        level = "L3"
    elif mean_precision is None:
        level = "L2"
    elif mean_precision < PRECISION_BLIND_FLOOR:
        level = "L3"          # 接近随机基线：预测本身没有信息量
        if "blind_prediction" not in reasons:
            reasons.append("blind_prediction")
    elif (mean_precision >= PRECISION_TRUST_FLOOR
          and regression_rate <= REGRESSION_TRUST_CEIL
          and "incomplete_precision_coverage" not in reasons):
        level = "L1"
    else:
        level = "L2"
    return TrustScore(kind, n_edits, invalid, mean_precision, regression_rate,
                      level, tuple(reasons), basis)


def score_history(rows: Sequence[dict[str, Any]],
                  min_edits: int = MIN_EDITS) -> dict[str, Any]:
    """整份账本的总判决：任一类 L3 → BLOCK；有 L2/NOT_ASSESSED → WARN。"""
    kinds = _kinds(rows)
    scores = {k: score_kind(rows, k, min_edits).to_dict() for k in kinds}
    levels = {s["level"] for s in scores.values()}
    if not kinds:
        verdict = "NOT_ASSESSED"
    elif "L3" in levels:
        verdict = "BLOCK"
    elif "L2" in levels or "NOT_ASSESSED" in levels:
        verdict = "WARN"
    else:
        verdict = "PASS"
    return {
        "verdict": verdict,
        "campaigns": len(rows),
        "invalid": sum(1 for r in rows if not r.get("valid", True)),
        "kinds": scores,
        "thresholds": {
            "min_edits": min_edits,
            "regression_block_rate": REGRESSION_BLOCK_RATE,
            "precision_trust_floor": PRECISION_TRUST_FLOOR,
            "precision_blind_floor": PRECISION_BLIND_FLOOR,
            "regression_trust_ceil": REGRESSION_TRUST_CEIL,
        },
        "basis": "verdicts.jsonl per-edit ledger; no success-rate or self-reported confidence",
    }


def _fixture(n: int, *, kind: str = "tool", verdict: str = "effective_fix",
             precision: float = 0.80) -> list[dict[str, Any]]:
    return [{
        "run_id": f"selftest-{i}", "candidate_id": f"c{i}", "valid": True,
        "prediction_precision": precision,
        "edits": [{"edit_id": "e1", "kind": kind, "verdict": verdict,
                   "prediction_precision": precision}],
    } for i in range(n)]


def _run_selftest() -> int:
    """自检：GREEN 放行 + RED 反证（注入违规必须判红），任一不成立 return 1。"""
    checks = [
        ("clean_L1", score_kind(_fixture(8), "tool").level == "L1"),
        ("regression_L3", score_kind(
            _fixture(8, verdict="regression"), "tool").level == "L3"),
        ("low_sample_third_state", score_kind(_fixture(2), "tool").level
         == "NOT_ASSESSED"),
        ("empty_history_third_state", score_history([])["verdict"] == "NOT_ASSESSED"),
        ("block_beats_pass", score_history(
            _fixture(8) + _fixture(8, kind="prompt", verdict="regression"))["verdict"]
         == "BLOCK"),
        # RED 反证：把「回归密集」的期望故意写成 L1，正确实现下这个断言必须为假
        ("red_negative_control", not (score_kind(
            _fixture(8, verdict="regression"), "tool").level == "L1")),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"trust selftest: {'PASS' if not failed else 'FAIL (' + ','.join(failed) + ')'}")
    return 1 if failed else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="per-edit trust scorer")
    parser.add_argument("--selftest", action="store_true", help="run RED/GREEN self-check")
    parser.add_argument("ledger", nargs="?", help="path to .evo/verdicts.jsonl")
    parser.add_argument("--min-edits", type=int, default=MIN_EDITS)
    args = parser.parse_args(argv)
    if args.selftest:
        return _run_selftest()
    if not args.ledger:
        parser.error("provide ledger path or --selftest")
    print(json.dumps(score_history(load_verdicts(args.ledger), args.min_edits),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
