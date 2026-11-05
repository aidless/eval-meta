"""Collected-test inventory.

This is the only count the README is allowed to quote.
``tests/test_inventory.py`` fails when pytest collection drifts from these tuples.
A sibling-repo id is an expected skip on a clean clone. A skip is not a pass.
"""

from __future__ import annotations

import argparse
import re
import sys

# In-repo tests. They must pass with no sibling checkout.
OFFLINE_NODE_IDS: tuple[str, ...] = (
    "tests/test_cli.py::test_cli_pipeline_outputs_json",
    "tests/test_cli.py::test_cli_pipeline_runs",
    "tests/test_cli.py::test_cli_selftest_all",
    "tests/test_cli.py::test_demo_pipeline_does_not_certify_the_judge",
    "tests/test_cli.py::test_full_receipt_match_still_does_not_certify_the_judge",
    "tests/test_cli.py::test_offline_refuses_inrepo_bad_judge",
    "tests/test_cli.py::test_partial_receipts_do_not_perfect_the_probe",
    "tests/test_conform.py::test_batch_detect_returns_one_per_model",
    "tests/test_conform.py::test_clean_model_not_contaminated",
    "tests/test_conform.py::test_expansion_is_relative_not_absolute",
    "tests/test_conform.py::test_high_contamination_detected",
    "tests/test_conform.py::test_inverted_model_not_contaminated",
    "tests/test_conform.py::test_mid_contamination_detected",
    "tests/test_inventory.py::test_collected_node_ids_match_inventory",
    "tests/test_inventory.py::test_readme_states_problem_counts_and_split",
    "tests/test_inventory.py::test_sibling_tests_skip_without_absolute_paths",
    "tests/test_inventory.py::test_tree_has_no_badges_pypi_or_author_paths",
    "tests/test_judge.py::test_calibration_requires_min_samples",
    "tests/test_judge.py::test_corrected_score_deducts_bias",
    "tests/test_judge.py::test_corrected_score_floor_at_zero",
    "tests/test_judge.py::test_high_tau_caller_record_stays_unverified",
    "tests/test_judge.py::test_low_tau_record_is_refused",
    "tests/test_judge.py::test_scripted_demo_is_not_a_certificate",
    "tests/test_judge.py::test_self_family_flag_preference_leakage",
    "tests/test_judge.py::test_self_family_is_refused_even_with_high_tau",
    "tests/test_judge.py::test_uncalibrated_judge_no_deduction_but_flags_leakage",
    "tests/test_judge.py::test_uncalibrated_record_is_refused",
    "tests/test_judge_estimator.py::test_estimator_recovers_known_biases",
    "tests/test_judge_estimator.py::test_estimator_requires_min_samples",
    "tests/test_judge_estimator.py::test_estimator_zero_bias_when_clean",
    "tests/test_ledger.py::test_claim_with_evidence_verifiable",
    "tests/test_ledger.py::test_ledger_save_load_roundtrip",
    "tests/test_ledger.py::test_no_evidence_claim_marked_missing",
    "tests/test_ledger.py::test_recompute_detects_mismatch",
    "tests/test_ledger.py::test_recompute_match",
    "tests/test_ledger.py::test_recompute_unavailable_for_no_evidence",
    "tests/test_reliab.py::test_empty_results",
    "tests/test_reliab.py::test_failures_reject_target",
    "tests/test_reliab.py::test_insufficient_samples_not_meet_target",
    "tests/test_reliab.py::test_meets_target_with_sufficient_clean_samples",
    "tests/test_reliab.py::test_sample_size_increases_with_reliability",
    "tests/test_reliab.py::test_sample_size_positive",
    "tests/test_rigor.py::test_cohens_d_positive_when_a_greater",
    "tests/test_rigor.py::test_cohens_d_zero_when_identical",
    "tests/test_rigor.py::test_kappa_report_counts_separate",
    "tests/test_rigor.py::test_kappa_report_flags_inflation",
    "tests/test_rigor.py::test_kappa_report_no_touching_rule",
    "tests/test_rigor.py::test_wilson_ci_bounded",
    "tests/test_rigor.py::test_wilson_ci_contains_point_estimate",
    "tests/test_rigor.py::test_wilson_ci_empty_n",
    "tests/test_selfaudit.py::test_classify_benign",
    "tests/test_selfaudit.py::test_classify_gamed",
    "tests/test_selfaudit.py::test_classify_overfit",
    "tests/test_selfaudit.py::test_probe_battery_detects_failure",
    "tests/test_selfaudit.py::test_probe_battery_healthy",
    "tests/test_selfaudit.py::test_probe_tolerance_boundary",
    "tests/test_validity.py::test_all_hack_types_classified",
    "tests/test_validity.py::test_clean_trajectory_valid",
    "tests/test_validity.py::test_exposed_trajectory_invalid",
    "tests/test_validity.py::test_exposed_types_enum_values",
    "tests/test_validity.py::test_gap_inflated_trajectory_invalid",
    "tests/test_validity.py::test_small_gap_is_noise",
)

# Expected skips when sibling checkouts are absent. Not coverage.
SIBLING_NODE_IDS: tuple[str, ...] = (
    "tests/test_integration_benchmarks.py::TestRealBenchmarkData::test_conform_from_real_mmlu",
    "tests/test_integration_benchmarks.py::TestRealBenchmarkData::test_gsm8k_real_problems",
    "tests/test_integration_benchmarks.py::TestRealBenchmarkData::test_humaneval_real_problems",
    "tests/test_integration_benchmarks.py::TestRealBenchmarkData::test_ledger_real_benchmark",
    "tests/test_integration_benchmarks.py::TestRealBenchmarkData::test_mmlu_real_questions",
    "tests/test_integration_benchmarks.py::TestRealBenchmarkData::test_mt_bench_real_conversations",
    "tests/test_integration_benchmarks.py::TestRealBenchmarkData::test_wilson_from_real_gsm8k",
    "tests/test_integration_p1.py::test_real_claims_all_verifiable",
    "tests/test_integration_p1.py::test_real_recompute_all_match",
    "tests/test_integration_p1.py::test_real_receipts_all_ok",
)

OFFLINE_PASS = len(OFFLINE_NODE_IDS)
SIBLING_SKIP = len(SIBLING_NODE_IDS)
COLLECTED = OFFLINE_PASS + SIBLING_SKIP

# What a clean clone must print. Do not quote a larger "passed" number.
CLEAN_CLONE_SUMMARY = f"{OFFLINE_PASS} passed, {SIBLING_SKIP} skipped, {COLLECTED} collected"


def check_pytest_summary(text: str) -> None:
    """Fail unless pytest reported exactly the clean-clone pass/skip split.

    ``N passed`` with no skipped count is a failure: it would mean the sibling
    tests ran, or the skip count was dropped. Sibling skips are not passes.
    """
    matches = re.findall(r"(\d+) passed, (\d+) skipped", text)
    if len(matches) != 1:
        raise SystemExit(
            "pytest summary must contain exactly one 'X passed, Y skipped' line; "
            f"found {len(matches)} in:\n{text}"
        )
    passed, skipped = (int(matches[0][0]), int(matches[0][1]))
    if (passed, skipped) != (OFFLINE_PASS, SIBLING_SKIP):
        raise SystemExit(
            f"expected {OFFLINE_PASS} passed, {SIBLING_SKIP} skipped; "
            f"got {passed} passed, {skipped} skipped"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a pytest summary against the inventory")
    parser.add_argument("--check-pytest-summary", required=True, help="path to pytest output")
    args = parser.parse_args(argv)
    text = open(args.check_pytest_summary, encoding="utf-8").read()
    check_pytest_summary(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
