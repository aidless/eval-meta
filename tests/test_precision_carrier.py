# P4 精度载体（precision carrier）语义测试。
#
# 缺陷（本轮用真账本发现的结构问题）：`score_kind` 原来要求
# `len(precisions) == n_edits` 才算「覆盖率完整」，而 change_manifest 对**只声明
# 回归、不声明修复**的编辑给 `prediction_precision = None`（它本来就没有修复可对账）。
# 于是只要账本里出现一笔 regression-only 编辑，该 kind 永远够不到 L1——
# 这是判据在惩罚诚实：编辑老实说「我这次只是防回归」，却被判成证据不全。
#
# 正解：覆盖率只该覆盖**声称要修复的编辑**。regression-only 编辑继续计入
# n_edits 与 regression_rate（不能靠「没预测修复」逃掉回归责任）。
#
# 夹具全部合成，不跑任何真实评测。
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval_meta.trust import score_kind  # noqa: E402


def _row(kind, verdict, precision, predicted_fix, predicted_regression=()):
    return {"valid": True, "edits": [{
        "kind": kind, "verdict": verdict, "prediction_precision": precision,
        "predicted_fix": list(predicted_fix),
        "predicted_regression": list(predicted_regression),
    }]}


def _ledger(kind, specs):
    return [_row(kind, *spec) for spec in specs]


def test_regression_only_edit_does_not_block_l1():
    # RED：4 笔有修复声明且预测准（0.75），1 笔只声明回归、实际没回归（no_effect）
    # → 覆盖率完整，回归率 0 → 应得 L1；旧实现因 precision 载体 4<5 判 L2
    rows = _ledger("memory", [
        ("effective_fix", 0.75, ["c09"]),
        ("effective_fix", 0.75, ["c10"]),
        ("effective_fix", 0.75, ["c11"]),
        ("effective_fix", 0.75, ["c12"]),
        ("no_effect", None, [], ["c05"]),
    ])
    score = score_kind(rows, "memory")
    assert score.n_edits == 5, "regression-only 编辑仍须计入分母"
    assert score.level == "L1", score.to_dict()
    assert "incomplete_precision_coverage" not in score.reasons


def test_fix_claim_without_precision_still_blocks_l1():
    # GREEN 守卫：只要有一笔声称修复却拿不到精度载体，覆盖率就不完整 → L2
    rows = _ledger("tool", [
        ("effective_fix", 0.75, ["c09"]),
        ("effective_fix", 0.75, ["c10"]),
        ("effective_fix", 0.75, ["c11"]),
        ("effective_fix", 0.75, ["c12"]),
        ("effective_fix", None, ["c13"]),
    ])
    score = score_kind(rows, "tool")
    assert score.level == "L2", score.to_dict()
    assert "incomplete_precision_coverage" in score.reasons


def test_kind_without_any_fix_claim_is_not_l1():
    # RED：整类编辑从不声称修复（纯防回归）→ 没有精度证据，不能判 L1
    rows = _ledger("subagent", [("no_effect", None, [], ["c05"])] * 5)
    score = score_kind(rows, "subagent")
    assert score.level == "L2", score.to_dict()
    assert "no_fix_claims" in score.reasons


def test_regression_only_edits_count_toward_regression_rate():
    # GREEN 守卫：regression-only 不能靠「没预测修复」逃掉回归责任 → L3
    rows = _ledger("workflow", [
        ("regression", None, [], ["c05"]),
        ("regression", None, [], ["c06"]),
        ("regression", None, [], ["c07"]),
        ("regression", None, [], ["c08"]),
        ("effective_fix", 0.9, ["c09"]),
    ])
    score = score_kind(rows, "workflow")
    assert score.n_edits == 5
    assert score.level == "L3", score.to_dict()
    assert "regression_rate_high" in score.reasons
