"""Judge 校准系数估计器测试——RED→GREEN。"""
import pytest

from eval_meta.judge import estimate_calibration


def test_estimator_recovers_known_biases():
    """最小二乘估计器必须恢复注入的已知偏差。

    注入：position_bias=0.10, length_bias=0.05, self_bias=0.20, authority_bias=0.02。
    """
    n = 100
    raw, positions, lengths, self_flags, auth_flags = [], [], [], [], []
    rng = __import__("random").Random(42)
    for i in range(n):
        pos = i % 3
        length = rng.uniform(100, 1000)
        is_self = i % 4 == 0
        is_auth = i % 5 == 0
        # 已知真实偏差 + 噪声
        score = 5.0 + 0.10 * pos + 0.05 * (length / 1000) + 0.20 * int(is_self) + 0.02 * int(is_auth) + rng.gauss(0, 0.05)
        raw.append(score)
        positions.append(pos)
        lengths.append(length)
        self_flags.append(is_self)
        auth_flags.append(is_auth)

    cal = estimate_calibration(
        "judge-est", raw_scores=raw, positions=positions, lengths=lengths,
        self_flags=self_flags, authority_flags=auth_flags,
    )
    assert cal.calibrated
    # 系数恢复在 ±0.05 内（噪声 0.05，样本 100）
    assert cal.position_bias == pytest.approx(0.10, abs=0.05)
    assert cal.length_bias == pytest.approx(0.05, abs=0.05)
    assert cal.self_bias == pytest.approx(0.20, abs=0.05)
    assert cal.authority_bias == pytest.approx(0.02, abs=0.05)


def test_estimator_requires_min_samples():
    """样本量 < 30 不算已校准。"""
    cal = estimate_calibration(
        "judge-low", raw_scores=[5.0] * 10, positions=[0] * 10,
        lengths=[500.0] * 10, self_flags=[False] * 10, authority_flags=[False] * 10,
    )
    assert not cal.calibrated
    assert cal.n_calibration == 10


def test_estimator_zero_bias_when_clean():
    """无偏差的合成数据必须估计出接近零的系数。"""
    n = 60
    raw = [5.0 + 0.01 * (i % 7) for i in range(n)]
    positions = [0] * n
    lengths = [300.0 + 50.0 * (i % 8) for i in range(n)]  # 有方差，避免与截距共线
    self_flags = [False] * n
    auth_flags = [False] * n
    cal = estimate_calibration(
        "judge-clean", raw_scores=raw, positions=positions, lengths=lengths,
        self_flags=self_flags, authority_flags=auth_flags,
    )
    assert cal.calibrated
    assert abs(cal.position_bias) < 0.02
    assert abs(cal.length_bias) < 0.02
    assert abs(cal.self_bias) < 0.02
    assert abs(cal.authority_bias) < 0.02
