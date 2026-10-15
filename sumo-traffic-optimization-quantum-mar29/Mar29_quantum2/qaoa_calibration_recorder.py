"""Append-only Hamiltonian snapshots for classical replay on common instances."""
import json
import os
from pathlib import Path


class CalibrationRecorder:
    def __init__(self, grid, alpha, seed, horizon, shots):
        self.path = Path(os.environ['QAOA_SNAPSHOT_PATH'])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open('w', encoding='utf-8')
        self.count = 0
        self.context = dict(grid=grid, alpha_index=alpha, sampler_seed=seed,
                            horizon_seconds=horizon, shots=shots)

    def record(self, time, biases, previous, neighbors, state, energy, exact, settings):
        self.count += 1
        row = dict(schema_version=1, decision=self.count, simulation_time=float(time),
                   **self.context, biases=[float(x) for x in biases],
                   previous_state=[int(x) for x in previous],
                   neighbors=[[int(j) for j in adjacent] for adjacent in neighbors],
                   switching_penalty=10, coupling_strength=2,
                   spin_convention='s=2*x-1; bitstring in TLS order',
                   selected_state=state, selected_energy=float(energy),
                   exact_min_energy=float(exact), optimality_gap=float(energy-exact),
                   qaoa=settings)
        self.handle.write(json.dumps(row, allow_nan=False) + '\n')
        self.handle.flush()

    def close(self):
        self.handle.close()
        print('SNAPSHOT_JSON: ' + json.dumps(dict(path=str(self.path.resolve()), decisions=self.count)))
