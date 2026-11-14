"""自我审计层测试——RED→GREEN。"""

from eval_meta.selfaudit import (
    FailureMode, Migration, Probe, classify_failure, run_probe_battery,
)


def test_probe_battery_healthy():
    """探针全部在容差内 → 系统健康。"""
    probes = [Probe("p1", true_value=0.80), Probe("p2", true_value=0.60)]
    report = run_probe_battery(probes, lambda p: p.true_value + 0.01)
    assert report.system_healthy
    assert report.probes_passed == 2


def test_probe_battery_detects_failure():
    """探针超出容差 → 系统不健康（系统自己失效）。"""
    probes = [Probe("p1", true_value=0.80), Probe("p2", true_value=0.60)]
    report = run_probe_battery(probes, lambda p: p.true_value + 0.10)
    assert not report.system_healthy
    assert report.probes_failed == 2
    assert len(report.failures) == 2


def test_probe_tolerance_boundary():
    """容差边界：恰好容差内 → 通过（用 pytest.approx 处理浮点边界）。"""
    p = Probe("p1", true_value=0.80, tolerance=0.02)
    assert p.is_within_tolerance(0.82)  # 恰好 +2% 边界
    assert p.is_within_tolerance(0.78)  # 恰好 -2% 边界（0.78 浮点 = 0.78000000000000002，差 0.020000000000000018）
    assert not p.is_within_tolerance(0.83)  # 超界


def test_classify_gamed():
    """被钻 → GAMED（无论迁移率）。"""
    c = classify_failure(Migration("m1", train_perf=0.90, heldout_perf=0.88, is_gamed=True))
    assert c.failure_mode == FailureMode.GAMED


def test_classify_overfit():
    """train 高、held-out 低 → OVERFIT。"""
    c = classify_failure(Migration("m2", train_perf=0.90, heldout_perf=0.60))
    assert c.failure_mode == FailureMode.OVERFIT
    assert c.migration_gap > 0.15


def test_classify_benign():
    """正常失效 → BENIGN。"""
    c = classify_failure(Migration("m3", train_perf=0.80, heldout_perf=0.75))
    assert c.failure_mode == FailureMode.BENIGN
