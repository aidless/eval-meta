"""证据链 ledger 测试——RED→GREEN。"""

from eval_meta.ledger import (
    Claim, ClaimState, Evidence, Ledger,
)


def test_claim_with_evidence_verifiable():
    """带证据的 claim → 可核查。"""
    ledger = Ledger()
    ledger.add(Claim("c1", "MMLU GPT-4 2023 ~86%", 0.86, "score",
                     Evidence("benchmarks/mmlu.csv", "row:gpt4-2023"), ClaimState.SUPPORTED))
    report = ledger.verify()
    assert report["all_verifiable"]
    assert report["supported"] == 1


def test_no_evidence_claim_marked_missing():
    """无证据 claim → 必须标记为 missing（无法追溯 = 删除候选）。"""
    ledger = Ledger()
    ledger.add(Claim("c3", "某模型 100% 准确率", 1.0, "score", None))
    report = ledger.verify()
    assert not report["all_verifiable"]
    assert report["missing"] == 1
    assert "c3" in report["unverifiable"]


def test_recompute_detects_mismatch():
    """独立重算必须能抓到不一致。"""
    ledger = Ledger()
    ledger.add(Claim("c4", "某模型 0.80", 0.80, "score",
                     Evidence("out.json", "score"), ClaimState.SUPPORTED))
    report = ledger.recompute(lambda c: 0.85)
    assert report["recompute_mismatch"] == 1
    assert report["mismatches"][0]["claim_id"] == "c4"


def test_recompute_match():
    """独立重算一致 → 通过。"""
    ledger = Ledger()
    ledger.add(Claim("c4", "某模型 0.80", 0.80, "score",
                     Evidence("out.json", "score"), ClaimState.SUPPORTED))
    report = ledger.recompute(lambda c: 0.80)
    assert report["recompute_match"] == 1


def test_recompute_unavailable_for_no_evidence():
    """无证据 claim → 重算不可用。"""
    ledger = Ledger()
    ledger.add(Claim("c5", "无载体声明", 0.50, "score", None))
    report = ledger.recompute(lambda c: 0.50)
    assert report["recompute_unavailable"] == 1


def test_ledger_save_load_roundtrip(tmp_path):
    """保存/加载往返。"""
    ledger = Ledger()
    ledger.add(Claim("c1", "MMLU GPT-4 2023 ~86%", 0.86, "score",
                     Evidence("benchmarks/mmlu.csv", "row:gpt4-2023"), ClaimState.SUPPORTED))
    path = str(tmp_path / "ledger.json")
    ledger.save(path)
    loaded = Ledger.load(path)
    assert loaded.entries[0].claim_id == "c1"
    assert loaded.entries[0].value == 0.86
    assert loaded.entries[0].evidence.path == "benchmarks/mmlu.csv"
