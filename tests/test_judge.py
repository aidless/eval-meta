"""Judge 校准层测试——RED→GREEN 双验证。"""
import pytest

from eval_meta.judge import JudgeCalibration, ScoredResponse, correct


@pytest.fixture
def calibrated_judge():
    return JudgeCalibration(
        judge="judge-A", position_bias=0.10, length_bias=0.05,
        self_bias=0.20, authority_bias=0.02, n_calibration=100, tau=0.62, calibrated=True,
    )


# ---- GREEN：合规输入必须放行 ----

def test_corrected_score_deducts_bias(calibrated_judge):
    """已校准 judge 正确扣减偏差：8.0 - (0.10+0.05+0.20+0.02) = 7.63。"""
    s = ScoredResponse(response_id="r1", judge="judge-A", model="m", raw_score=8.0,
                       position=0, length_chars=500, is_self_family=False)
    r = correct([s], [calibrated_judge])[0]
    assert not r.preference_leakage
    assert r.corrected_score == pytest.approx(7.63)


def test_corrected_score_floor_at_zero(calibrated_judge):
    """扣减后得分不为负。"""
    s = ScoredResponse(response_id="r2", judge="judge-A", model="m", raw_score=0.5,
                       is_self_family=False)
    r = correct([s], [calibrated_judge])[0]
    assert r.corrected_score >= 0


# ---- RED：违规输入必须报红 ----

def test_self_family_flag_preference_leakage(calibrated_judge):
    """同族偏好必须判红。"""
    s = ScoredResponse(response_id="r3", judge="judge-A", model="m-same",
                       raw_score=8.5, is_self_family=True)
    r = correct([s], [calibrated_judge])[0]
    assert r.preference_leakage


def test_uncalibrated_judge_no_deduction_but_flags_leakage():
    """未校准 judge 不做偏差校正，但同族偏好仍判红。"""
    s = ScoredResponse(response_id="r4", judge="judge-B", model="m-same",
                       raw_score=8.0, is_self_family=True)
    r = correct([s], [])[0]
    assert r.corrected_score == pytest.approx(8.0)  # 未校准不扣
    assert r.preference_leakage


def test_calibration_requires_min_samples():
    """n_calibration < 30 不算已校准。"""
    low = JudgeCalibration(judge="judge-C", n_calibration=10)
    assert not low.calibrated
