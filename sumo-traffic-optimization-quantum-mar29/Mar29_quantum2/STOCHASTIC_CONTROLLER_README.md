# Reviewer stochastic global control

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
