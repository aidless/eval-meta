"""统计严谨门测试——RED→GREEN。"""
import pytest

from eval_meta.rigor import (
    AgreementDecision, cohens_d, kappa_touch_report, wilson_ci,
)


# ---- Wilson CI ----

def test_wilson_ci_contains_point_estimate():
    lo, hi = wilson_ci(80, 100)
    assert lo <= 0.80 <= hi


def test_wilson_ci_empty_n():
    lo, hi = wilson_ci(0, 0)
    assert lo == 0 and hi == 0


def test_wilson_ci_bounded():
    lo, hi = wilson_ci(100, 100)
    assert lo >= 0 and hi <= 1.0
    # 边界在 float 精度内（1.0 可能表现为 0.9999999999999999）
    assert hi == pytest.approx(1.0, abs=1e-9)


# ---- Cohen's d ----

def test_cohens_d_positive_when_a_greater():
    d = cohens_d([1.0, 2.0, 3.0, 4.0], [1.0, 1.0, 1.0, 1.0])
    assert d > 0


def test_cohens_d_zero_when_identical():
    d = cohens_d([2.0, 2.0, 2.0], [2.0, 2.0, 2.0])
    assert d == 0.0


# ---- κ 触及报告 ----

def test_kappa_report_no_touching_rule():
    """无触及规则 → 不充高。"""
    decisions = [
        AgreementDecision(f"d{i}", judge_verdict=(i % 3 == 0), human_verdict=(i % 3 == 0), touched=False)
        for i in range(30)
    ]
    r = kappa_touch_report(decisions)
    assert not r.kappa_inflated_by_touching
    assert r.untouched_count == 30


def test_kappa_report_flags_inflation():
    """触及规则充高 κ（touched >> untouched）→ 必须警告。"""
    touched = [AgreementDecision(f"t{i}", True, True, touched=True, by_construction=True) for i in range(20)]
    untouched = [AgreementDecision(f"u{i}", i % 2 == 0, i % 2 == 1, touched=False) for i in range(20)]
    r = kappa_touch_report(touched + untouched)
    assert r.kappa_inflated_by_touching
    assert r.warning is not None
    # 充高判据：被触及 κ 明显高于未触及（Agreement by Construction 0.056→0.714 vs 0.064）
    assert r.kappa_touched > r.kappa_untouched + 0.1


def test_kappa_report_counts_separate():
    """报告必须区分被触及/未触及判决数。"""
    touched = [AgreementDecision(f"t{i}", True, True, touched=True) for i in range(10)]
    untouched = [AgreementDecision(f"u{i}", True, True, touched=False) for i in range(15)]
    r = kappa_touch_report(touched + untouched)
    assert r.touched_count == 10
    assert r.untouched_count == 15
    assert r.total == 25
