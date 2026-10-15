# QAOA calibration recorder

Review entry points:
- `run_qaoa_calibration.py`: six runs by default (two grids, seeds 201–203).
- `qaoa_calibration_recorder.py`: append-only JSONL snapshots, flushed each decision.
- `grid_2x2/qaoa_calibration/` and `grid_3x3/qaoa_calibration/`: independent controller/optimizer copies.

From the project directory:
```
qiskit_env\Scripts\python.exe -u run_qaoa_calibration.py
```
Preview with `--dry-run`. Use `--horizon 1 --seeds 201 --output qaoa_recorder_validation`
for a smoke test only, not a scientific calibration. Default horizon is 600 s,
alpha index 7, and 512 shots per circuit. Full runs may take substantial time:
2x2 searches 200 parameter combinations at every decision; 3x3 searches during
the first 50 seconds, then retains the original fixed-parameter behavior.

## Recorded data

Each `.snapshots.jsonl` row contains biases, previous binary states, neighbor
indices, coupling and switching coefficients, TLS ordering, simulation time,
chosen state, chosen energy, exact minimum, gap, seed, shots, chosen gamma/beta/p,
expected energy, circuit count, and total shots for that decision. The Ising
convention is s=2*x-1 with each i<j neighbor entry counted once. These inputs
allow classical optimizers to replay the same Hamiltonians without SUMO.

Per-run JSON contains settings, input/source hashes, energy statistics, and
supplementary completed/unfinished/delay metrics. Raw tripinfo XML is retained
under the output folder's `tripinfo` directory. A successful run is resumed only
when settings/hashes match and the snapshot file exists. Failures retain logs
and partial snapshots and are retried. Do not use partial runs for calibration.

## Deliberate differences from source

Original `3_quantum` files are unchanged; hashes are retained in
`qaoa_calibration_source_manifest.json`.

- The copied 2x2 script uses the root `sim2x2_a*.sumocfg`. Its original source
  currently points to a 3x3 configuration; that path is not reproduced.
- Each copied optimizer uses one seeded NumPy generator for Qiskit's sampler,
  carried across calls. No reseeding occurs at each decision. Seeds refer to
  QAOA sampling, not independent traffic realizations; SUMO demand/settings
  remain those in the existing configurations.
- Observer metadata and supplementary tripinfo output are added, plus an
  optional horizon override. Traffic pressure and signal-transition logic
  remain copied from source.

This recorder does not implement the offline replay sweep or claim that prior
saved results are reproduced. Use the snapshots to calibrate on common inputs,
then freeze settings and use independent seeds for evaluation. Never choose
annealing settings based on downstream traffic outcomes.
