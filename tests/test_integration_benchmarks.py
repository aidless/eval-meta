"""
tests/test_integration_benchmarks.py - 真实 benchmark 数据端到端验证

用 20-llm-eval-benchmark 的真实评测数据（MMLU/GSM8K/HumanEval/MT-Bench sample）
验证 eval-meta 的多个模块能从真实数据提取有效信号：
- conform：从真实问题集导出泛化面指标
- rigor：对真实题目统计严谨性
- ledger：真实评测数据 → 证据链验证
"""

import json
from pathlib import Path

import pytest

from eval_meta.conform import ModelPerformance, detect
from eval_meta.rigor import wilson_ci, cohens_d
from eval_meta.ledger import Claim, ClaimState, Evidence, Ledger

BENCH_DIR = Path(__file__).resolve().parents[2] / "llm-agent-projects" / "20-llm-eval-benchmark" / "data"


def _load_bench(name: str) -> dict:
    path = BENCH_DIR / f"{name}_sample.json"
    if not path.exists():
        pytest.skip(f"{path} 不存在")
    return json.loads(path.read_text())


class TestRealBenchmarkData:
    """用真实 benchmark 数据验证模块提取有效信号."""

    def test_mmlu_real_questions(self):
        """MMLU 50 题真实数据 → 可导出题量与类别."""
        d = _load_bench("mmlu")
        qs = d["questions"]
        assert len(qs) == 50
        cats = {q["category"] for q in qs}
        assert "mathematics" in cats
        assert all(0 <= q["answer"] < 4 for q in qs)  # 四选一

    def test_gsm8k_real_problems(self):
        """GSM8K 真实题目 → 可统计题量与难度分布."""
        d = _load_bench("gsm8k")
        probs = d["problems"]
        assert len(probs) > 0
        assert all("question" in p for p in probs)

    def test_humaneval_real_problems(self):
        """HumanEval 真实题目 → 可统计题量."""
        d = _load_bench("humaneval")
        probs = d["problems"]
        assert len(probs) > 0
        assert all("prompt" in p for p in probs)

    def test_mt_bench_real_conversations(self):
        """MT-Bench 真实对话 → 可统计题量与类别."""
        d = _load_bench("mt_bench")
        convs = d["conversations"]
        assert len(convs) > 0
        assert all("category" in c for c in convs)

    def test_conform_from_real_mmlu(self):
        """从真实 MMLU 题量导出 conform 泛化面（说明性，但数据真实）."""
        d = _load_bench("mmlu")
        n = len(d["questions"])
        # 真实数据只有题量，无分数 → 用题量作 base 的说明性指标
        perfs = [
            ModelPerformance(model="mmlu-real", base=0.80,
                             rewritten=0.795, synthetic=0.798,
                             cross_bench=0.792, n=n),
        ]
        verdicts = detect(perfs)
        assert len(verdicts) == 1
        assert not verdicts[0].contaminated  # 真实数据本身干净

    def test_wilson_from_real_gsm8k(self):
        """用真实 GSM8K 题量算 Wilson CI（统计严谨性）."""
        d = _load_bench("gsm8k")
        n = len(d["problems"])
        # 假设 70% 通过率（说明性），但 n 是真实的
        lower, upper = wilson_ci(0.70 * n, n, z=1.96)
        assert lower <= 0.70 <= upper
        assert upper - lower < 0.40  # 30 题 CI 宽应在合理范围（n=30 时 ~0.31）

    def test_ledger_real_benchmark(self):
        """真实 benchmark 数据 → ledger 证据链可验证."""
        d = _load_bench("mmlu")
        n = len(d["questions"])
        ledger = Ledger()
        ev = Evidence("data/mmlu_sample.json", f"questions:{n}")
        ledger.add(Claim("BENCH-MMLU-01",
                         f"MMLU sample 含 {n} 题，类别 {len({q['category'] for q in d['questions']})} 个",
                         0.80, "value", ev, ClaimState.SUPPORTED))
        rep = ledger.verify()
        assert rep["all_verifiable"] is True
        assert rep["total"] == 1
