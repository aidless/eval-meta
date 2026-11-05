# Failure modes

## FM-1 — The meta-eval falsely certifies a bad judge

A false certification is any report a reader can treat as "this judge passed" when the judge is bad, or when the judge was never measured.

`certify_judge` in `eval_meta/judge.py` has no pass state. `certified` is always false. `status` is `REFUSED` or `UNVERIFIED`.

### What is refused

For `source="caller_supplied"` the record is `REFUSED` when:

1. The calibration is missing, `calibrated` is false, or `n_calibration` is below 30 (`uncalibrated`).
2. Any scored response sets `is_self_family=True` (`preference_leakage`). The corrected score is still computed. The certificate is not.
3. `tau` is below `TAU_FLOOR` (0.50). That floor is a local refusal threshold in this file. It is not a cutoff from a paper (`tau_below_floor`).

`python -m eval_meta.cli offline` loads `fixtures/offline/bad_judge.json`. The fixture is synthetic and in-repo: raw score 9.8, `tau` 0.05, `is_self_family` false. The previous judge stage treated "no leakage flag" as a pass. The command now prints `REFUSED` / `tau_below_floor` and exits 0 only for that refusal. Exit 0 is the refusal running. It is not a judge pass.

`python -m eval_meta.cli pipeline` builds the judge stage from literals in `eval_meta/cli.py`. `certify_judge(..., source="scripted")` returns `UNVERIFIED` / `scripted_demo`. The stage verdict is `SCRIPTED`. The pipeline's top-level verdict is not `PASS` unless every stage verdict is `PASS`, and the judge stage is never `PASS` on this entry point.

### When a bad judge is still certified

These cases are open. This package does not close them.

1. **Caller-supplied tau.** A record with `tau` at or above 0.50, `n_calibration` at least 30, `calibrated=True`, and every `is_self_family` flag false returns `UNVERIFIED` / `caller_supplied_calibration`. It does not return `PASS`. Tau is not recomputed from human labels. A forged tau is not detected. A reader who promotes `UNVERIFIED`, or the corrected score, to "the judge passed" has certified it themselves.

2. **Self-family is a flag.** Leakage is whatever the caller wrote in `is_self_family`. Judge name and model name are not compared. A same-family score with the flag left false is not a `preference_leakage` refusal. Combined with a high caller-supplied tau, the result is `UNVERIFIED`, not a refusal.

3. **Additive debiasing is not agreement.** `correct()` subtracts the sum of the non-negative bias coefficients from the raw score. It does not use the response's position or length. A judge that inverts rankings still receives a corrected number. That number is not a judge certificate.

4. **Other stages do not measure the judge.** In `--claims` / `--receipts` mode, conform, validity, rigor, judge, and reliab stay `SCRIPTED`. Conform's "real" branch multiplies one claim scalar by fixed factors; that is not a contamination measurement. Ledger can be `PASS` when the supplied claims have evidence paths and locators. Self-audit can be `PASS` when the receipt match rate is 1 within 0.05. Both details set `not_a_judge_certificate`. A ledger PASS is not a judge certificate. A partial receipt match is `WARN` (the old code treated any non-zero match as a perfect probe). That `WARN` is about the receipt rate, not about a judge.

5. **A good judge is not confirmed either.** There is no in-repo human-agreement battery, and no `source` value that means "we recomputed tau". This package cannot certify a bad judge, and it also cannot certify a good one.

6. **Skipped sibling tests.** `tests/test_integration_p1.py` (3) and `tests/test_integration_benchmarks.py` (7) need files that are not in this tree. On a clean clone they skip. A skip is not evidence that those files would pass, and it is not coverage.
