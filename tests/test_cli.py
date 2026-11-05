"""CLI 测试——流水线入口。"""
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "eval_meta.cli", *args],
        capture_output=True, text=True, cwd=str(ROOT),
    )


def test_cli_pipeline_runs():
    """CLI 流水线能跑通（返回 exit 0，输出合法 JSON）。"""
    result = subprocess.run(
        [sys.executable, "-m", "eval_meta.cli", "pipeline"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stderr


def test_cli_pipeline_outputs_json():
    """CLI 流水线输出合法 JSON。"""
    result = subprocess.run(
        [sys.executable, "-m", "eval_meta.cli", "pipeline"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    import json
    d = json.loads(result.stdout)
    assert "stages" in d
    assert "verdict" in d
    assert len(d["stages"]) == 7


def test_cli_selftest_all():
    """CLI 全模块自检返回 exit 0。"""
    result = subprocess.run(
        [sys.executable, "-m", "eval_meta.cli", "selftest"],
        capture_output=True, text=True,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stderr


def _stage(report: dict, name: str) -> dict:
    return next(s for s in report["stages"] if s["stage"] == name)


def test_demo_pipeline_does_not_certify_the_judge():
    """脚本演示不得把 judge 阶段报成 PASS，总判决也不得是 PASS。"""
    result = _run("pipeline")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["data_mode"] == "demo"
    assert report["sibling_repos_used"] is False
    judge = _stage(report, "judge")
    assert judge["verdict"] == "SCRIPTED"
    assert judge["evidence"] == "scripted"
    assert judge["certification"]["certified"] is False
    assert judge["certification"]["reason"] == "scripted_demo"
    assert report["verdict"] != "PASS"
    assert all(s["verdict"] != "PASS" for s in report["stages"])


def test_offline_refuses_inrepo_bad_judge(tmp_path, monkeypatch):
    """离线入口只读仓内夹具，低 tau 的坏 judge 被拒绝，且不访问兄弟仓。"""
    monkeypatch.setenv("EVAL_META_SIBLING_ROOT", str(tmp_path / "no-siblings"))
    result = _run("offline")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["data_mode"] == "offline_fixture"
    assert report["sibling_repos_used"] is False
    assert report["fixture"] == "fixtures/offline/bad_judge.json"
    assert report["certified"] is False
    assert report["verdict"] == "REFUSED"
    assert report["reason"] == "tau_below_floor"
    assert (ROOT / report["fixture"]).is_file()
    assert not report["fixture"].startswith("/")
    assert ("/" + "Users/") not in result.stdout
    assert ("/" + "home/") not in result.stdout


def test_partial_receipts_do_not_perfect_the_probe(tmp_path):
    """一半 receipt 对上时，探针不得报成完美，judge 仍不得 PASS。"""
    claims = {
        "claims": [
            {"id": "c1", "claim": "one", "evidence": "e", "locator": "L1", "status": "verified"},
            {"id": "c2", "claim": "two", "evidence": "e", "locator": "L2", "status": "verified"},
        ]
    }
    receipts = {
        "all_ok": False,
        "receipts": [{"claim": "c1", "ok": True, "computed": {"value": 1}}],
    }
    claims_path = tmp_path / "claims.json"
    receipts_path = tmp_path / "receipts.json"
    claims_path.write_text(json.dumps(claims))
    receipts_path.write_text(json.dumps(receipts))
    result = _run("pipeline", "--claims", str(claims_path), "--receipts", str(receipts_path))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["data_mode"] == "real"
    assert report["sibling_repos_used"] is False
    audit = _stage(report, "selfaudit")
    assert audit["evidence"] == "measured"
    assert audit["verdict"] == "WARN"
    assert audit["details"]["match_rate"] == 0.5
    assert audit["details"]["probe_within_tolerance"] is False
    assert audit["details"]["not_a_judge_certificate"] is True
    assert _stage(report, "judge")["verdict"] != "PASS"
    assert report["verdict"] != "PASS"


def test_full_receipt_match_still_does_not_certify_the_judge(tmp_path):
    """收据全部对上只说明证据链探针，不能把整条流水线或 judge 报成通过。"""
    claims = {
        "claims": [
            {"id": "c1", "claim": "one", "evidence": "e", "locator": "L1", "status": "verified"},
        ]
    }
    receipts = {
        "all_ok": True,
        "receipts": [{"claim": "c1", "ok": True, "computed": {"value": 1}}],
    }
    claims_path = tmp_path / "claims.json"
    receipts_path = tmp_path / "receipts.json"
    claims_path.write_text(json.dumps(claims))
    receipts_path.write_text(json.dumps(receipts))
    result = _run("pipeline", "--claims", str(claims_path), "--receipts", str(receipts_path))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    audit = _stage(report, "selfaudit")
    assert audit["verdict"] == "PASS"
    assert audit["details"]["match_rate"] == 1.0
    assert audit["details"]["not_a_judge_certificate"] is True
    assert _stage(report, "ledger")["verdict"] == "PASS"
    assert _stage(report, "ledger")["evidence"] == "measured"
    assert _stage(report, "judge")["verdict"] == "SCRIPTED"
    assert _stage(report, "conform")["evidence"] == "scripted"
    assert report["verdict"] != "PASS"
