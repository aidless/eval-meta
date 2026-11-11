# P4 per-edit 信任度打分器测试：消费 evoagent 的 .evo/verdicts.jsonl。
# 证据口径：arXiv:2604.25850（AHE）实测 fix 预测 precision 33.7% / recall 51.4%，
# regression 预测 11.8% / 11.1%（回归盲区）；故低样本一律 NOT_ASSESSED，
# 回归率高的编辑类别直接判不可信，绝不因为「通过了安全门」就抬信任。
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from eval_meta.trust import (  # noqa: E402
    TrustScore, load_verdicts, score_history, score_kind,
)


def _rows(n, *, kind="tool", verdict="effective_fix", precision=0.8, valid=True):
    return [
        {"run_id": f"r{i}", "candidate_id": f"c{i}", "valid": valid,
         "prediction_precision": precision if valid else None,
         "edits": ([{"edit_id": "e1", "kind": kind, "verdict": verdict,
                     "prediction_precision": precision}] if valid else []),
         "reasons": [] if valid else ["change_manifest_malformed"]}
        for i in range(n)
    ]


def test_low_sample_is_third_state():
    # GREEN：证据不足是 NOT_ASSESSED，不是「可信」
    s = score_kind(_rows(2), "tool")
    assert s.level == "NOT_ASSESSED"
    assert "insufficient_evidence" in s.reasons


def test_clean_kind_trusted():
    # GREEN：8 次有效编辑、高精度、零回归 → L1
    s = score_kind(_rows(8), "tool")
    assert s.level == "L1"
    assert s.n_edits == 8
    assert s.mean_precision == pytest.approx(0.8)
    assert s.regression_rate == 0.0


def test_regression_heavy_kind_untrusted():
    # GREEN：回归率高 → L3（AHE 的回归盲区不能靠成功率掩盖）
    rows = _rows(8, verdict="regression", precision=0.9)
    s = score_kind(rows, "tool")
    assert s.level == "L3"
    assert s.regression_rate == 1.0
    assert "regression_rate_high" in s.reasons


def test_blind_prediction_low_precision():
    # GREEN：预测精度接近随机基线 → 至少 L2，绝不 L1
    s = score_kind(_rows(8, precision=0.10), "tool")
    assert s.level in ("L2", "L3")
    assert "low_prediction_precision" in s.reasons


def test_invalid_rows_are_governance_events_not_evidence():
    # GREEN：fail-closed 的畸形 manifest 不算编辑证据，但计数可见
    rows = _rows(6) + _rows(4, valid=False)
    s = score_kind(rows, "tool")
    assert s.n_edits == 6
    assert s.invalid == 4
    assert s.level == "L1"


def test_load_verdicts_skips_bad_lines(tmp_path: Path):
    # GREEN：JSONL 坏行跳过，不因一行损坏整份账本不可用
    path = tmp_path / "verdicts.jsonl"
    good = _rows(1)[0]
    path.write_text(json.dumps(good) + "\n{bad json\n" + json.dumps(good) + "\n",
                    encoding="utf-8")
    rows = load_verdicts(path)
    assert len(rows) == 2
    assert path.name == "verdicts.jsonl"


def test_missing_history_is_not_assessed():
    # GREEN：文件不存在 → 第三态，绝不静默判可信
    assert load_verdicts("/nonexistent/verdicts.jsonl") == []
    report = score_history([])
    assert report["verdict"] == "NOT_ASSESSED"


def test_score_history_block_wins_over_warn():
    # GREEN：任一类 L3 → 整体 BLOCK（不能被其他类的 L1 稀释）
    rows = _rows(8, kind="tool") + _rows(8, kind="prompt", verdict="regression")
    report = score_history(rows)
    assert report["verdict"] == "BLOCK"
    assert report["kinds"]["tool"]["level"] == "L1"
    assert report["kinds"]["prompt"]["level"] == "L3"


def test_selftest_returns_zero_and_cli_selftest_is_green():
    # GREEN：模块自带 RED 夹具（注入违规必须能红）+ CLI 全模块自检 exit 0
    from eval_meta.trust import _run_selftest
    assert _run_selftest() == 0
    result = subprocess.run(
        [sys.executable, "-m", "eval_meta.cli", "selftest"],
        capture_output=True, text=True, cwd=str(ROOT))
    assert result.returncode == 0, result.stderr
    assert "trust" in result.stdout


def test_trust_score_to_dict_roundtrip():
    s = score_kind(_rows(8), "tool")
    d = s.to_dict()
    assert d["kind"] == "tool" and d["level"] == "L1"
    assert isinstance(s, TrustScore)
