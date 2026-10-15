"""Record QAOA Hamiltonians for offline stochastic calibration (six runs by default)."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from run_stochastic_calibration import save_json

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--grids', nargs='+', choices=['2x2', '3x3'], default=['2x2', '3x3'])
    p.add_argument('--seeds', nargs='+', type=int, default=[201, 202, 203])
    p.add_argument('--alpha', type=int, choices=range(11), default=7)
    p.add_argument('--horizon', type=int, default=600, help='Use 1 for a recorder smoke test only')
    p.add_argument('--shots', type=int, default=512)
    p.add_argument('--timeout', type=int, default=21600)
    p.add_argument('--output', type=Path, default=ROOT / 'qaoa_calibration_results')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--force', action='store_true')
    args = p.parse_args()
    if min(args.seeds) < 0 or min(args.horizon, args.shots, args.timeout) < 1:
        p.error('Seeds must be nonnegative; horizon, shots, and timeout must be positive')
    output = args.output.resolve()
    failures = 0
    for grid, seed in itertools.product(dict.fromkeys(args.grids), dict.fromkeys(args.seeds)):
        folder = ROOT / f'grid_{grid}' / 'qaoa_calibration'
        optimizer = folder / ('annealer_quantum.py' if grid == '2x2' else 'annealer.py')
        config_path = ROOT / (f'sim2x2_a{args.alpha}.sumocfg' if grid == '2x2' else f'grid_3x3/sim3x3_a{args.alpha}.sumocfg')
        import xml.etree.ElementTree as ET
        inputs = [config_path]
        for tag in ('net-file', 'route-files', 'additional-files'):
            node = ET.parse(config_path).find('./input/' + tag)
            if node is not None:
                inputs.extend(config_path.parent / value for value in node.get('value').split(','))
        paths = [folder / 'a7.py', optimizer, ROOT / 'qaoa_calibration_recorder.py',
                 ROOT / 'supplementary_traffic_metrics.py', *inputs]
        hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        config = dict(grid=grid, seed=seed, alpha=args.alpha, horizon=args.horizon,
                      shots=args.shots, python=sys.executable, source_hashes=hashes)
        key = f'{grid}_a{args.alpha}_seed{seed}_t{args.horizon}_shots{args.shots}'
        print(key, flush=True)
        if args.dry_run:
            continue
        output.mkdir(parents=True, exist_ok=True)
        destination = output / (key + '.json')
        snapshots = output / (key + '.snapshots.jsonl')
        if destination.exists() and not args.force:
            old = json.loads(destination.read_text())
            if old.get('status') == 'success' and old.get('config') == config and snapshots.exists():
                print('  already complete; skipped', flush=True)
                continue
        env = dict(os.environ, QAOA_SEED=str(seed), QAOA_HORIZON=str(args.horizon),
                   QAOA_SHOTS=str(args.shots), QAOA_SNAPSHOT_PATH=str(snapshots),
                   SUPPLEMENTARY_OUTPUT_DIR=str(output / 'tripinfo'))
        result = dict(config=config, status='failed', snapshot_path=str(snapshots))
        records = []
        started = time.perf_counter()
        log_path = output / (key + '.log')
        try:
            with log_path.open('w', encoding='utf-8') as log:
                proc = subprocess.run([sys.executable, '-u', str(folder / 'a7.py'), str(args.alpha)],
                                      cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
                                      timeout=args.timeout)
            if proc.returncode:
                raise RuntimeError(f'Exit {proc.returncode}; see {log_path}')
            for line in log_path.read_text(encoding='utf-8').splitlines():
                for prefix, field in [('ENERGY_JSON: ', 'energy'), ('SUPPLEMENTARY_JSON: ', 'supplementary')]:
                    if line.startswith(prefix):
                        result[field] = json.loads(line[len(prefix):])
            records = [json.loads(line) for line in snapshots.read_text().splitlines()]
            if len(records) != result['energy']['num_decisions'] or not records:
                raise ValueError('Snapshot count does not match decision count')
            if not all(result['supplementary'][k] for k in ('departure_accounting_ok', 'arrival_accounting_ok')):
                raise ValueError('Vehicle accounting mismatch')
            result['status'] = 'success'
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
            result['error'] = str(exc)
            failures += 1
        result['elapsed_seconds'] = time.perf_counter() - started
        save_json(destination, result)
        print('  ' + result['status'] + ': ' + result.get('error', str(len(records)) + ' snapshots'), flush=True)
    return int(failures > 0)


if __name__ == '__main__':
    raise SystemExit(main())
