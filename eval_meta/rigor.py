"""统计严谨门（κ 触及报告 + Cohen's d + Wilson CI）——蓝图 §4.1。

锚定证据：
- Agreement by Construction（2026 Crossref）：确定性前置规则把 Cohen's κ 从 0.056 充到
  0.714（600 LoCoMo 配对）；461 未触及判决 κ=0.064 不变 → 表观改善不来自真一致。
- 关键纪律：报告 κ 本身不够，必须报告「哪些判决被触及、哪些没被触及」。
  只报「未触及判决」的 κ。若 κ 只来自被触及判决，必须警告表观一致不来自真一致。

设计：
1. Wilson 95% CI（解析公式，来自知识库统计严谨性；bootstrap 1000 次是知识库的另一条路径，
   本模块实现解析 Wilson——更快且对比例区间足够精确）。
2. Cohen's d 效应量（p<0.05 不够，必须报效应量）。
3. κ 触及报告：区分「被触及」vs「未触及」判决，分别报告 κ。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


# ---------- Wilson 置信区间 ----------

def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% 置信区间（用于比例）。"""
    if n <= 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = float(center - half)
    hi = float(center + half)
    # clamp 到 [0,1]（float64 精度可致 0.9999... < 1.0）
    return (max(0.0, min(1.0, lo)), max(0.0, min(1.0, hi)))


# ---------- Cohen's d ----------

def cohens_d(scores_a: Sequence[float], scores_b: Sequence[float]) -> float:
    """Cohen's d 效应量（合并标准差）。"""
    a = np.array(scores_a, dtype=float)
    b = np.array(scores_b, dtype=float)
    if len(a) < 2 or len(b) < 2:
        return 0.0
    pooled_sd = np.sqrt(((len(a) - 1) * a.std(ddof=1) ** 2 + (len(b) - 1) * b.std(ddof=1) ** 2) / (len(a) + len(b) - 2))
    if pooled_sd == 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled_sd)


# ---------- κ 触及报告 ----------

@dataclass(frozen=True)
class AgreementDecision:
    """一次人机一致性判定（LLM-judge vs 人类评审）。"""

    decision_id: str
    judge_verdict: bool      # LLM judge 判定
    human_verdict: bool      # 人类评审判定
    touched: bool            # 是否被确定性前置规则「触及」（关键：Agreement by Construction）
    by_construction: bool = False  # 是否由设计规则判定（而非 judge 真实判定）


@dataclass(frozen=True)
class KappaReport:
    """κ 触及报告：区分被触及 vs 未触及判决。"""

    total: int
    touched_count: int
    untouched_count: int
    kappa_all: float            # 全部判决的 κ
    kappa_touched: float        # 被触及判决的 κ
    kappa_untouched: float      # 未触及判决的 κ（真一致）
    kappa_inflated_by_touching: bool  # 表观一致是否被触及规则充高
    warning: str | None

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "touched_count": self.touched_count,
            "untouched_count": self.untouched_count,
            "kappa_all": round(self.kappa_all, 4),
            "kappa_touched": round(self.kappa_touched, 4),
            "kappa_untouched": round(self.kappa_untouched, 4),
            "kappa_inflated_by_touching": self.kappa_inflated_by_touching,
            "warning": self.warning,
        }


def _cohens_kappa(a: Sequence[bool], b: Sequence[bool]) -> float:
    """Cohen's κ（原始公式）。"""
    if len(a) != len(b) or len(a) == 0:
        return 0.0
    n = len(a)
    # 观察一致率
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    # 期望一致率（边际）
    pa = sum(a) / n
    pb = sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return float((po - pe) / (1 - pe))


def kappa_touch_report(decisions: Sequence[AgreementDecision]) -> KappaReport:
    """生成 κ 触及报告。

    关键纪律（Agreement by Construction）：必须分别报告被触及/未触及判决的 κ。
    若 kappa_touched 显著高于 kappa_untouched，表观一致是「被设计充高」，
    必须警告「表观改善不来自真一致」。
    """
    if not decisions:
        return KappaReport(
            total=0, touched_count=0, untouched_count=0,
            kappa_all=0.0, kappa_touched=0.0, kappa_untouched=0.0,
            kappa_inflated_by_touching=False, warning="no_decisions",
        )

    all_j = [d.judge_verdict for d in decisions]
    all_h = [d.human_verdict for d in decisions]
    touched_j = [d.judge_verdict for d in decisions if d.touched]
    touched_h = [d.human_verdict for d in decisions if d.touched]
    untouched_j = [d.judge_verdict for d in decisions if not d.touched]
    untouched_h = [d.human_verdict for d in decisions if not d.touched]

    k_all = _cohens_kappa(all_j, all_h)
    k_touched = _cohens_kappa(touched_j, touched_h) if touched_j else 0.0
    k_untouched = _cohens_kappa(untouched_j, untouched_h) if untouched_j else 0.0

    # 充高判据：被触及判决 κ 显著高于未触及（差值 > 0.1），且未触及判决有样本
    inflated = (len(untouched_j) > 0) and (k_touched - k_untouched > 0.1)
    warning = None
    if inflated:
        warning = (
            f"kappa_inflated_by_touching: touched kappa={k_touched:.3f} >> "
            f"untouched kappa={k_untouched:.3f}. 表观改善不来自真一致，"
            f"只报未触及判决 κ（Agreement by Construction 0.056→0.714 vs 0.064）。"
        )

    return KappaReport(
        total=len(decisions),
        touched_count=len(touched_j),
        untouched_count=len(untouched_j),
        kappa_all=k_all,
        kappa_touched=k_touched,
        kappa_untouched=k_untouched,
        kappa_inflated_by_touching=inflated,
        warning=warning,
    )


def _run_selftest() -> int:
    """RED→GREEN 自检。"""
    failures = 0

    # GREEN 1：无触及规则的判决，κ 来自真一致 → 不警告
    decisions = [
        AgreementDecision(f"d{i}", judge_verdict=(i % 3 == 0), human_verdict=(i % 3 == 0), touched=False)
        for i in range(30)
    ]
    r = kappa_touch_report(decisions)
    if r.kappa_inflated_by_touching:
        print(f"[FAIL] GREEN1: no touching rule → should not be inflated")
        failures += 1
    else:
        print(f"[PASS] GREEN1: no touching (kappa_untouched={r.kappa_untouched:.3f})")

    # RED 1：触及规则充高 κ（touched κ >> untouched κ）→ 必须警告
    # 构造：被触及判决几乎全一致（κ高），未触及判决随机（κ低）
    touched = [AgreementDecision(f"t{i}", judge_verdict=True, human_verdict=True, touched=True, by_construction=True) for i in range(20)]
    untouched = [AgreementDecision(f"u{i}", judge_verdict=(i % 2 == 0), human_verdict=(i % 2 == 1), touched=False) for i in range(20)]
    r = kappa_touch_report(touched + untouched)
    if not r.kappa_inflated_by_touching:
        print(f"[FAIL] RED1: touching rule should be flagged as inflated")
        failures += 1
    else:
        print(f"[PASS] RED1: touching flagged (kappa_touched={r.kappa_touched:.3f} vs untouched={r.kappa_untouched:.3f})")

    # RED 2：Cohen's d 效应量必须有正负方向
    d = cohens_d([1.0, 2.0, 3.0, 4.0], [1.0, 1.0, 1.0, 1.0])
    if d <= 0:
        print(f"[FAIL] RED2: cohens_d should be positive (A>B)")
        failures += 1
    else:
        print(f"[PASS] RED2: cohens_d={d:.3f} (A>B, positive)")

    # RED 3：Wilson CI 必须包含点估计
    lo, hi = wilson_ci(80, 100)
    if not (lo <= 0.80 <= hi):
        print(f"[FAIL] RED3: wilson_ci must contain point estimate 0.80, got ({lo:.3f},{hi:.3f})")
        failures += 1
    else:
        print(f"[PASS] RED3: wilson_ci=({lo:.3f},{hi:.3f}) contains 0.80")

    print(f"\n统计严谨门 selftest: {'PASS' if failures == 0 else f'FAIL ({failures})'}")
    return failures


if __name__ == "__main__":
    import sys
    sys.exit(_run_selftest())
