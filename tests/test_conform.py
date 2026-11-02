"""抗污染门测试——RED→GREEN 双验证。

按 AGENTS.md 第 21 条：每条断言都要先失败后通过，注入违规必须 exit≠0。
"""
import pytest

from eval_meta.conform import ModelPerformance, detect


# ---- GREEN：合规输入必须放行 ----

def test_clean_model_not_contaminated():
    """无污染模型（泛化面在 base 的 1% 内）必须判 L1/clean。"""
    clean = ModelPerformance(
        model="clean-model", base=0.80, rewritten=0.795, synthetic=0.798, cross_bench=0.796, n=100
    )
    v = detect([clean])[0]
    assert not v.contaminated
    assert v.level == "L1"


def test_expansion_is_relative_not_absolute():
    """污染膨胀是相对量：base 高但泛化面绝对差 0.03 是 3.75% 相对差。

    回归测试：绝对差 0.03 曾误判 L3（阈值 0.01 绝对差），
    修正后 3.75% 相对差落在 L2（2%-10% 可疑），绝不判 L3。
    """
    model = ModelPerformance(
        model="relative-check", base=0.80, rewritten=0.78, synthetic=0.79, cross_bench=0.77, n=100
    )
    v = detect([model])[0]
    # expansion = 0.03, ratio = 3.75% → L2（可疑），不是 L3（红线）
    assert v.level != "L3"
    assert v.level == "L2"


def test_inverted_model_not_contaminated():
    """base 低于泛化面 = 无膨胀，不能判污染。"""
    inverted = ModelPerformance(
        model="inverted", base=0.60, rewritten=0.75, synthetic=0.78, cross_bench=0.80, n=100
    )
    v = detect([inverted])[0]
    assert not v.contaminated
    assert v.expansion < 0


# ---- RED：违规输入必须报红 ----

def test_high_contamination_detected():
    """高污染模型（相对衰减 >10%）必须判 L3。"""
    dirty = ModelPerformance(
        model="dirty", base=0.85, rewritten=0.60, synthetic=0.55, cross_bench=0.50, n=100
    )
    v = detect([dirty])[0]
    assert v.contaminated
    assert v.level == "L3"
    # 精确值逐字复制：expansion = 0.85 - 0.50 = 0.35, ratio = 0.35/0.85
    assert v.expansion == pytest.approx(0.35)
    assert v.ratio == pytest.approx(0.35 / 0.85)


def test_mid_contamination_detected():
    """中污染模型（相对衰减 2-10%）必须判 L2。"""
    mid = ModelPerformance(
        model="mid", base=0.85, rewritten=0.82, synthetic=0.80, cross_bench=0.84, n=100
    )
    v = detect([mid])[0]
    assert v.contaminated
    assert v.level == "L2"
    # expansion = 0.85 - 0.80 = 0.05, ratio = 5.88%
    assert v.expansion == pytest.approx(0.05)
    assert v.ratio == pytest.approx(0.05 / 0.85)


def test_batch_detect_returns_one_per_model():
    """批量检测：每个模型返回一个 verdict。"""
    models = [
        ModelPerformance("a", base=0.80, rewritten=0.795, synthetic=0.798, cross_bench=0.796, n=50),
        ModelPerformance("b", base=0.85, rewritten=0.60, synthetic=0.55, cross_bench=0.50, n=50),
    ]
    vs = detect(models)
    assert len(vs) == 2
    assert vs[0].model == "a"
    assert vs[1].model == "b"
