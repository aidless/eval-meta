"""CLI 入口——把 7 个模块串成一条评测流水线。

用法：
    python3 -m eval_meta.cli selftest                 # 全模块自检
    python3 -m eval_meta.cli offline                  # 仓内坏 judge 夹具，不读兄弟仓
    python3 -m eval_meta.cli pipeline                 # 脚本演示（不认证 judge）
    python3 -m eval_meta.cli pipeline --claims <json> --receipts <json>

流水线：conform（抗污染）→ validity（协议效度）→ rigor（统计严谨）
        → judge（校准）→ reliab（可靠性）→ selfaudit（自我审计）→ ledger（证据链）

判决词：
- PASS：这一阶段读了调用方这次给的输入，并且检查成立。不是对 judge 的认证。
- WARN：这一阶段读了输入，并且检查不成立。
- SCRIPTED：数字来自本文件里的演示字面量，或来自把 claim 数字乘上固定系数。不是测量。
- UNVERIFIED：没有足够的输入来做这一阶段的测量。
流水线总判决不是 PASS，除非七个阶段都是 PASS。judge 阶段在本入口里始终是 SCRIPTED。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())


def _numeric_values(claim: dict) -> list[float]:
    """从 claim 里提取数值字段（用于说明性指标）。"""
    out = []
    for v in claim.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            out.append(float(v))
        elif isinstance(v, dict):
            for vv in v.values():
                if isinstance(vv, (int, float)) and not isinstance(vv, bool):
                    out.append(float(vv))
    return out


def run_selftest_all() -> int:
    """全模块 --selftest。"""
    failures = 0
    modules = ["conform", "validity", "rigor", "judge", "reliab", "selfaudit", "ledger"]
    for mod in modules:
        print(f"--- {mod} ---")
        try:
            import importlib
            m = importlib.import_module(f"eval_meta.{mod}")
            if hasattr(m, "_run_selftest"):
                rc = m._run_selftest()
                if rc != 0:
                    failures += 1
            else:
                print(f"  [SKIP] no _run_selftest")
        except Exception as e:
            print(f"  [ERROR] {e}")
            failures += 1
    print(f"\n全模块自检: {'PASS' if failures == 0 else f'FAIL ({failures})'}")
    return failures


def _cert_dict(cert) -> dict:
    return {"certified": cert.certified, "status": cert.status, "reason": cert.reason}


def _append_stage(report: dict, *, stage: str, verdict: str, evidence: str,
                  details, scripted_check: str | None = None, certification: dict | None = None) -> None:
    item = {"stage": stage, "verdict": verdict, "evidence": evidence, "details": details}
    if scripted_check is not None:
        # holds/fires，不用 PASS/WARN，避免脚本结果被读成测量通过。
        if scripted_check not in {"holds", "fires"}:
            raise ValueError(scripted_check)
        item["scripted_check"] = scripted_check
    if certification is not None:
        item["certification"] = certification
    report["stages"].append(item)


def _finalize(report: dict) -> None:
    verdicts = [s["verdict"] for s in report["stages"]]
    if any(v == "WARN" for v in verdicts):
        report["verdict"] = "WARN"
    elif any(v == "REFUSED" for v in verdicts):
        report["verdict"] = "REFUSED"
    elif verdicts and all(v == "PASS" for v in verdicts):
        report["verdict"] = "PASS"
    else:
        report["verdict"] = "UNVERIFIED"


def run_offline() -> int:
    """只读仓内夹具。退出码 0 表示坏 judge 被拒绝，不表示 judge 通过。"""
    from eval_meta.judge import JudgeCalibration, ScoredResponse, certify_judge

    fixture_rel = "fixtures/offline/bad_judge.json"
    path = Path(__file__).resolve().parents[1] / fixture_rel
    data = json.loads(path.read_text())
    cal = JudgeCalibration(
        judge=data["judge"],
        position_bias=float(data["position_bias"]),
        length_bias=float(data["length_bias"]),
        self_bias=float(data["self_bias"]),
        authority_bias=float(data["authority_bias"]),
        n_calibration=int(data["n_calibration"]),
        tau=float(data["tau"]),
        calibrated=bool(data["calibrated"]),
    )
    scores = [
        ScoredResponse(
            response_id=s["response_id"],
            judge=data["judge"],
            model=s["model"],
            raw_score=float(s["raw_score"]),
            is_self_family=bool(s["is_self_family"]),
        )
        for s in data["scores"]
    ]
    cert = certify_judge(cal, scores, source="caller_supplied")
    report = {
        "data_mode": "offline_fixture",
        "fixture": fixture_rel,
        "sibling_repos_used": False,
        "certified": cert.certified,
        "verdict": cert.status,
        "reason": cert.reason,
        "note": data.get("note", ""),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if cert.certified or cert.status != "REFUSED" or cert.reason != "tau_below_floor":
        return 1
    return 0


def run_pipeline(claims_path: str | None = None,
                 receipts_path: str | None = None) -> int:
    """完整流水线。

    ``--claims`` / ``--receipts`` 只喂给 ledger 和 selfaudit 的收据一致率。
    conform 即使拿到 claims，也只是把某个数字乘上固定系数，仍然是 SCRIPTED。
    validity / rigor / judge / reliab 在这条入口里不读输入文件，永远是 SCRIPTED。
    本函数不打开兄弟仓库。
    """
    from eval_meta.conform import ModelPerformance, detect
    from eval_meta.validity import TrajectoryAudit, audit
    from eval_meta.rigor import AgreementDecision, kappa_touch_report
    from eval_meta.judge import JudgeCalibration, ScoredResponse, certify_judge, correct
    from eval_meta.reliab import estimate_reliability
    from eval_meta.selfaudit import Probe, Migration, classify_failure
    from eval_meta.ledger import Claim, ClaimState, Evidence, Ledger

    report = {
        "stages": [],
        "verdict": "UNVERIFIED",
        "data_mode": "demo",
        "sibling_repos_used": False,
    }
    real_claims = []
    real_receipts = []
    if claims_path:
        raw = _load_json(claims_path)
        real_claims = raw.get("claims", raw) if isinstance(raw, dict) else raw
        report["data_mode"] = "real"
    if receipts_path:
        raw = _load_json(receipts_path)
        real_receipts = raw.get("receipts", raw) if isinstance(raw, dict) else raw

    # ① conform。claims 存在时的系数是固定乘数，不是污染测量。
    if real_claims:
        base_val = next((float(v) for c in real_claims
                         for v in _numeric_values(c) if v is not None), 0.80)
        perfs = [
            ModelPerformance(model="p1-claims", base=base_val,
                             rewritten=base_val * 0.995, synthetic=base_val * 0.998,
                             cross_bench=base_val * 0.992, n=len(real_claims)),
        ]
        conform_note = "fixed multipliers on a claim scalar; not a contamination measurement"
    else:
        perfs = [
            ModelPerformance(model="demo-clean", base=0.80, rewritten=0.795,
                             synthetic=0.798, cross_bench=0.792, n=1000),
            ModelPerformance(model="demo-leaky", base=0.95, rewritten=0.60,
                             synthetic=0.55, cross_bench=0.50, n=1000),
        ]
        conform_note = "in-repo demo literals"
    conform_verdicts = detect(perfs)
    conform_check = "holds" if all(not v.contaminated for v in conform_verdicts) else "fires"
    _append_stage(
        report, stage="conform", verdict="SCRIPTED", evidence="scripted",
        scripted_check=conform_check,
        details={"note": conform_note, "rows": [asdict(v) for v in conform_verdicts]},
    )

    # ② validity。轨迹是写死的，不来自 claims。
    traj = TrajectoryAudit(
        trajectory_id="demo-traj", model="demo",
        recovers_public_solution=False,
        reads_eval_artifact=False,
        infers_generator_structure=False,
        manipulates_feedback=False,
        benefits_invalid_scoring=False,
        exploit_score=0.75, intended_score=0.76,
    )
    val_verdict = audit([traj])[0]
    _append_stage(
        report, stage="validity", verdict="SCRIPTED", evidence="scripted",
        scripted_check="holds" if val_verdict.valid else "fires",
        details=asdict(val_verdict),
    )

    # ③ rigor。30 条脚本化判决。
    decisions = [
        AgreementDecision(f"d{i}", judge_verdict=(i % 3 == 0), human_verdict=(i % 3 == 0), touched=False)
        for i in range(30)
    ]
    kappa = kappa_touch_report(decisions)
    _append_stage(
        report, stage="rigor", verdict="SCRIPTED", evidence="scripted",
        scripted_check="holds" if not kappa.kappa_inflated_by_touching else "fires",
        details=kappa.to_dict(),
    )

    # ④ judge。演示系数不是校准电池。certify_judge 不会给 PASS。
    cal = JudgeCalibration(judge="demo-judge", position_bias=0.05, length_bias=0.03,
                           self_bias=0.10, authority_bias=0.02,
                           n_calibration=100, tau=0.90, calibrated=True)
    resp = ScoredResponse(response_id="r1", judge="demo-judge", model="demo-model",
                          raw_score=7.5, position=1, length_chars=200,
                          is_self_family=False, is_authority=False)
    corrected = correct([resp], [cal])[0]
    cert = certify_judge(cal, [resp], source="scripted")
    _append_stage(
        report, stage="judge", verdict="SCRIPTED", evidence="scripted",
        scripted_check="fires" if corrected.preference_leakage else "holds",
        certification=_cert_dict(cert),
        details=asdict(corrected),
    )

    # ⑤ reliab。5 万个全 True 是脚本，不是一次测量。
    rel = estimate_reliability([True] * 50000, target_reliability=0.99)
    _append_stage(
        report, stage="reliab", verdict="SCRIPTED", evidence="scripted",
        scripted_check="holds" if rel.meets_target else "fires",
        details=asdict(rel),
    )

    # ⑥ selfaudit。只有收据一致率是测量；它不认证 judge。
    if real_claims and real_receipts:
        rec_map = {r.get("claim"): r for r in real_receipts}
        n = len(real_claims)
        n_match = sum(
            1 for c in real_claims
            if c.get("id") in rec_map and rec_map[c["id"]].get("ok")
        )
        rate = (n_match / n) if n else 0.0
        probe = Probe(probe_id="receipt-match-rate", true_value=1.0, tolerance=0.05)
        probe_ok = probe.is_within_tolerance(rate)
        migration = Migration(
            mechanism="receipt-match", train_perf=1.0, heldout_perf=rate,
            is_gamed=False, is_overfit=False,
        )
        failure = classify_failure(migration)
        verdict = "PASS" if failure.failure_mode.value == "benign" and probe_ok else "WARN"
        _append_stage(
            report, stage="selfaudit", verdict=verdict, evidence="measured",
            details={
                "probe": probe.probe_id,
                "probe_within_tolerance": probe_ok,
                "match_rate": rate,
                "n_claims": n,
                "n_match": n_match,
                "failure_mode": failure.failure_mode.value,
                "basis": failure.basis,
                "measures": "receipt_match_rate",
                "not_a_judge_certificate": True,
                "note": "match rate of supplied receipts against supplied claims",
            },
        )
    elif real_claims:
        _append_stage(
            report, stage="selfaudit", verdict="UNVERIFIED", evidence="measured",
            details={
                "probe": "receipt-match-rate",
                "probe_within_tolerance": False,
                "match_rate": None,
                "not_a_judge_certificate": True,
                "note": "claims were supplied without receipts; the probe was not run",
            },
        )
    else:
        probe = Probe(probe_id="demo-probe", true_value=0.80, tolerance=0.02)
        probe_ok = probe.is_within_tolerance(0.79)
        migration = Migration(mechanism="demo-migration", train_perf=0.92,
                              heldout_perf=0.70, is_gamed=False, is_overfit=True)
        failure = classify_failure(migration)
        _append_stage(
            report, stage="selfaudit", verdict="SCRIPTED", evidence="scripted",
            scripted_check="holds" if failure.failure_mode.value == "benign" else "fires",
            details={
                "probe": probe.probe_id,
                "probe_within_tolerance": probe_ok,
                "failure_mode": failure.failure_mode.value,
                "basis": failure.basis,
                "not_a_judge_certificate": True,
                "note": "scripted overfit demo",
            },
        )

    # ⑦ ledger。claims 文件是这次调用的输入；演示 claim 不是。
    ledger = Ledger()
    if real_claims:
        for c in real_claims:
            evidence_path = c.get("evidence") or ""
            locator = c.get("locator") or ""
            ev = Evidence(evidence_path, locator) if evidence_path and locator else None
            state = ClaimState.SUPPORTED if c.get("status") == "verified" else ClaimState.INCONCLUSIVE
            num_val = next(iter(_numeric_values(c)), None)
            ledger.add(Claim(c.get("id", ""), c.get("claim", ""), num_val,
                             "value", ev, state))
        ledger_rep = ledger.verify()
        ledger_rep["source"] = f"{len(real_claims)} supplied claims"
        ledger_rep["not_a_judge_certificate"] = True
        ledger_verdict = "PASS" if ledger_rep["all_verifiable"] else "WARN"
        _append_stage(
            report, stage="ledger", verdict=ledger_verdict, evidence="measured",
            details=ledger_rep,
        )
    else:
        ledger.add(Claim("e2e-1", "端到端演示 claim", 0.86, "score",
                         Evidence("demo/out.json", "row:1"), ClaimState.SUPPORTED))
        ledger_rep = ledger.verify()
        ledger_rep["source"] = "demo"
        ledger_rep["not_a_judge_certificate"] = True
        _append_stage(
            report, stage="ledger", verdict="SCRIPTED", evidence="scripted",
            scripted_check="holds" if ledger_rep["all_verifiable"] else "fires",
            details=ledger_rep,
        )

    _finalize(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="eval-meta CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("selftest", help="全模块自检")
    sub.add_parser("offline", help="仓内坏 judge 夹具；不读兄弟仓")
    p = sub.add_parser("pipeline", help="流水线（演示，或调用方提供的 claims/receipts）")
    p.add_argument("--claims", default=None, help="claims.json 路径（可选，不来自兄弟仓路径）")
    p.add_argument("--receipts", default=None, help="recompute_receipts.json 路径（可选）")

    args = parser.parse_args()
    if args.command == "selftest":
        return run_selftest_all()
    if args.command == "offline":
        return run_offline()
    if args.command == "pipeline":
        return run_pipeline(args.claims, args.receipts)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
