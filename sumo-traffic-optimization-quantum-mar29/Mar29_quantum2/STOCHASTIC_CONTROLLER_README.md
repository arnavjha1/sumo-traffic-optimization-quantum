# Reviewer stochastic global control

## Frozen traffic evaluation

`run_stochastic_evaluation.py` uses `stochastic_evaluation_settings.json`,
which records the finer sweep's tuning-selected settings and their unmatched
status. It does not retune or select using traffic outcomes. The default is
20 fresh optimizer seeds (301–320) per grid, alpha .7, horizon 600 seconds.
Demand is fixed; uncertainty across these seeds concerns optimizer randomness.

Preview without running simulations:

```
qiskit_env\Scripts\python.exe run_stochastic_evaluation.py --dry-run
```

Run the 40-run stochastic evaluation:

```
qiskit_env\Scripts\python.exe -u run_stochastic_evaluation.py
```

The output folder contains an immutable protocol/source/seed manifest, per-run
JSON and logs, retained raw tripinfo XML, `runs.csv`, and `summary.csv` with
means and sample standard deviations across successful runs. Null completed-trip
means are retained and their nonnull sample counts are reported. Failed runs
are marked explicitly; the process exits nonzero if any run failed.

Repeating the same command validates and resumes successful results. Changing
the seed list, source, or settings requires a new `--output` folder. Failed or
incomplete runs are retried. Each decision's applied optimizer configuration
and budget, decision count, cutoff, raw XML existence, and departure/arrival
accounting are checked. Calibration seeds are rejected.

Validation uses a separate folder and seed:

```
qiskit_env\Scripts\python.exe -u run_stochastic_evaluation.py --seeds 901 --output stochastic_evaluation_validation
```

This runner evaluates the stochastic controller only. Instrumenting the existing
classical global baseline and making final cross-controller comparisons remain
separate steps. SUMO tripinfo completed-trip times are used consistently in
the CSVs; legacy printed waiting averages may use different accounting.

Both `grid_2x2/2_classical_global_stochastic/a7.py` and the corresponding
3x3 controller apply seeded, budget-limited simulated annealing to the global
Ising objective. They preserve the pressure calculation and signal constraints.
The optimizer uses switching penalty 10, coupling 2, spins `s=2*x-1`, and
counts each initialization and proposed state as one energy evaluation.
Exhaustive minima are diagnostics only; they do not choose the applied action.

## Calibration workflow

1. Collect full QAOA trajectories with `qiskit_env\Scripts\python.exe -u run_qaoa_calibration.py`.
2. Replay these Hamiltonians using `qiskit_env\Scripts\python.exe replay_stochastic_calibration.py`.
3. Compare recovery rate, mean gap, and gap quantiles in
   `stochastic_replay_results/summary.json`. No setting is automatically selected.
   Choose and document settings using energy quality only, then freeze them.
4. Evaluate the frozen controller with separate optimizer seeds using the
   environment variables `STOCHASTIC_SEED`, `STOCHASTIC_BUDGET`, and
   `STOCHASTIC_RESTARTS`, running the grid's `a7.py` from the project root.
   For replay parity, set restarts to `min(4, budget // 2)`.

Replay checks snapshot counts and independently enumerates the Hamiltonian to
verify the saved exact minimum, selected QAOA energy, and gap. It retains paired
per-decision gaps and hashes the inputs and optimizer sources. It is calibration
on QAOA-visited states, not a substitute for closed-loop traffic evaluation.
QAOA shots and classical energy evaluations are different computational costs.
Decisions within a trajectory are dependent; do not treat them as independent
replications for confidence intervals.

`--allow-smoke --input qaoa_recorder_validation --output tmp/replay_validation`
checks the replay plumbing only. Short recorder runs are rejected by default.
The full QAOA collection may take hours; the smoke files are not calibration
evidence. Existing main-study outputs are not rewritten by this workflow.

Run objective/budget/reproducibility checks with
`qiskit_env\Scripts\python.exe -m unittest test_stochastic_optimizer.py`.

## Random-start distribution calibration

`match_stochastic_controller.py` tests 30 settings per grid using QAOA seeds
201/202, selecting by energy-distribution distance and recovery rate. Only the
selected candidate is checked against seed 203. All three recordings had already
contributed to earlier baseline summaries; this is not fully unseen validation.
The saved protocol defines exploratory screening tolerances, not a statistical
equivalence test. In particular, the one-energy-unit normalization floor makes
the 2x2 screen permissive when mean gaps are very small; report raw gaps too.

Run with `qiskit_env\Scripts\python.exe -u match_stochastic_controller.py`.
Outputs in `stochastic_matching_results` retain all tuning candidates, the
selected candidate's validation, source hashes, and the selection protocol.
The sweep found an approximate 2x2 candidate, but the selected 3x3 candidate
failed validation. Neither is certified as an equivalent gap distribution.

The live controllers now accept `STOCHASTIC_RANDOM_START` (probability from 0
to 1, default 0) and `STOCHASTIC_INITIAL_TEMPERATURE` (default 5), alongside
budget/restarts/seed. Final temperature remains .01. Defaults preserve previous
behavior. A random start changes the first restart only; subsequent restarts
already start randomly. The selected state is always the best state encountered
within the search budget, independent of QAOA choices.
