# Alpha 0.7: QAOA and stochastic calibration

Each run contains 600 decisions. Means and sample standard deviations are across runs.

| Network | Controller | Budget | Runs | Recovery % (mean ± SD) | Gap (mean ± SD) | Approx. mean nonzero gap |
|---|---|---:|---:|---:|---:|---:|
| 2x2 | QAOA (512 shots) | — | 20 | 99.40 ± 0.24 | 0.07354 ± 0.06300 | 12.257 |
| 2x2 | Classical stochastic | 8 | 3 | 85.39 ± 3.43 | 1.08990 ± 0.60155 | 7.459 |
| 2x2 | Classical stochastic | 16 | 3 | 96.61 ± 0.95 | 0.15057 ± 0.04666 | 4.443 |
| 2x2 | Classical stochastic | 32 | 3 | 99.33 ± 0.17 | 0.02084 ± 0.00757 | 3.127 |
| 2x2 | Classical stochastic | 64 | 3 | 99.83 ± 0.17 | 0.00404 ± 0.00635 | 2.427 |
| 2x2 | Classical stochastic | 128 | 3 | 99.89 ± 0.10 | 0.00013 ± 0.00012 | 0.120 |
| 3x3 | QAOA (512 shots) | — | 20 | 41.42 ± 3.75 | 23.32345 ± 2.54391 | 39.812 |
| 3x3 | Classical stochastic | 8 | 3 | 19.33 ± 1.04 | 22.05509 ± 2.73368 | 27.341 |
| 3x3 | Classical stochastic | 16 | 3 | 44.50 ± 3.01 | 8.60316 ± 0.39260 | 15.501 |
| 3x3 | Classical stochastic | 32 | 3 | 77.94 ± 1.08 | 1.67913 ± 0.16968 | 7.613 |
| 3x3 | Classical stochastic | 64 | 3 | 95.83 ± 1.45 | 0.18428 ± 0.06062 | 4.423 |
| 3x3 | Classical stochastic | 128 | 3 | 99.50 ± 0.29 | 0.01231 ± 0.00776 | 2.462 |

## Interpretation and limitations

- QAOA budgets are shots; stochastic budgets count energy evaluations. These are not equal-cost budgets.
- The approximate pooled nonzero-gap mean is total gap divided by non-optimal decisions, reconstructed from summaries. It assumes optimal-hit gaps are numerically zero; it is not a recovered distribution.
- Saved QAOA records contain run-level energy summaries and selected-energy logs, but no per-decision exact-minimum sequence or Hamiltonian snapshots. Gap quantiles and distribution matching cannot be established.
- These controllers encounter different closed-loop Hamiltonians. These numbers screen candidates; they do not establish matching on common instances.
- 2x2 budget 32 approximately matches recovery but has smaller gaps. Budget 16 has a higher mean gap and substantially lower recovery.
- 3x3 budget 16 approximately matches recovery but has much smaller gaps. Budget 8 approximately matches mean gap but has much lower recovery.
- No tested budget matches both QAOA summary targets closely. Do not choose by traffic outcomes.
- All 30 inspected stochastic result JSON files lack the supplementary vehicle-accounting block; they remain useful for energy calibration, not the reviewer population/delay comparison.

## QAOA sources

- quantum_data/quantum_simulation_results.json, a7, 20 runs
- quantum_data_3x3/quantum_3x3_simulation_results.json, a7, 20 runs

Per-row source paths are retained in comparison.json.
