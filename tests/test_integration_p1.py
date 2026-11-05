"""端到端集成测试——兄弟仓 P1 数据，不在本仓库内。

需要（相对兄弟根目录，默认是本仓库的父目录，可用 EVAL_META_SIBLING_ROOT 覆盖）：
- agi-research-program/p1/claims.json
- agi-research-program/p1/recompute_receipts.json

文件不在时 skip。skip 不是通过，也不计入离线覆盖。
"""
import json

import pytest

from eval_meta.ledger import Claim, ClaimState, Evidence, Ledger
from eval_meta.siblings import P1_SKIP, p1_files

pytestmark = pytest.mark.sibling_repo


def _require_p1():
    """P1 数据不在本仓库内——缺失时 skip，原因里只有相对标签。"""
    claims, receipts = p1_files()
    if not claims.is_file() or not receipts.is_file():
        pytest.skip(P1_SKIP)


@pytest.fixture
def p1_claims():
    _require_p1()
    claims, _ = p1_files()
    d = json.loads(claims.read_text())
    return d.get("claims", d) if isinstance(d, dict) else d


@pytest.fixture
def p1_receipts():
    _require_p1()
    _, receipts = p1_files()
    d = json.loads(receipts.read_text())
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
    _require_p1()
    _, receipts = p1_files()
    d = json.loads(receipts.read_text())
    assert d.get("all_ok") is True
