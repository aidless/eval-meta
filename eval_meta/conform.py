"""抗污染门（ConStat 行为性检测）——蓝图 §3.2。

锚定证据：ConStat (arXiv:2405.16281, Dekoninck/Mueller/Vechev 2024)。
核心定义：污染 = 「人为膨胀且不泛化的基准性能」，而非「训练数据含基准样本」。
无需访问训练数据即可检测——这正是蓝图 §3.2 解决「污染检测与隐私冲突」的关键。

设计：一个模型在一个基准上表现高，但在改写样本 / 同分布合成样本 / 同任务不同基准上
表现明显更低 = 性能膨胀且不泛化 = 污染。检测的是「行为」，不是「数据归属」。

三档分级（相对差 = 膨胀量 / 基准性能，来自知识库污染分级作为工程阈值）：
    L1 ≤ 2%     低污染（干净）
    L2 2%–10%   中污染（可疑）
    L3 > 10%    高污染（红线）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

# --- 工程阈值（相对差三档，来自知识库污染分级）---
L1_MAX = 0.02   # 2% 相对差以内 = 干净
L2_MAX = 0.10   # 10% 相对差以内 = 可疑


@dataclass(frozen=True)
class ModelPerformance:
    """一个模型在某个评测面上的表现。"""

    model: str
    # 原始基准表现（0-1 的准确率/得分率）
    base: float
    # 改写样本表现（同一题改写成同型新题）
    rewritten: float
    # 同分布合成样本表现（同任务、不同基准）
    synthetic: float
    # 同任务不同基准表现（跨基准泛化）
    cross_bench: float
    # 样本量（用于置信判断）
    n: int = 100

    @property
    def expansion(self) -> float:
        """膨胀量 = 原始表现 − 泛化表现（改写/合成/跨基准的最小值）。"""
        generalization = min(self.rewritten, self.synthetic, self.cross_bench)
        return self.base - generalization


@dataclass(frozen=True)
class ContaminationVerdict:
    """污染判定结果。"""

    model: str
    expansion: float
    ratio: float
    level: str          # L1 / L2 / L3
    contaminated: bool  # 是否判为污染膨胀
    basis: str          # 判定依据（哪条面泛化最弱）

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "expansion": round(self.expansion, 4),
            "ratio": round(self.ratio, 4),
            "level": self.level,
            "contaminated": self.contaminated,
            "basis": self.basis,
        }


def _classify(expansion: float, base: float) -> tuple[str, bool, str]:
    """按膨胀量分级。

    判据修正（2026-11-01 v2）：污染膨胀是**相对量**——「泛化面比原始面低多少比例」，
    不是绝对差。真实模型的泛化噪声通常 1-5%（跨基准/改写/合成的自然衰减），
    污染膨胀是 20%+ 的持续塌陷。阈值按相对差：
        L1  < 2%     相对泛化衰减（正常噪声）
        L2  2%-10%   相对泛化衰减（可疑，需复查）
        L3  > 10%    相对泛化衰减（污染膨胀红线）
    """
    if base <= 0:
        return "L1", False, "base_zero"
    ratio = expansion / base
    # 相对阈值：正常模型泛化面衰减 <2%（噪声），污染膨胀 >10%（塌陷）
    if ratio <= 0.02:
        return "L1", False, f"ratio<={0.02}"
    if ratio <= 0.10:
        return "L2", True, f"ratio<={0.10}"
    return "L3", True, f"ratio>{0.10}"


def detect(performances: Sequence[ModelPerformance], verbose: bool = False) -> list[ContaminationVerdict]:
    """对一批模型做行为性污染检测。

    判据（ConStat）：若 base 高而改写/合成/跨基准至少一条面明显低，
    说明性能膨胀不泛化 = 污染。用「泛化面最小值」做最保守估计。
    """
    verdicts: list[ContaminationVerdict] = []
    for p in performances:
        expansion = p.expansion
        level, contaminated, basis = _classify(expansion, p.base)
        verdicts.append(
            ContaminationVerdict(
                model=p.model,
                expansion=expansion,
                ratio=(expansion / p.base) if p.base > 0 else 0.0,
                level=level,
                contaminated=contaminated,
                basis=basis,
            )
        )
        if verbose:
            print(f"  {p.model}: expansion={expansion:.4f} level={level} "
                  f"contaminated={contaminated} basis={basis}")
    return verdicts


def _run_selftest() -> int:
    """RED→GREEN 自检：注入已知污染，门必须报红。

    返回 exit code：0=全部符合预期；1=有断言失败。
    """
    failures = 0

    # GREEN 1：无污染模型（泛化面都在 base 附近，相对衰减 <0.5%）→ 必须判 L1 不污染
    # clean 模型泛化面在 base 的 1% 内是正常噪声（0.80 vs 0.79/0.795/0.798）
    clean = ModelPerformance(
        model="clean-model", base=0.80, rewritten=0.795, synthetic=0.798, cross_bench=0.796, n=100
    )
    v = detect([clean])[0]
    if v.contaminated or v.level != "L1":
        print(f"[FAIL] GREEN1: clean model should be L1/clean, got level={v.level} contaminated={v.contaminated}")
        failures += 1
    else:
        print(f"[PASS] GREEN1: clean model level={v.level} contaminated={v.contaminated}")

    # RED 1：高污染模型（base 高但所有泛化面都低，相对衰减>10%）→ 必须判 L3 污染
    dirty = ModelPerformance(
        model="dirty-model", base=0.85, rewritten=0.60, synthetic=0.55, cross_bench=0.50, n=100
    )
    v = detect([dirty])[0]
    if not v.contaminated or v.level != "L3":
        print(f"[FAIL] RED1: dirty model should be L3/contaminated, got level={v.level} contaminated={v.contaminated}")
        failures += 1
    else:
        print(f"[PASS] RED1: dirty model level={v.level} contaminated={v.contaminated}")

    # RED 2：中污染（相对衰减在 2%-10% 之间）→ 必须判 L2
    # base=0.85, 泛化面 min=0.80 → expansion=0.05 → ratio=5.88% → L2
    mid = ModelPerformance(
        model="mid-model", base=0.85, rewritten=0.82, synthetic=0.80, cross_bench=0.84, n=100
    )
    v = detect([mid])[0]
    if not (0.02 < mid.expansion / mid.base <= 0.10):
        print(f"[INFO] mid expansion={mid.expansion:.4f} ratio={mid.expansion/mid.base:.4f}")
    if not v.contaminated or v.level != "L2":
        print(f"[FAIL] RED2: mid model should be L2/contaminated, got level={v.level} contaminated={v.contaminated}")
        failures += 1
    else:
        print(f"[PASS] RED2: mid model level={v.level} contaminated={v.contaminated}")

    # RED 3：膨胀方向必须正确——base 低于泛化面 = 无膨胀，不能判污染
    inverted = ModelPerformance(
        model="inverted-model", base=0.60, rewritten=0.75, synthetic=0.78, cross_bench=0.80, n=100
    )
    v = detect([inverted])[0]
    if v.contaminated:
        print(f"[FAIL] RED3: inverted model (base<generalization) should NOT be contaminated")
        failures += 1
    else:
        print(f"[PASS] RED3: inverted model not contaminated (expansion={v.expansion:.4f})")

    print(f"\n抗污染门 selftest: {'PASS' if failures == 0 else f'FAIL ({failures})'}")
    return failures


if __name__ == "__main__":
    import sys
    sys.exit(_run_selftest())
