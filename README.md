# eval-meta

An evaluator can pass its own checks and still be a bad judge: contaminated items, a leaked preference, or a calibration number nobody recomputed.
This package runs seven local checks and labels each result as measured, scripted, or unverified.
It does not certify a judge, and a skipped sibling-repo test is not a pass.

## In-repo fixtures

These files live in this repository. Nothing in this section reads a sibling checkout.

- Unit tests and the CLI tests, except the two modules under [Sibling-repo dependencies](#sibling-repo-dependencies).
- `python -m eval_meta.cli pipeline` uses the scripted literals in `eval_meta/cli.py`. The judge stage is `SCRIPTED`, not `PASS`.
- `python -m eval_meta.cli offline` reads only `fixtures/offline/bad_judge.json`. That file is synthetic. The command reports `REFUSED` / `tau_below_floor`. `REFUSED` means the bad record was rejected. It is not a pass.

## Sibling-repo dependencies

These tests read checkouts that are not published in this repository. Point `EVAL_META_SIBLING_ROOT` at the directory that contains them, or leave it unset to use the parent of this repo. When the files are missing, the tests skip. That skip is the expected clean-clone result. It is not coverage.

| tests | sibling files | clean-clone result |
|---|---|---|
| `tests/test_integration_p1.py` (3) | `agi-research-program/p1/claims.json+recompute_receipts.json` | skip |
| `tests/test_integration_benchmarks.py` (7) | `llm-agent-projects/20-llm-eval-benchmark/data/{mmlu,gsm8k,humaneval,mt_bench}_sample.json` | skip |

## Counts

Clean clone, sibling files absent: **62 passed, 10 skipped, 72 collected**.

Those numbers are `eval_meta/inventory.py`. `tests/test_inventory.py` fails if collection, the `sibling_repo` marker, or this sentence drifts. The 10 skips are the two modules above and no others. Do not add the skips to the pass count.

## Run

```bash
pip install -e ".[dev]"
python -m eval_meta.cli offline
python -m eval_meta.cli pipeline
python -m pytest tests/ -q -rs
```

`offline` does not look for sibling clones. `pipeline` with no arguments does not either. `--claims` and `--receipts` read only the paths you pass. A `PASS` on the ledger, or on the receipt-match probe, is not a judge certificate.

Not published to PyPI. There is no install badge.

`FAILURE_MODES.md` records when a report can still be read as certifying a bad judge. `ARCHITECTURE.md` describes the seven checks.
