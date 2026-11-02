"""自我审计层（校准探针 + 失效分类）——蓝图 §5，评测的评测。

锚定证据：
- EvalSafetyGap (arXiv:2606.30219, Uluırmak & Kurban 2026, 74页, 373 项研究)：
  把基准效度与对齐失败统一为「优化压力下的代理-目标发散」问题。
- 设计指导（2608.08722）：迁移率仅按每失败机制分级（gamed/overfit/benign）可解释。

设计：
1. 校准探针（Loop A）：定期注入已知答案的探针，验证系统仍测得对。
   探针 = 已知真值的题目，系统必须测得对，否则系统自己失效。
2. 失效分类（Loop B）：把每次评测失败归入 gamed（被钻）/overfit（过拟合）/benign（良性）。
   单一迁移率不可解释，必须按机制分级。

关键纪律（蓝图 §5.3 自指问题）：
- 校准探针注入已知真值，验证系统内部一致性。
- 人类锚定（judge 校准）是外部锚点，非自指；本模块的校准探针用**已知真值**而非 Bradley-Terry
  每周校正（BT 是 judge 校准层的外部锚点，见 judge.py；本模块实现的是内部一致性探针）。
- 独立重算（PROGRAM.md P1）是外部验证。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class FailureMode(str, Enum):
    """失效机制分类（2608.08722：迁移率仅按每失败机制分级可解释）。"""

    GAMED = "gamed"        # 被钻（系统被攻击者利用）
    OVERFIT = "overfit"    # 过拟合（系统在测试集过拟合，不泛化）
    BENIGN = "benign"      # 良性（正常失效，无恶意）


@dataclass(frozen=True)
class Probe:
    """校准探针：已知真值的测试题。"""

    probe_id: str
    true_value: float       # 已知真值（0-1）
    tolerance: float = 0.02  # 容差（±2%）

    def is_within_tolerance(self, measured: float) -> bool:
        # 浮点边界容差（如 0.78 与 0.80 的差 = 0.020000000000000018）
        return abs(measured - self.true_value) <= self.tolerance + 1e-9


@dataclass(frozen=True)
class ProbeResult:
    """探针测量结果。"""

    probe: Probe
    measured: float
    passed: bool            # 是否在容差内
    deviation: float        # |measured − true_value|

    @property
    def failed(self) -> bool:
        return not self.passed


@dataclass(frozen=True)
class AuditReport:
    """自我审计报告。"""

    system_healthy: bool    # 系统是否健康（所有探针通过）
    probes_total: int
    probes_passed: int
    probes_failed: int
    failures: list[ProbeResult]  # 失败的探针
    detail: str

    def to_dict(self) -> dict:
        return {
            "system_healthy": self.system_healthy,
            "probes_total": self.probes_total,
            "probes_passed": self.probes_passed,
            "probes_failed": self.probes_failed,
            "failures": [
                {"probe_id": f.probe.probe_id, "measured": round(f.measured, 4),
                 "true_value": f.probe.true_value, "deviation": round(f.deviation, 4)}
                for f in self.failures
            ],
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Migration:
    """一次迁移率测量（held-out 性能 vs 训练集性能）。"""

    mechanism: str          # 触发迁移的机制名
    train_perf: float       # 训练集/被评估集性能
    heldout_perf: float     # held-out 性能
    is_gamed: bool = False  # 是否被钻（攻击者利用）
    is_overfit: bool = False  # 是否过拟合


@dataclass(frozen=True)
class FailureClassification:
    """失效分类结果。"""

    mechanism: str
    failure_mode: FailureMode
    train_perf: float
    heldout_perf: float
    migration_gap: float    # train − heldout
    basis: str

    def to_dict(self) -> dict:
        return {
            "mechanism": self.mechanism,
            "failure_mode": self.failure_mode.value,
            "train_perf": round(self.train_perf, 4),
            "heldout_perf": round(self.heldout_perf, 4),
            "migration_gap": round(self.migration_gap, 4),
            "basis": self.basis,
        }


def classify_failure(migration: Migration, overfit_threshold: float = 0.15) -> FailureClassification:
    """把一次迁移率失效分类。

    判据（2608.08722）：
    - 被钻（is_gamed=True）→ GAMED（无论迁移率如何）。
    - 过拟合（train 高、held-out 低，gap > 15%）→ OVERFIT。
    - 否则 → BENIGN（正常失效）。
    """
    gap = migration.train_perf - migration.heldout_perf
    if migration.is_gamed:
        mode = FailureMode.GAMED
        basis = "is_gamed"
    elif gap > overfit_threshold:
        mode = FailureMode.OVERFIT
        basis = f"gap={gap:.4f}>{overfit_threshold}"
    else:
        mode = FailureMode.BENIGN
        basis = f"gap={gap:.4f}<={overfit_threshold}"
    return FailureClassification(
        mechanism=migration.mechanism,
        failure_mode=mode,
        train_perf=migration.train_perf,
        heldout_perf=migration.heldout_perf,
        migration_gap=gap,
        basis=basis,
    )


def run_probe_battery(probes: Sequence[Probe], measure_fn) -> AuditReport:
    """运行校准探针电池。

    measure_fn(probe) -> float：对每个探针返回测量值。
    系统健康 = 所有探针在容差内。
    """
    results: list[ProbeResult] = []
    for p in probes:
        measured = measure_fn(p)
        passed = p.is_within_tolerance(measured)
        results.append(ProbeResult(probe=p, measured=measured, passed=passed,
                                   deviation=abs(measured - p.true_value)))

    failed = [r for r in results if r.failed]
    healthy = len(failed) == 0
    detail = (
        f"probes={len(results)} passed={len(results) - len(failed)} failed={len(failed)}"
        if healthy
        else f"FAILED probes: {[f.probe.probe_id for f in failed]}"
    )
    return AuditReport(
        system_healthy=healthy,
        probes_total=len(results),
        probes_passed=len(results) - len(failed),
        probes_failed=len(failed),
        failures=failed,
        detail=detail,
    )


def _run_selftest() -> int:
    """RED→GREEN 自检。"""
    failures = 0

    # GREEN 1：探针全部在容差内 → 系统健康
    probes = [Probe("p1", true_value=0.80), Probe("p2", true_value=0.60)]
    report = run_probe_battery(probes, lambda p: p.true_value + 0.01)  # 测量接近真值
    if not report.system_healthy:
        print(f"[FAIL] GREEN1: accurate probes → system should be healthy")
        failures += 1
    else:
        print(f"[PASS] GREEN1: probes healthy ({report.detail})")

    # RED 1：探针超出容差 → 系统不健康（系统自己失效）
    report = run_probe_battery(probes, lambda p: p.true_value + 0.10)  # 测量偏 10%
    if report.system_healthy:
        print(f"[FAIL] RED1: inaccurate probes → system should be unhealthy")
        failures += 1
    else:
        print(f"[PASS] RED1: probes detect system failure ({report.detail})")

    # RED 2：被钻 → 必须判 GAMED
    c = classify_failure(Migration("m1", train_perf=0.90, heldout_perf=0.88, is_gamed=True))
    if c.failure_mode != FailureMode.GAMED:
        print(f"[FAIL] RED2: gamed should be GAMED, got {c.failure_mode.value}")
        failures += 1
    else:
        print(f"[PASS] RED2: gamed classified ({c.basis})")

    # RED 3：过拟合（train 高、held-out 低）→ 必须判 OVERFIT
    c = classify_failure(Migration("m2", train_perf=0.90, heldout_perf=0.60))
    if c.failure_mode != FailureMode.OVERFIT:
        print(f"[FAIL] RED3: overfit should be OVERFIT, got {c.failure_mode.value}")
        failures += 1
    else:
        print(f"[PASS] RED3: overfit classified (gap={c.migration_gap:.4f})")

    # GREEN 2：正常失效 → BENIGN
    c = classify_failure(Migration("m3", train_perf=0.80, heldout_perf=0.75))
    if c.failure_mode != FailureMode.BENIGN:
        print(f"[FAIL] GREEN2: normal should be BENIGN, got {c.failure_mode.value}")
        failures += 1
    else:
        print(f"[PASS] GREEN2: benign classified (gap={c.migration_gap:.4f})")

    print(f"\n自我审计层 selftest: {'PASS' if failures == 0 else f'FAIL ({failures})'}")
    return failures


if __name__ == "__main__":
    import sys
    sys.exit(_run_selftest())
