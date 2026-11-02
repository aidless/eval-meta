"""协议效度门测试——RED→GREEN 双验证。"""
import pytest

from eval_meta.validity import HackType, TrajectoryAudit, audit


# ---- GREEN：合规输入必须放行 ----

def test_clean_trajectory_valid():
    """无暴露、gap≈0 的轨迹必须 valid。"""
    clean = TrajectoryAudit(
        trajectory_id="t-clean", model="m", exploit_score=0.80, intended_score=0.79
    )
    v = audit([clean])[0]
    assert v.valid
    assert not v.exposed


def test_small_gap_is_noise():
    """gap=1% 是评分噪声，不判通胀（阈值 0.02）。"""
    noise = TrajectoryAudit(
        trajectory_id="t-noise", model="m", exploit_score=0.80, intended_score=0.79
    )
    v = audit([noise])[0]
    assert v.valid


# ---- RED：违规输入必须报红 ----

def test_exposed_trajectory_invalid():
    """暴露（恢复公开解）→ invalid。"""
    exposed = TrajectoryAudit(
        trajectory_id="t-exp", model="m",
        recovers_public_solution=True,
        exploit_score=0.85, intended_score=0.50,
    )
    v = audit([exposed])[0]
    assert not v.valid
    assert v.exposed
    assert HackType.RECOVERS_PUBLIC_SOLUTION in v.exposed_types


def test_gap_inflated_trajectory_invalid():
    """无暴露但 mislead_gap >0.02 → invalid。"""
    gap = TrajectoryAudit(
        trajectory_id="t-gap", model="m", exploit_score=0.80, intended_score=0.60
    )
    v = audit([gap])[0]
    assert not v.valid
    assert v.mislead_gap == pytest.approx(0.20)


def test_all_hack_types_classified():
    """五种暴露类型必须全部分类。"""
    all_exposed = TrajectoryAudit(
        trajectory_id="t-all", model="m",
        recovers_public_solution=True, reads_eval_artifact=True,
        infers_generator_structure=True, manipulates_feedback=True,
        benefits_invalid_scoring=True,
        exploit_score=0.90, intended_score=0.40,
    )
    v = audit([all_exposed])[0]
    assert len(v.exposed_types) == 5
    assert set(v.exposed_types) == set(HackType)


def test_exposed_types_enum_values():
    """枚举值必须是 HackDetect 分类字符串。"""
    assert HackType.RECOVERS_PUBLIC_SOLUTION.value == "recovers_public_solution"
    assert HackType.READS_EVAL_ARTIFACT.value == "reads_eval_artifact"
    assert HackType.INFERS_GENERATOR_STRUCTURE.value == "infers_generator_structure"
    assert HackType.MANIPULATES_FEEDBACK.value == "manipulates_feedback"
    assert HackType.BENEFITS_INVALID_SCORING.value == "benefits_invalid_scoring"
