# Finer calibration sweep

Completed 117 settings: 36 for 2x2 and 81 for 3x3. Tuning used QAOA seeds
201/202 and classical seeds 101–103. Only the tuning-selected candidate for
each grid was checked on QAOA seed 203. This seed was previously inspected,
so this remains diagnostic validation, not fully independent confirmation.

Before execution, criteria were recorded in protocol.json: recovery within
3 percentage points, mean gap within 20% relative to QAOA, full empirical
gap Wasserstein distance within 25% of QAOA mean gap, and nonzero-gap
quantile distance within 25% of QAOA mean nonzero gap. These are exploratory
engineering tolerances, not statistical equivalence bounds. Unlike the first
sweep, small QAOA gaps are not normalized by a one-energy-unit floor.

## Results on seed 203

| Grid | Classical recovery | QAOA recovery | Classical mean gap | QAOA mean gap | Passed all checks |
|---|---:|---:|---:|---:|---|
| 2x2 | 99.56% | 99.33% | 0.04027 | 0.07363 | No |
| 3x3 | 42.11% | 34.50% | 25.40010 | 26.98623 | No |

2x2 selected budget 32, restarts 2, random-start probability .25, initial
temperature 50, final temperature .01. It failed gap-distribution checks on
both tuning and validation. QAOA had only three nonoptimal tuning decisions
and four validation decisions; tail estimates are poorly supported.

3x3 selected budget 28, restarts 4, random-start probability .5, initial
temperature 50, final temperature .01. Nine tuning candidates passed all
checks; the selected candidate passed tuning but failed validation's recovery
check by a 7.61-point recovery difference. Its mean gap and distribution
distance checks passed validation. Other candidates were not substituted
after seeing this result.

No matched controller is certified. No new traffic evaluations or fresh QAOA
confirmation runs were launched. Settings should not be presented as a frozen,
validated distribution match. A bounded practical next step is an explicitly
unmatched stochastic control with these calibration discrepancies disclosed;
further matching research would require additional independent data and a
clearly specified calibration protocol.
