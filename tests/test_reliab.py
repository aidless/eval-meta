"""可靠性估计器测试——RED→GREEN。"""
import pytest

from eval_meta.reliab import (
    estimate_reliability, sample_size_for_reliability,
)


def test_sample_size_positive():
    """五九目标需要大量样本（正数）。"""
    n = sample_size_for_reliability(0.99999, 0.95)
    assert n > 0
    assert n > 100000  # 五九需要约 30 万样本


def test_sample_size_increases_with_reliability():
    """目标可靠度越高，所需样本量越大。"""
    n_three_nines = sample_size_for_reliability(0.999, 0.95)
    n_five_nines = sample_size_for_reliability(0.99999, 0.95)
    assert n_five_nines > n_three_nines


def test_meets_target_with_sufficient_clean_samples():
    """样本量足够且无故障 → 达到五九目标。"""
    n = int(sample_size_for_reliability(0.99999, 0.95)) + 10
    est = estimate_reliability([True] * n, target_reliability=0.99999)
    assert est.meets_target


def test_insufficient_samples_not_meet_target():
    """样本量不足 → 即使全成功也不能声称达到目标。"""
    est = estimate_reliability([True] * 100, target_reliability=0.99999)
    assert not est.meets_target


def test_failures_reject_target():
    """有故障 → 未达到目标。"""
    est = estimate_reliability([True] * 999 + [False], target_reliability=0.99999)
    assert not est.meets_target


def test_empty_results():
    """空结果 → 不可达。"""
    est = estimate_reliability([], target_reliability=0.99999)
    assert not est.meets_target
    assert est.total == 0
