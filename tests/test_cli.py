"""CLI 测试——流水线入口。"""
import subprocess
import sys
from pathlib import Path


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
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.returncode == 0, result.stderr
