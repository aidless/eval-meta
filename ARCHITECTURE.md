# eval-meta 工程架构说明

> 这是「评测的评测」的可运行实现。组件职责、数据流和测试策略写在下面。
> 代码注释里的 arXiv 编号是引用，不是本仓里的复现实验。计数与 skip 以 `eval_meta/inventory.py` 为准。Judge 误认证见 `FAILURE_MODES.md`。

---

## 1. 设计定位

评测系统的核心难题不是「再设计一个 benchmark」，而是：**评测系统自己也会被钻空子、被污染、被过拟合**。传统基准的失效模式（Goodhart 饱和、数据污染、judge 偏差、agent 奖励黑客）同样会发生在评测系统自身。

eval-meta 把「评测的评测」做成**一等公民**：7 个模块各自检测一种可复现的评测失效模式，且每个模块自己也要被测试（RED→GREEN 纪律）。

## 2. 组件职责（7 模块 + 1 CLI）

| 组件 | 检测的失效模式 | 核心判据 |
|---|---|---|
| `conform` | 数据污染（训练集混入测试集） | 相对差三档：L1≤2%（干净）/ L2 2-10%（可疑）/ L3>10%（污染） |
| `validity` | 协议效度被钻（agent 奖励黑客） | 5 类黑客行为暴露 或 Mislead gap>0.02 → 无效 |
| `rigor` | 统计严谨性（κ 被「触及」充高） | 被触及 κ − 未触及 κ > 0.1 → 充高警告 |
| `judge` | LLM-as-Judge 偏差 + 偏好泄漏 | 位置/长度/自我/权威四偏差校正 + 自家人判红 |
| `reliab` | 样本量不足（五九不可靠） | 观测可靠度 ≥ 目标 且 样本量 ≥ 所需 |
| `selfaudit` | 评测系统自身失效（gamed/overfit） | 校准探针（已知真值）+ 失效三分类 |
| `ledger` | 数字无载体 / 独立重算不一致 | claim-evidence 链 + recompute 不一致必抓 |
| `cli` | 编排（把 7 模块串成流水线） | 输出合法 JSON，每阶段 verdict |

## 3. 数据流

```
输入数据（真实 claims/receipts 或 demo）
        │
        ▼
┌─────────────────────────────────────────────────────────┐
│  CLI pipeline（eval_meta/cli.py）                         │
│                                                          │
│  ① conform ──► ② validity ──► ③ rigor                   │
│      │            │             │                        │
│  ④ judge ◄──── ⑤ reliab ◄──── ⑥ selfaudit              │
│      │            │             │                        │
│  ⑦ ledger（汇总证据链）                                   │
└─────────────────────────────────────────────────────────┘
        │
        ▼
输出：pipeline report（JSON，每阶段 verdict + 明细）
```

- **数据模式**：`real`（调用方传入 `--claims`/`--receipts`）或 `demo`（脚本字面量）。两条路都不读兄弟仓库。
- **谁真正读了输入**：`--claims`/`--receipts` 只进入 `ledger` 和收据一致率（`selfaudit`）。`conform` 即使看到 claims，也只是把一个标量乘上固定系数，阶段判决保持 `SCRIPTED`。`validity` / `rigor` / `judge` / `reliab` 在这条 CLI 里不读输入文件。

## 4. 自指问题处理

评测系统自身也可能被钻空子（这就是「评测的评测」的意义）。eval-meta 的处理方式：

1. **校准探针**（`selfaudit.Probe`）：用已知真值注入，验证评测系统是否如实测量。`probe.is_within_tolerance()` 判据：测量值在真值 ± tolerance 内 → 探针通过。
2. **失效三分类**（`selfaudit.classify_failure`）：
   - `GAMED`（`is_gamed=True`）：评测被故意钻空子 → 最高严重度。
   - `OVERFIT`（`train_perf − heldout_perf > 0.15`）：过拟合（训练/评测分离不足）。
   - `BENIGN`：良性（未发现失效）。
3. **收据一致率**：`--receipts` 存在时，探针测量的是 `ok` 收据占 claims 的比例，真值按 1.0、容差 0.05。有一条对上不算通过。这个探针不是 judge 认证。

> 自指的边界：`selfaudit` 检测的是「评测系统测量的是否正确」，不是「评测系统是否自洽」——后者是 `ledger` 的职责（证据链一致性）。

## 5. 测试策略

- **模块自检**（`--selftest`）：每个模块注入违规必红（RED→GREEN，AGENTS.md 第 21 条）。
- **仓内测试**：不依赖兄弟仓库。数量以 `eval_meta/inventory.py` 的 `OFFLINE_NODE_IDS` 为准，由 `tests/test_inventory.py` 对照 pytest 收集结果。
- **兄弟仓测试**（标记 `sibling_repo`，缺文件则 skip，skip 不是通过，也不计入覆盖）：
  - `test_integration_p1.py`：`agi-research-program/p1/` 的 claims 与 recompute receipts。文件不在本仓。
  - `test_integration_benchmarks.py`：`llm-agent-projects/20-llm-eval-benchmark/data/` 的 sample JSON。文件不在本仓。
- **计数**：只引用 inventory 里的 clean-clone 句子（passed / skipped / collected）。不要把 skipped 加进 passed。

Judge 阶段不会给出认证通过。误认证的边界写在 `FAILURE_MODES.md`。

## 6. 关键设计决策（每个决策 = 一条可复现失效模式）

| 决策 | 理由（失效模式） |
|---|---|
| 相对差而非绝对差（conform） | 绝对差阈值误判干净模型（0.03 绝对差 = 3.75% 相对差被判 L3）；污染膨胀是相对量 |
| gap 阈值 0.02（validity） | 1% 内是评分噪声，0.01 会误杀干净模型 |
| min 30 样本（judge） | 校准电池最小样本量，否则估计不稳定 |
| 五九需 ~30 万样本（reliab） | 0.99 可靠度的置信区间需要大样本 |
| 被触及/未触及分报 κ（rigor） | 「触及」判决（by construction）充高整体 κ——必须分开报 |
| 真实数据优先（CLI） | demo 数据验证的是逻辑，真实数据验证的是有效性 |

## 7. 与现有资产的关系

| 资产 | 关系 |
|---|---|
| claims/receipts JSON（用户提供） | 真实数据源：claim 证据链 + 独立重算 receipt（ledger 验证） |
| benchmark 评测结果 JSON（用户提供） | 真实评测数据：MMLU/GSM8K/HumanEval/MT-Bench sample（benchmark 集成） |
| 评测 harness 输出（用户提供） | 备用数据源：真实 agent 评测 cases |

## 8. 快速运行

```bash
cd eval-meta
python3 -m eval_meta.cli offline                               # 仓内坏 judge 夹具，不读兄弟仓
python3 -m eval_meta.cli pipeline                              # 脚本演示；judge 阶段不是 PASS
python3 -m pytest tests/ -q -rs                                # 干净 clone：见 inventory（skip 不是 pass）
python3 -m eval_meta.cli selftest                              # 全模块自检
python3 -m eval_meta.cli pipeline \
  --claims <path-to-claims.json> \
  --receipts <path-to-recompute_receipts.json>  # 只把这两份文件喂给 ledger 与收据一致率
```
