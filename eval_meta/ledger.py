"""证据链 ledger——蓝图 §7 可核查性，PROGRAM.md P1 证据纪律。

关键纪律（PROGRAM.md §5）：
1. 预注册先于实验。
2. 主指标只有一个（其余 secondary）。
3. **每个数字有载体**：claim 必须带 evidence path + locator；
   无法追溯的声明删除或降级为 inconclusive。
4. **独立重算**：P1 的目标是让别人能重算；不是「我自己再跑一遍」。
5. Null 也是结果：不得把未观测到写成不存在。
6. 不做 p-hacking：看到结果后改主指标/样本量/排除规则 = 违规。

设计：
- Claim（声明）+ Evidence（证据载体）+ Locator（定位）。
- 每个 Claim 必须带 evidence（path + locator），否则不可信。
- 可核查性判定：claim 是否满足「每个数字有载体」。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Sequence


class ClaimState(str, Enum):
    """声明状态（PROGRAM.md：无法追溯的声明删除或降级为 inconclusive）。"""

    SUPPORTED = "supported"      # 有载体且可追溯
    INFERRED = "inferred"        # 推断（部分载体）
    INCONCLUSIVE = "inconclusive"  # 无法追溯（降级）
    MISSING = "missing"          # 无载体（删除候选）


@dataclass(frozen=True)
class Evidence:
    """证据载体（数字有载体：每个数字挂 evidence path + locator）。"""

    path: str       # 文件路径（evidence 文件）
    locator: str    # 定位（行号 / 键 / 公式）

    def to_dict(self) -> dict:
        return {"path": self.path, "locator": self.locator}


@dataclass
class Claim:
    """声明（claim）+ 证据（evidence）。"""

    claim_id: str
    text: str
    value: float | None
    unit: str | None
    evidence: Evidence | None
    state: ClaimState = ClaimState.MISSING
    basis: str = ""

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "value": self.value,
            "unit": self.unit,
            "evidence": self.evidence.to_dict() if self.evidence else None,
            "state": self.state.value,
            "basis": self.basis,
        }


@dataclass
class Ledger:
    """证据链账本。"""

    entries: list[Claim] = field(default_factory=list)

    def add(self, claim: Claim) -> None:
        self.entries.append(claim)

    def verify(self) -> dict:
        """可核查性判定：每个 claim 必须带 evidence，否则降级/标记。"""
        report = {
            "total": len(self.entries),
            "supported": 0,
            "inferred": 0,
            "inconclusive": 0,
            "missing": 0,
            "unverifiable": [],
            "all_verifiable": True,
        }
        for claim in self.entries:
            if claim.evidence is not None:
                if claim.state == ClaimState.SUPPORTED:
                    report["supported"] += 1
                elif claim.state == ClaimState.INFERRED:
                    report["inferred"] += 1
                else:
                    report["inconclusive"] += 1
            else:
                claim.state = ClaimState.MISSING
                report["missing"] += 1
                report["unverifiable"].append(claim.claim_id)
                report["all_verifiable"] = False
        return report

    def recompute(self, recompute_fn) -> dict:
        """独立重算（PROGRAM.md P1：让别人能重算）。

        recompute_fn(claim) -> float | None：对每个 claim 重算值。
        返回：重算一致/不一致/无法重算计数。
        """
        report = {
            "total": len(self.entries),
            "recompute_match": 0,
            "recompute_mismatch": 0,
            "recompute_unavailable": 0,
            "mismatches": [],
        }
        for claim in self.entries:
            if claim.evidence is None or claim.value is None:
                report["recompute_unavailable"] += 1
                continue
            recomputed = recompute_fn(claim)
            if recomputed is None:
                report["recompute_unavailable"] += 1
            elif abs(recomputed - claim.value) <= 1e-9:
                report["recompute_match"] += 1
            else:
                report["recompute_mismatch"] += 1
                report["mismatches"].append({
                    "claim_id": claim.claim_id,
                    "claimed": claim.value,
                    "recomputed": recomputed,
                })
        return report

    def save(self, path: str) -> None:
        """保存账本到 JSON（预注册先于实验的证据链）。"""
        data = {
            "entries": [c.to_dict() for c in self.entries],
            "verify": self.verify(),
        }
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2))

    @classmethod
    def load(cls, path: str) -> "Ledger":
        """从 JSON 加载账本。"""
        data = json.loads(Path(path).read_text())
        ledger = cls()
        for e in data["entries"]:
            ev = None
            if e.get("evidence"):
                ev = Evidence(e["evidence"]["path"], e["evidence"]["locator"])
            ledger.add(Claim(
                claim_id=e["claim_id"],
                text=e["text"],
                value=e.get("value"),
                unit=e.get("unit"),
                evidence=ev,
                state=ClaimState(e.get("state", "missing")),
                basis=e.get("basis", ""),
            ))
        return ledger


def _run_selftest() -> int:
    """RED→GREEN 自检。"""
    failures = 0

    # GREEN 1：每个 claim 带证据 → 全部可核查
    ledger = Ledger()
    ledger.add(Claim("c1", "MMLU GPT-4 2023 ~86%", 0.86, "score",
                     Evidence("benchmarks/mmlu.csv", "row:gpt4-2023"), ClaimState.SUPPORTED))
    ledger.add(Claim("c2", "污染阈值 L3>10%", 0.10, "ratio",
                     Evidence("eval_meta/conform.py", "L3_threshold"), ClaimState.SUPPORTED))
    report = ledger.verify()
    if not report["all_verifiable"]:
        print(f"[FAIL] GREEN1: all claims with evidence → should be verifiable")
        failures += 1
    else:
        print(f"[PASS] GREEN1: all verifiable ({report['supported']} supported)")

    # RED 1：无证据 claim → 必须标记为 missing（无法追溯 = 删除候选）
    ledger = Ledger()
    ledger.add(Claim("c3", "某模型 100% 准确率", 1.0, "score", None))
    report = ledger.verify()
    if report["all_verifiable"] or report["missing"] != 1:
        print(f"[FAIL] RED1: no-evidence claim → should be missing")
        failures += 1
    else:
        print(f"[PASS] RED1: no-evidence claim marked missing")

    # RED 2：独立重算必须能抓到不一致
    ledger = Ledger()
    ledger.add(Claim("c4", "某模型 0.80", 0.80, "score",
                     Evidence("out.json", "score"), ClaimState.SUPPORTED))
    # 重算返回 0.85（不一致）
    report = ledger.recompute(lambda c: 0.85)
    if report["recompute_mismatch"] != 1:
        print(f"[FAIL] RED2: recompute should detect mismatch")
        failures += 1
    else:
        print(f"[PASS] RED2: recompute mismatch detected")

    # GREEN 2：独立重算一致 → 通过
    report = ledger.recompute(lambda c: 0.80)
    if report["recompute_match"] != 1:
        print(f"[FAIL] GREEN2: recompute match should pass")
        failures += 1
    else:
        print(f"[PASS] GREEN2: recompute match confirmed")

    print(f"\n证据链 ledger selftest: {'PASS' if failures == 0 else f'FAIL ({failures})'}")
    return failures


if __name__ == "__main__":
    import sys
    sys.exit(_run_selftest())
