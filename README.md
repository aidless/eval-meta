# 评测元系统（eval-meta）工程

[![CI](https://github.com/aidless/eval-meta/actions/workflows/ci.yml/badge.svg)](https://github.com/aidless/eval-meta/actions/workflows/ci.yml)

> **English TL;DR**: A runnable engineering implementation of an 'evaluation-of-evaluations' meta-system: seven modules (contamination, validity, statistical rigor, judge calibration, reliability, self-audit, evidence ledger), each anchored to verified literature and each carrying a `--selftest` that must fail on injected violations. Run `python3 -m eval_meta.cli pipeline` for the staged verdict pipeline; 49 tests pass in a standalone clone. Its stance is disciplinary: every claim carries an evidence-chain entry, and an unobserved result is still a result.

> 对应「评测系统架构 · 工程蓝图」的**可运行实现**——把「评测的评测」做成一等公民的工程。
> 所有组件锚定在已验证外部证据上（6 篇验号论文 + 1 份内部程序文档 + 373 项研究综述），每个模块的存在理由 = 一条可复现失效模式。

## 模块（7 个，全部实现并测试通过）

| 模块 | 蓝图章节 | 锚定证据 | 职责 | 测试数 |
|---|---|---|---|---|
| `conform` | §3.2 抗污染门 | `2405.16281` ConStat | 行为性污染检测（无需训练数据），三档分级 L1≤2%/L2≤10%/L3>10%（相对差） | 6 |
| `validity` | §3.3 协议效度门 | `2607.22368` HackDetect | 奖励黑客审计（5 类）+ Mislead gap>0.02 判无效 | 6 |
| `rigor` | §4.1 统计严谨门 | Agreement by Construction | κ 触及报告（被触及/未触及分别报 κ，充高警告）+ Cohen's d + Wilson CI | 8 |
| `judge` | §4.2 judge 校准层 | 2026 Crossref/PLOS One + `2502.01534` | 位置/长度/自我/权威四偏差校正（最小二乘估计，min 30 样本）+ 抗偏好泄漏判红 | 8 |
| `reliab` | §4.3 五九可靠性 | 蓝图 §4.3 | 样本高效可靠度估计（五九需 ~30 万样本）+ 达到目标所需样本量 | 6 |
| `selfaudit` | §5 自我审计层 | `2606.30219` + `2608.08722` | 校准探针（已知真值）+ 失效分类 gamed/overfit/benign | 6 |
| `ledger` | §2 证据链 | 内部程序文档 P1（不在仓内） | 数字有载体：claim-evidence 链 + 独立重算（不一致必抓） | 6 |

**合计：46 个模块测试 + 10 个集成测试 + 3 个 CLI 测试 = 59 个测试被收集。**

在**独立 clone**（无外部工作区）下实跑结果是 **49 passed + 10 skipped**：那 10 个集成测试
依赖仓外兄弟目录的数据文件（`../llm-agent-projects/20-llm-eval-benchmark/data/` 与
`../agi-research-program/p1/`），数据不在本仓内，缺文件时按设计 skip。
每个模块的 `--selftest` 全部 PASS。

> 架构说明见 `ARCHITECTURE.md`（组件职责、数据流、自指问题处理、测试策略、关键设计决策）。

## 快速运行

```bash
cd eval-meta
python3 -m pytest tests/ -q                          # 49 passed + 10 skipped（跳过项需仓外数据）
python3 -m eval_meta.conform --selftest              # 抗污染门自检
python3 -m eval_meta.validity --selftest             # 协议效度门自检
python3 -m eval_meta.rigor --selftest                # 统计严谨门自检
python3 -m eval_meta.judge --selftest                # judge 校准自检
python3 -m eval_meta.reliab --selftest               # 可靠性估计器自检
python3 -m eval_meta.selfaudit --selftest            # 自我审计层自检
python3 -m eval_meta.ledger --selftest               # 证据链自检
```

### CLI 入口（7 模块流水线）

```bash
python3 -m eval_meta.cli selftest                    # 全模块自检
python3 -m eval_meta.cli pipeline                    # 完整流水线（demo 数据）
python3 -m eval_meta.cli pipeline \
  --claims <path-to-claims.json> \
  --receipts <path-to-recompute_receipts.json>   # 真实数据模式（claims/receipts JSON）
```

**demo 模式实跑输出**（2026-11-10，`python3 -m eval_meta.cli pipeline`）：

```text
conform    → WARN   （demo-leaky L3 ratio=0.474>0.1，污染标记，故意注入）
validity   → PASS
rigor      → PASS
judge      → PASS
reliab     → PASS
selfaudit  → WARN   （overfit demo：gap=0.22>0.15，自我审计如实报警）
ledger     → PASS   （1 supported）
final      → WARN   （data_mode=demo）
```

demo 数据故意带缺陷（demo-leaky / overfit），两处 WARN 是门在正确报警，不是环境问题。

流水线顺序：`conform`（抗污染）→ `validity`（协议效度）→ `rigor`（统计严谨）→ `judge`（校准）→ `reliab`（可靠性）→ `selfaudit`（自我审计）→ `ledger`（证据链）。输出合法 JSON，每阶段带 verdict + 明细。

**真实数据模式**（`--claims`/`--receipts`）的端到端路径已验证：30 条 claim + 23 条独立重算 receipt → **7 模块全 PASS**（`selfaudit` 用独立重算一致性作已知真值探针，`ledger` 用 claim 证据链）。

> 证据边界：这 30 条 claim / 23 条 receipt 的数据文件来自仓外工作区
> （`agi-research-program/p1/`），**不随本仓发布**，所以在独立 clone 上对应断言是 skip
> 而不是 pass——本仓**无法自证**这组数字。机制本身可核：把同形数据喂给
> `python3 -m eval_meta.cli pipeline --claims … --receipts …` 会输出 `"verdict": "PASS"`、
> `"data_mode": "real"`。

## 纪律

- 每个模块带 `--selftest`（注入违规必须 exit≠0，AGENTS.md 第 21 条 RED→GREEN）。
- 每个数字有载体：`ledger` 记录 evidence path + locator，无法追溯的声明不写。
- Null 也是结果：未观测到 ≠ 不存在。
- 独立重算是外部验证（内部程序文档 P1，该文档不在本仓内）：`ledger.recompute()` 不一致必抓。

## 锚定证据（全部验号）

| 证据 | 来源 | 锚定模块 |
|---|---|---|
| `2405.16281` ConStat | arXiv abs 已验号 | `conform` |
| `2607.22368` HackDetect | arXiv abs 已验号 | `validity` |
| Agreement by Construction | 2026 Crossref（κ 0.056→0.714 vs 0.064） | `rigor` |
| `2502.01534` 偏好泄漏 | arXiv abs 已验号 | `judge` |
| `2606.30219` EvalSafetyGap | arXiv abs 已验号（373 项研究） | `selfaudit` |
| `2608.08722` 指纹化 | arXiv abs 已验号 | `selfaudit` |
| 内部程序文档 P1（不在仓内） | 证据链纪律（预注册/主指标唯一/独立重算/Null 也是结果） | `ledger` |

## Limits

- demo 数据模式（无 `--claims`/`--receipts`）的 verdict 只证明管道机制，不代表任何真实评测。
- 真实数据模式的 30 claim / 23 receipt 数据文件不在本仓内（仓外工作区），独立 clone 上
  对应集成测试按设计 skip——本仓无法自证那组数字，机制可按上面的命令复核。
- `judge` 偏差校正最小 30 样本；样本不足时该层降级并如实标注。
- 五九可靠性需要 ~30 万样本量级；`reliab` 在小样本下输出的是"达到目标还差多少"的估计。

## 结构导览

| 路径 | 内容 |
|------|------|
| `eval_meta/conform.py` … `ledger.py` | 7 个模块，各带 `--selftest`（注入违规必须 exit≠0） |
| `eval_meta/cli.py` | `pipeline` 流水线入口（demo / 真实数据双模式） |
| `tests/` | 46 模块测试 + 10 集成（仓外数据，缺文件 skip）+ 3 CLI |
| `ARCHITECTURE.md` | 组件职责、数据流、自指问题处理、关键设计决策 |
