# Reviewer comparison readiness

available_runs.csv separates fresh evaluation, calibration, and historical data. Do not pool these roles or compare legacy waiting means directly with full-trip waiting.

QAOA calibration recordings provide descriptive supplementary metrics only; fresh QAOA evaluation is read from qaoa_evaluation_results when available. Current baseline scripts implement simulated annealing, not exact action selection. Their new accounting runs must be labeled accordingly; historical equivalence has not been established.

New baseline output is picked up from classical_global_accounting_results on rerun. Validation folders are intentionally excluded. Final inference and figures are pending comparable controller data.
