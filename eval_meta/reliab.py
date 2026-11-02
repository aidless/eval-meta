"""可靠性估计器（五九）——蓝图 §4.3。

问题：饱和掩盖可靠性需求；99.999% vs 99.9% 差距 = 一个数量级故障。
架构决策：可靠性作为**独立于准确率**的指标。

关键设计：
- 真实部署需 99.999%（五九）可靠性，而非 99.9%（三九）。
- 标准蒙特卡洛在有限算力下不可行 → 用样本高效估计。
  故障呈强系统模式：一小部分输入承担大部分故障（蓝图上文：故障分布、样本效率）。
- 输出：可靠度估计 + 达到五九所需的样本量。

数学（蓝图 §4.3 采样）：
- 可靠度 R = 1 − 故障率 λ。
- 达到目标可靠度 R* 所需的样本量 n ≈ ln(1−δ)/ln(R*)，δ=置信度。
- 注：本模块实现的是**均匀采样**下达到目标可靠度的样本量估计；
  「分层采样可降低样本量」是蓝图的方向性说明，本模块暂未实现分层采样（见 README 模块表）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class ReliabilityEstimate:
    """可靠度估计。"""

    observed_successes: int
    observed_failures: int
    total: int
    reliability: float          # 观测可靠度 R = 成功/总数
    failure_rate: float         # 故障率 λ = 1 − R
    target_reliability: float   # 目标可靠度（如 0.99999）
    meets_target: bool          # 是否达到目标
    n_needed_for_target: float  # 达到目标所需的样本量（当前置信度）
    basis: str

    def to_dict(self) -> dict:
        return {
            "observed_successes": self.observed_successes,
            "observed_failures": self.observed_failures,
            "total": self.total,
            "reliability": round(self.reliability, 6),
            "failure_rate": round(self.failure_rate, 6),
            "target_reliability": self.target_reliability,
            "meets_target": self.meets_target,
            "n_needed_for_target": round(self.n_needed_for_target, 1),
            "basis": self.basis,
        }


def sample_size_for_reliability(target_reliability: float, confidence: float = 0.95) -> float:
    """达到目标可靠度所需的样本量（无故障假设下）。

    n ≈ ln(1−δ)/ln(R*)，δ=置信度。
    例：五九（R*=0.99999），95% 置信 → n≈299,573 样本。
    """
    import math
    if target_reliability <= 0 or target_reliability >= 1:
        raise ValueError("target_reliability must be in (0, 1)")
    delta = 1 - confidence
    if delta <= 0:
        raise ValueError("confidence must be in (0, 1)")
    return math.log(delta) / math.log(target_reliability)


def estimate_reliability(
    results: Sequence[bool],
    target_reliability: float = 0.99999,
    confidence: float = 0.95,
) -> ReliabilityEstimate:
    """从观测结果估计可靠度。

    results[i]=True 表示第 i 次运行成功。
    输出：观测可靠度 + 是否达到目标 + 达到目标所需样本量。
    """
    total = len(results)
    if total == 0:
        return ReliabilityEstimate(
            observed_successes=0, observed_failures=0, total=0,
            reliability=0.0, failure_rate=1.0,
            target_reliability=target_reliability,
            meets_target=False,
            n_needed_for_target=sample_size_for_reliability(target_reliability, confidence),
            basis="no_observations",
        )
    successes = sum(1 for r in results if r)
    failures = total - successes
    reliability = successes / total
    failure_rate = 1 - reliability

    n_needed = sample_size_for_reliability(target_reliability, confidence)
    # 达到目标判据：观测可靠度 ≥ 目标可靠度（在无故障假设下，样本量足够时）
    # 关键：若观测样本量 < 达到目标所需样本量，即使观测可靠度=1.0 也不能声称达到目标
    # （因为样本不够，观测到 0 故障只是运气）
    meets_target = (reliability >= target_reliability) and (total >= n_needed)

    basis = f"reliability={reliability:.6f} (failures={failures}/{total}), n_needed={n_needed:.0f}"
    return ReliabilityEstimate(
        observed_successes=successes,
        observed_failures=failures,
        total=total,
        reliability=reliability,
        failure_rate=failure_rate,
        target_reliability=target_reliability,
        meets_target=meets_target,
        n_needed_for_target=n_needed,
        basis=basis,
    )


def _run_selftest() -> int:
    """RED→GREEN 自检。"""
    failures = 0

    # GREEN 1：样本量足够且无故障 → 达到五九目标
    n = int(sample_size_for_reliability(0.99999, 0.95)) + 10  # 足够样本
    results = [True] * n
    est = estimate_reliability(results, target_reliability=0.99999)
    if not est.meets_target:
        print(f"[FAIL] GREEN1: sufficient clean samples → should meet five-nine")
        failures += 1
    else:
        print(f"[PASS] GREEN1: meets five-nine (R={est.reliability:.6f}, n={n})")

    # RED 1：样本量不足 → 即使观测全成功也不能声称达到目标
    results = [True] * 100  # 只有 100 样本
    est = estimate_reliability(results, target_reliability=0.99999)
    if est.meets_target:
        print(f"[FAIL] RED1: insufficient samples → should NOT meet five-nine")
        failures += 1
    else:
        print(f"[PASS] RED1: insufficient samples correctly rejected (n_needed={est.n_needed_for_target:.0f})")

    # RED 2：有故障 → 未达到目标
    results = [True] * 999 + [False]  # 1 故障 / 1000
    est = estimate_reliability(results, target_reliability=0.99999)
    if est.meets_target:
        print(f"[FAIL] RED2: failures → should NOT meet five-nine")
        failures += 1
    else:
        print(f"[PASS] RED2: failures correctly rejected (R={est.reliability:.6f})")

    # RED 3：样本量公式必须给出正数（五九需要大量样本）
    n = sample_size_for_reliability(0.99999, 0.95)
    if n <= 0:
        print(f"[FAIL] RED3: sample size should be positive")
        failures += 1
    else:
        print(f"[PASS] RED3: sample size n={n:.0f} (positive)")

    print(f"\n可靠性估计器 selftest: {'PASS' if failures == 0 else f'FAIL ({failures})'}")
    return failures


if __name__ == "__main__":
    import sys
    sys.exit(_run_selftest())
