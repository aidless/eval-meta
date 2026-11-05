"""Judge 校准层测试——RED→GREEN 双验证。"""
import pytest

from eval_meta.judge import JudgeCalibration, JudgeCertification, ScoredResponse, certify_judge, correct


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


def _score(self_family: bool = False, raw: float = 9.5) -> ScoredResponse:
    return ScoredResponse(
        response_id="r", judge="judge-A", model="m", raw_score=raw, is_self_family=self_family,
    )


def test_low_tau_record_is_refused():
    """高分且未标同族，但 tau 低于本地门槛 → 拒绝，不得认证。"""
    cal = JudgeCalibration(
        judge="judge-A", position_bias=0.4, length_bias=0.3, self_bias=0.5,
        authority_bias=0.2, n_calibration=100, tau=0.05, calibrated=True,
    )
    cert = certify_judge(cal, [_score()], source="caller_supplied")
    assert cert.certified is False
    assert cert.status == "REFUSED"
    assert cert.reason == "tau_below_floor"


def test_self_family_is_refused_even_with_high_tau():
    """同族标记优先于高 tau：拒绝，而不是认证。"""
    cal = JudgeCalibration(
        judge="judge-A", n_calibration=100, tau=0.90, calibrated=True,
    )
    cert = certify_judge(cal, [_score(self_family=True)], source="caller_supplied")
    assert cert == JudgeCertification(status="REFUSED", reason="preference_leakage", certified=False)


def test_uncalibrated_record_is_refused():
    """样本量不足或未校准 → 拒绝。"""
    cal = JudgeCalibration(judge="judge-C", n_calibration=10, tau=0.90, calibrated=False)
    cert = certify_judge(cal, [_score()], source="caller_supplied")
    assert cert.status == "REFUSED"
    assert cert.reason == "uncalibrated"
    assert cert.certified is False


def test_scripted_demo_is_not_a_certificate():
    """流水线里的演示系数是脚本，不是测量。"""
    cal = JudgeCalibration(
        judge="demo-judge", n_calibration=100, tau=0.90, calibrated=True,
    )
    cert = certify_judge(cal, [_score(raw=7.5)], source="scripted")
    assert cert.status == "UNVERIFIED"
    assert cert.reason == "scripted_demo"
    assert cert.certified is False


def test_high_tau_caller_record_stays_unverified():
    """看起来很好的调用方记录仍然不是独立认证。"""
    cal = JudgeCalibration(
        judge="judge-A", n_calibration=100, tau=0.90, calibrated=True,
    )
    cert = certify_judge(cal, [_score()], source="caller_supplied")
    assert cert.status == "UNVERIFIED"
    assert cert.reason == "caller_supplied_calibration"
    assert cert.certified is False
    assert "independent" not in cert.reason
