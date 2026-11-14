"""Judge 校准层（位置/长度/自我偏差校正 + 抗偏好泄漏门）——蓝图 §4.2。

锚定证据：
- 2026 Crossref：位置 flip 0.17–0.50、冗长 0.15–0.42、自我高估 +3.5~4.5、自信但错 0.075。
- PLOS One 10 周波次：校准提高与人类一致（τ=0.59–0.68 且降波动）。
- Preference Leakage (arXiv:2502.01534)：judge 偏好与自己同族模型，比既有偏差更难检测。

设计：judge 不是「可信」，是**可校准**。
1. 预注册校准电池估计位置/长度/自我/权威系数。
2. 修正模型：s_corrected = s − coefficient。
3. 抗偏好泄漏门：judge 与生成器同族时，必须判红（分数不可信）。

校准电池必须预注册（主指标唯一），否则本身成为被优化的目标（P6 自指问题）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class JudgeCalibration:
    """一个 judge 的校准系数（从预注册校准电池估计）。"""

    judge: str
    position_bias: float = 0.0     # 位置偏差（展示顺序偏好）
    length_bias: float = 0.0       # 长度偏差（冗长偏好）
    self_bias: float = 0.0         # 自我高估（judge 对自己族模型）
    authority_bias: float = 0.0    # 权威偏差（对知名模型）
    n_calibration: int = 0         # 校准样本量
    tau: float = 0.0               # 校准后与人类一致度（Kendall tau）
    calibrated: bool = False       # 是否已校准（n_calibration 足够）

    @property
    def total_bias(self) -> float:
        return self.position_bias + self.length_bias + self.self_bias + self.authority_bias


@dataclass(frozen=True)
class ScoredResponse:
    """一次带元数据的评分。"""

    response_id: str
    judge: str
    model: str
    raw_score: float            # judge 原始分（0-10 或 0-1）
    position: int = 0           # 展示位置（0=先）
    length_chars: int = 0       # 响应长度（字符）
    is_self_family: bool = False  # 是否 judge 与 model 同族
    is_authority: bool = False    # 是否知名模型


@dataclass(frozen=True)
class CorrectedScore:
    """校正后得分。"""

    response_id: str
    judge: str
    model: str
    raw_score: float
    corrected_score: float
    preference_leakage: bool     # 同族偏好判红
    basis: str

    def to_dict(self) -> dict:
        return {
            "response_id": self.response_id,
            "judge": self.judge,
            "model": self.model,
            "raw_score": round(self.raw_score, 4),
            "corrected_score": round(self.corrected_score, 4),
            "preference_leakage": self.preference_leakage,
            "basis": self.basis,
        }


def correct(scores: Sequence[ScoredResponse], calibrations: Sequence[JudgeCalibration]) -> list[CorrectedScore]:
    """应用校准 + 抗偏好泄漏门。

    修正模型（蓝图 §4.2）：s_corrected = s_raw − (position_bias + length_bias + self_bias + authority_bias)。
    偏好泄漏：judge 与 model 同族 → 必须判红，分数不可信。

    注：位置/长度/自我/权威偏差各自独立估计后，从原始分中扣除。
    若 judge 未校准（n_calibration < 30），校正不生效，但偏好泄漏仍判红。
    """
    calib_map = {c.judge: c for c in calibrations}
    results: list[CorrectedScore] = []
    for s in scores:
        cal = calib_map.get(s.judge)
        if cal is None or not cal.calibrated:
            # 未校准：只做偏好泄漏判红，不做偏差校正
            leakage = s.is_self_family
            basis = "uncalibrated"
            if leakage:
                basis = "uncalibrated,preference_leakage"
            results.append(CorrectedScore(
                response_id=s.response_id, judge=s.judge, model=s.model,
                raw_score=s.raw_score, corrected_score=s.raw_score,
                preference_leakage=leakage, basis=basis,
            ))
            continue

        # 已校准：扣除偏差（各系数夹紧到 ≥0，避免负偏差反向放大分数）
        deduction = (max(0.0, cal.position_bias) + max(0.0, cal.length_bias)
                     + max(0.0, cal.self_bias) + max(0.0, cal.authority_bias))
        corrected = max(0.0, s.raw_score - deduction)
        leakage = s.is_self_family
        basis = f"calibrated,deduct={deduction:.4f}"
        if leakage:
            basis += ",preference_leakage"
        results.append(CorrectedScore(
            response_id=s.response_id, judge=s.judge, model=s.model,
            raw_score=s.raw_score, corrected_score=corrected,
            preference_leakage=leakage, basis=basis,
        ))
    return results


def estimate_calibration(
    judge: str,
    raw_scores: Sequence[float],
    positions: Sequence[int],
    lengths: Sequence[float],
    self_flags: Sequence[bool],
    authority_flags: Sequence[bool],
    tau: float = 0.0,
    min_samples: int = 30,
) -> JudgeCalibration:
    """从预注册校准电池估计偏差系数。

    最小二乘拟合：raw ≈ intercept + β_pos·position + β_len·length_norm
                             + β_self·self_flag + β_auth·authority_flag
    其中 length_norm 是归一化长度（0-1，除以最大长度）。
    返回校准系数（position/length/self/authority 即 β_pos/β_len/β_self/β_auth）。

    校准电池必须预注册（主指标唯一），否则本身成为被优化的目标。
    样本量 < min_samples 不算已校准。
    """
    n = len(raw_scores)
    if n < min_samples:
        return JudgeCalibration(judge=judge, n_calibration=n, tau=tau, calibrated=False)

    # 归一化长度
    max_len = max(lengths) if lengths else 1.0
    len_norm = [l / max_len for l in lengths]

    # 设计矩阵：截距 + position + len_norm + self + authority
    X = np.column_stack([
        np.ones(n),
        np.array(positions, dtype=float),
        np.array(len_norm, dtype=float),
        np.array(self_flags, dtype=float),
        np.array(authority_flags, dtype=float),
    ])
    y = np.array(raw_scores, dtype=float)

    # 最小二乘（无正则化，简单线性）
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    intercept, beta_pos, beta_len, beta_self, beta_auth = coef

    return JudgeCalibration(
        judge=judge,
        position_bias=float(beta_pos),
        length_bias=float(beta_len),
        self_bias=float(beta_self),
        authority_bias=float(beta_auth),
        n_calibration=n,
        tau=tau,
        calibrated=True,
    )


def _run_selftest() -> int:
    """RED→GREEN 自检。"""
    failures = 0
    cal = JudgeCalibration(
        judge="judge-A", position_bias=0.10, length_bias=0.05,
        self_bias=0.20, authority_bias=0.02, n_calibration=100, tau=0.62, calibrated=True,
    )

    # GREEN 1：已校准，扣减正常生效（无偏好泄漏）
    s = ScoredResponse(response_id="r1", judge="judge-A", model="m", raw_score=8.0,
                       position=0, length_chars=500, is_self_family=False)
    r = correct([s], [cal])[0]
    # corrected = 8.0 - (0.10+0.05+0.20+0.02) = 7.63
    if r.preference_leakage or abs(r.corrected_score - 7.63) > 1e-9:
        print(f"[FAIL] GREEN1: corrected should be 7.63, got {r.corrected_score:.4f} leakage={r.preference_leakage}")
        failures += 1
    else:
        print(f"[PASS] GREEN1: corrected={r.corrected_score:.4f}")

    # RED 1：同族偏好必须判红
    s = ScoredResponse(response_id="r2", judge="judge-A", model="m-same-family",
                       raw_score=8.5, is_self_family=True)
    r = correct([s], [cal])[0]
    if not r.preference_leakage:
        print("[FAIL] RED1: self-family should be flagged as preference leakage")
        failures += 1
    else:
        print("[PASS] RED1: self-family flagged")

    # RED 2：未校准 judge 不做偏差校正，但仍判偏好泄漏
    s = ScoredResponse(response_id="r3", judge="judge-B", model="m-same-family",
                       raw_score=8.0, is_self_family=True)
    r = correct([s], [cal])[0]
    if not r.preference_leakage:
        print("[FAIL] RED2: uncalibrated judge should still flag self-family")
        failures += 1
    else:
        print("[PASS] RED2: uncalibrated judge flags self-family")

    print(f"\njudge 校准层 selftest: {'PASS' if failures == 0 else f'FAIL ({failures})'}")
    return failures


if __name__ == "__main__":
    import sys
    sys.exit(_run_selftest())
