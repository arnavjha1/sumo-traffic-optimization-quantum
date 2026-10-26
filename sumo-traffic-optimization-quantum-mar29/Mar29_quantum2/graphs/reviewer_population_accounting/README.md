# Revised reviewer supplement

All files are built from the 120 completed evaluations at alpha 0.7, 600 seconds and fixed demand. No controller or saved simulation results were changed. The current global baseline is simulated annealing (SA); these artifacts do not certify an exact action-selecting historical benchmark.

## Start here

- `revised_tables.tex`: 17 tables (two population/delay tables, demand audit, energy statistics, budget accounting, matching diagnostics, six adjusted comparison tables, three common-state replay tables, and two outlier-audit/sensitivity tables).
- `revised_figures.tex`: all 12 figure PDFs with captions.
- `preview_revised_tables.tex` and `preview_revised_figures.tex`: standalone previews.
- Each figure has a `.pdf`, `.png`, and reproducible Python plotting script.

Do not include both revised_tables.tex and the older supplementary_tables.tex/additional_tables.tex together: those entrypoints overlap. The original four table files remain available, but the revised entrypoint uses the more complete adjusted-effects tables instead of duplicating the older differences tables.

## Recommended figures

1. `figure_population.pdf`: completed and unfinished populations.
2. `figure_network_delay.pdf`: accumulated time loss and stopped waiting for all entered vehicles, including unfinished trips.
3. `figure_effects_qaoa_vs_stochastic.pdf`: direct QAOA/stochastic differences with confidence intervals.
4. `figure_total_delay.pdf`: pre-entry delay and time loss plus pre-entry delay, including vehicles still pending insertion.

Supporting figures: `figure_trip_times.pdf`, `figure_insertion_backlog.pdf`, `figure_effects_qaoa_vs_global.pdf`, `figure_effects_stochastic_vs_global.pdf`, `figure_energy_gaps.pdf`, and `figure_energy_run_summary.pdf`.

All mean error bars now show pointwise 95% bootstrap confidence intervals, not SD. Small dots retain the run-to-run variation. The difference plots give independent two-sample bootstrap intervals, including ratio-of-means intervals for percent changes. Overlap between mean intervals is not a test of a controller difference. None of the plotted intervals is multiplicity-adjusted; adjusted tests are in the tables.

## Statistical interpretation

The tests use approximate Welch comparisons and Holm adjustment across 66 nonconstant outcomes/grid/controller comparisons. All outcomes remain exploratory; no primary endpoint is claimed retrospectively. Bootstrap resampling uses full optimizer runs, not individual decisions or vehicles. Twenty runs per condition share fixed traffic demand; uncertainty does not cover different demand scenarios. Non-significance does not establish equivalence.

Two qualifications matter for the manuscript:

- On 2x2, the QAOA advantage over global SA in in-network time loss does not clearly persist in the new composite including pre-entry delay: mean difference -921.50 vehicle-s, pointwise 95% CI approximately [-3030.77, 1662.10].
- On 3x3, QAOA minus global SA in the composite is -8176.91 vehicle-s, pointwise 95% CI approximately [-11738.95, -4487.67], Holm-adjusted Welch p approximately 0.0221. The in-network time-loss comparison alone does not survive the full Holm adjustment.
- QAOA versus classical stochastic composite intervals span zero on both grids. A quantum-specific advantage is not established.

Raw/normalized gap ECDFs describe the controllers' own visited states and cannot demonstrate matching. Saved common-Hamiltonian calibration diagnostics are provided separately: neither grid passed every diagnostic validation check. QAOA circuit shots and SA energy evaluations are different work counters, not equivalent computational costs. The 2x2 ECDF panels zoom above 0.985 to make rare errors visible.

## Demand and delay verification

All 120 runs reconcile completed + unfinished + removed + pending with realized demand (6672 for 2x2; 10228 for 3x3). Effective input hashes and vehicle identities/types/speed factors match within grids; intended departure schedules match within XML rounding. See `data_analysis/population_accounting_comparison/demand_accounting_audit.md` and its JSON.

Pre-entry delay is summed from departDelay across both entered and undeparted raw tripinfo records. For undeparted vehicles it is accrued only through the cutoff. It is added to in-network timeLoss as a clearly named supplementary composite, joining disjoint pre-entry and in-network phases. Do not add stopped waiting or the sampled backlog integral again. Documentation: https://sumo.dlr.de/docs/Simulation/Output/TripInfo.html .

All 24000 QAOA Hamiltonian snapshots were independently enumerated again to verify selected and exact energies. Existing stochastic objective/budget/reproducibility tests pass. See `objective_verification.md` in the analysis folder.

## Rebuild or view

From the project root, rebuild everything without running simulations:

```powershell
.\qiskit_env\Scripts\python.exe data_analysis\rebuild_reviewer_supplement.py
```

Open individual plots with `--show`, for example:

```powershell
.\qiskit_env\Scripts\python.exe graphs\reviewer_population_accounting\plot_effects.py --show
.\qiskit_env\Scripts\python.exe graphs\reviewer_population_accounting\plot_energy.py --show
.\qiskit_env\Scripts\python.exe graphs\reviewer_population_accounting\plot_total_delay.py --show
```

The existing plot_population.py, plot_network_delay.py, plot_trip_times.py, and plot_insertion_backlog.py also support --show.

## LaTeX inclusion

Copy this folder to graphs/reviewer_population_accounting within the paper project. Add packages in the preamble:

```latex
\usepackage{booktabs}
\usepackage{graphicx}
\usepackage{textcomp}
```

Include the revised sets:

```latex
\input{graphs/reviewer_population_accounting/revised_tables.tex}
\input{graphs/reviewer_population_accounting/revised_figures.tex}
```

Select individual tables/figures if space is limited. Caption labels and uncertainty descriptions are included. The original study's historical waiting-time accounting must remain distinct from these full-trip SUMO waitingTime measurements. Grammar, reference formatting, and manuscript provenance still require a separate editing pass.


## Mentor follow-up: common states and the outlier

Read MENTOR_FEEDBACK_IMPLEMENTATION.md for the follow-up findings and limitations.

- `figure_common_hamiltonian_gaps.pdf`: frozen classical stochastic replay on the SAME evaluation Hamiltonians as recorded QAOA, not merely similar closed-loop state distributions.
- `figure_common_hamiltonian_differences.pdf`: paired source-trajectory differences with 95% cluster bootstrap intervals.
- `table_common_hamiltonian_energy.tex`, `table_common_hamiltonian_paired.tex`, `table_common_hamiltonian_screen.tex`: common-state statistics and screening limits.
- `table_qaoa_outlier_audit.tex`, `table_qaoa_outlier_sensitivity.tex`: seed 312 investigation and post-hoc leave-one-out checks. The run is retained in all primary analyses.

The common-state replay has 12,000 unique QAOA-origin states per grid and three classical replay seeds (701--703) per state. The original stochastic settings are frozen; QAOA is not resampled and no SUMO run is repeated. The 3x3 replay passes the earlier descriptive engineering screen; 2x2 does not. Passing is not an equivalence certificate, and no computational-budget matching is claimed. The earlier calibration-validation failures remain reported. Reverse replay on classical-origin states cannot be reconstructed from the current recordings because their per-decision Hamiltonian coefficients were not saved.

Seed 312 used different final fixed QAOA angles after the existing within-run calibration. All 600 recorded energies and exact minima were checked, and accounting passes. This observation explains a configuration difference, not a proven causal explanation of traffic performance. Sensitivity estimates excluding it are supplementary only.

Both the own-trajectory and common-state 2x2 ECDFs now explicitly label the truncated vertical range (0.985 to 1.0005).
