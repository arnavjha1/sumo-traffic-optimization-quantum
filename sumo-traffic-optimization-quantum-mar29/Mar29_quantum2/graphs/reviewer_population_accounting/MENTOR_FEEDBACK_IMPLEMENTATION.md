# Mentor feedback: implemented follow-up

The comments were checked against the full supplement, not just the figures previously shared. No controller settings, saved traffic results, or primary run inclusion were changed.

| Feedback | Action |
|---|---|
| The 2x2 ECDF truncation needs an explicit annotation | Both the own-trajectory and new common-state ECDFs label the range 0.985 to 1.0005 inside the plots. |
| Investigate the 3x3 QAOA outlier | Identified seed 312; verified 600 decisions and accounting; all selected/exact energies were independently checked. Added parameter audit and leave-one-out sensitivity tables. The run is retained. |
| Compare the optimizers on identical Hamiltonians | Added frozen classical replay on all 24000 recorded QAOA-evaluation states, using three separate replay seeds per state (72000 classical optimizations). No SUMO or QAOA reruns and no retuning. |
| Use appropriate replication for uncertainty | Paired bootstrap resamples 20 complete QAOA source trajectories per grid. Three classical repeats are averaged within each trajectory. Individual decisions are not independent replications. |
| Document computational budgets | Already present in table_optimizer_budgets.tex. This remains distinct from traffic-decision counts; no equal-cost or matched-budget claim is made. |
| Prefer the run-level quality figure and retain ECDFs as supporting evidence | Retained and annotated figure_energy_run_summary.pdf, added paired common-state differences, and positioned the own-trajectory ECDF later among the additional figures. |
| Avoid attributing effects specifically to quantum sampling or stochasticity as a cause | Captions and conclusions retain observational/conditional wording. No distinctive quantum advantage, equivalence, or causal benefit of stochastic approximation is established. |

## Common-state replay findings

Each grid has 12000 distinct source Hamiltonians from 20 QAOA evaluation runs. QAOA energies are the recorded selected energies; the classical algorithm is rerun with the SAME pressure coefficients, prior signal state, neighbors and coupling/switching constants. Exact energies and selected states are checked independently. The original frozen budgets (32 for 2x2; 28 for 3x3) and other stochastic settings are unchanged.

| Grid | Classical replay mean gap | Recorded QAOA mean gap | Classical recovery | QAOA recovery | Earlier engineering screen |
|---|---:|---:|---:|---:|---|
| 2x2 | 0.02573 | 0.05468 | 99.286% | 99.367% | Fails mean-gap, full-distribution and tail checks |
| 3x3 | 24.69659 | 22.81081 | 43.156% | 41.692% | Passes all four descriptive tolerances |

On 3x3, the paired classical-minus-QAOA mean-gap difference is +1.88579, with pointwise trajectory-cluster 95% CI [0.49166, 3.79476]. Thus a descriptive tolerance pass is not equality: the mean gap still differs. The recovery difference is +1.46389 percentage points, CI [-1.15278, 3.45563].

On 2x2, the paired mean-gap difference is -0.02895, CI [-0.04357, -0.01562]. Recovery differs by -0.08056 percentage points, CI [-0.20833, 0.05278]. Near-identical recovery rates do not imply identical nonzero-gap tails.

These are post-hoc diagnostics under QAOA-visited states. They strengthen the controlled comparison, but are not formal equivalence tests, a new tuning procedure, or proof of matched computational cost. The older calibration-validation failures remain in the supplement. The same earlier engineering tolerances are shown transparently, including all 101 equally spaced nonzero-gap quantiles.

Reverse replay on classical-origin states is not possible from the current stochastic recordings: those decision records omit the Hamiltonian bias coefficients. This is a limitation, not grounds to invent those states or rerun the full traffic study without a separate decision.

## Outlier findings

Seed 312 selected final fixed angles gamma = 0.698132, beta = 1.221730, depth p = 2 during the existing within-run calibration. The other 19 runs selected gamma = 3.141593, beta = 0.523599, p = 2. Its run-average gap is 6.8586 and recovery is 68.33%; the other 19 have mean run-average gap approximately 23.6504. This identifies a real configuration difference but does not prove its causal contribution to traffic outcomes.

The sensitivity tables compare QAOA against classical stochastic control with all runs and with seed 312 omitted. Completion, in-network time-loss and combined-delay intervals span zero in both versions. The conclusion that a QAOA traffic advantage over this stochastic baseline is not established does not depend on dropping the outlier. The full 20-run analyses remain primary.

## Files to share

- README.md: updated index and methodological limits.
- preview_revised_tables.tex: all 17 current tables.
- preview_revised_figures.tex: all 12 current figures with captions.
- This document: what was implemented and what remains limited.

The three common-state tables begin with table_common_hamiltonian_. The outlier tables are table_qaoa_outlier_audit.tex and table_qaoa_outlier_sensitivity.tex. Every figure is supplied as PDF and PNG with reproducible Python source.

Grammar, references, historical exact-baseline provenance and the difference between historical and full-trip waiting definitions are manuscript tasks; these analyses do not fix them automatically. The reviewer said preferably matched: a transparent, limited stochastic control remains scientifically useful even where a matching screen fails.
