# Fresh QAOA evaluation

`run_qaoa_evaluation.py` preserves the existing instrumented per-grid QAOA algorithms. Defaults: alpha .7, 600 seconds, 512 shots, optimizer seeds 301–320, 20 runs per grid. Seeds vary sampler randomness; traffic demand is fixed. Calibration seeds are excluded. The 3x3 controller retains its existing within-run parameter calibration; no traffic-outcome tuning is added.

Run validation separately:

```
qiskit_env\Scripts\python.exe -u run_qaoa_evaluation.py --seeds 903 --output qaoa_evaluation_validation
```

Run the evaluation after validation passes:

```
qiskit_env\Scripts\python.exe -u run_qaoa_evaluation.py
```

The runner freezes source/input hashes and the seed list in a manifest. It validates 600 sequential Hamiltonian records, sampler seed, shots, grid, alpha, horizon, raw tripinfo existence, and vehicle accounting. Successful matching runs resume; failed runs retry. Changed sources or seed lists require another output folder. Raw snapshots, tripinfo, logs, per-run JSON, runs.csv and summary.csv are retained. Calibration and validation outputs are excluded from the evaluation inventory.

Refresh the inventory using `qiskit_env\Scripts\python.exe data_analysis/prepare_reviewer_control_data.py`. Final comparisons must use fresh evaluation records and consistent trip accounting. Completed-trip means should be reported alongside throughput, unfinished vehicles and insertion backlog.
