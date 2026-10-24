# Supplementary classical global baseline

The `grid_2x2/classical_global_accounting` and corresponding 3x3 directories
copy the current global controllers with tripinfo instrumentation. Original
scripts and saved main-study results remain unchanged. Original source hashes
and deliberate changes are in `classical_global_accounting_manifest.json`.

These controllers apply simulated annealing; they must not be labeled exact.
The copied 2x2 script corrects its source's 3x3 configuration path. Each decision
uses an independently spawned seeded generator, preserving the original search
settings. The seed labels control optimizer randomness, not independent traffic
demand. Historical result equivalence has not been established.

Validation command (one full run per grid):

```
qiskit_env\Scripts\python.exe -u run_classical_global_accounting.py --seeds 902 --output baseline_validation
```

Main accounting batch (20 optimizer seeds per grid):

```
qiskit_env\Scripts\python.exe -u run_classical_global_accounting.py
```

Runs save raw XML, logs, energy diagnostics, complete/unfinished populations,
network time loss, waiting, and insertion backlog. The runner checks 600
decisions, the cutoff, and departure/arrival reconciliation. It resumes successful
results with matching provenance and retries failed runs. Changed inputs or
seed lists require a new output directory. Filenames are shortened for Windows
path limits. Two initial failed validation attempts in
`classical_global_accounting_validation` are diagnostic only and are excluded
from comparisons; the corrected validation folder is `baseline_validation`.

Refresh the comparison inventory after new runs finish:

```
qiskit_env\Scripts\python.exe data_analysis/prepare_reviewer_control_data.py
```

That inventory excludes validation runs and distinguishes QAOA calibration
records from evaluation. Fresh instrumented QAOA evaluation remains needed for
an independent supplementary comparison. Historical legacy waiting means must
not be directly combined with full-trip SUMO tripinfo waiting means.
