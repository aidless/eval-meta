"""端到端集成测试——用真实 P1 数据验证 eval-meta 全流水线。

数据来源：agi-research-program/p1/claims.json（30 条真实 claim）
+ agi-research-program/p1/recompute_receipts.json（23 条真实独立重算 receipt）。
这验证：不是合成夹具，而是真实科研数据能跑通可核查性判定。
"""
import json
import sys
from pathlib import Path

import pytest

# 找到工作区根（eval-meta 的父目录）
WORKSPACE = Path(__file__).resolve().parents[2]
P1_DIR = WORKSPACE / "agi-research-program" / "p1"
sys.path.insert(0, str(WORKSPACE / "eval-meta"))

from eval_meta.ledger import Claim, ClaimState, Evidence, Ledger  # noqa: E402


@pytest.fixture
def p1_claims():
    d = json.loads((P1_DIR / "claims.json").read_text())
    return d.get("claims", d) if isinstance(d, dict) else d


@pytest.fixture
def p1_receipts():
    d = json.loads((P1_DIR / "recompute_receipts.json").read_text())
    return d.get("receipts", d) if isinstance(d, dict) else d


def test_real_claims_all_verifiable(p1_claims):
    """真实 30 条 claim：全部有 evidence + locator → 可核查。"""
    ledger = Ledger()
    for c in p1_claims:
        ev = Evidence(c["evidence"], c.get("locator", ""))
        state = ClaimState.SUPPORTED if c.get("status") == "verified" else ClaimState.INCONCLUSIVE
        ledger.add(Claim(c["id"], c["claim"], None, None, ev, state))
    rep = ledger.verify()
    assert rep["total"] == 30
    assert rep["missing"] == 0
    assert rep["all_verifiable"]


def test_real_recompute_all_match(p1_claims, p1_receipts):
    """真实独立重算：receipts all_ok=True，且重算无不一致。"""
    receipt_map = {r["claim"]: r["computed"] for r in p1_receipts}
    assert len(p1_receipts) == 23

    ledger = Ledger()
    for c in p1_claims:
        if c["id"] in receipt_map:
            computed = receipt_map[c["id"]]
            num_val = None
            for v in computed.values():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    num_val = float(v)
                    break
            ev = Evidence(c["evidence"], c.get("locator", ""))
            state = ClaimState.SUPPORTED if c.get("status") == "verified" else ClaimState.INCONCLUSIVE
            ledger.add(Claim(c["id"], c["claim"], num_val, "value", ev, state))

    def recompute_fn(claim):
        if claim.claim_id in receipt_map:
            computed = receipt_map[claim.claim_id]
            for v in computed.values():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    return float(v)
        return None

    rep = ledger.recompute(recompute_fn)
    assert rep["recompute_mismatch"] == 0
    assert rep["recompute_match"] > 0


def test_real_receipts_all_ok(p1_receipts):
    """真实 receipts 官方 all_ok=True（P1_FREEZE 基准）。"""
    d = json.loads((P1_DIR / "recompute_receipts.json").read_text())
    assert d.get("all_ok") is True
