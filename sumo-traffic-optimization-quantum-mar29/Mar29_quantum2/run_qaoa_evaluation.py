"""Evaluate QAOA on fresh optimizer seeds with full-trip SUMO accounting."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from run_stochastic_calibration import save_json
from run_stochastic_evaluation import write_tables, METRICS

ROOT = Path(__file__).resolve().parent


def validate(result):
    s = result['supplementary']
    config = result['config']
    rows = [json.loads(line) for line in Path(result['snapshot_path']).read_text().splitlines()]
    if len(rows) != 600 or result['energy']['shots'] != 512:
        raise ValueError('Incomplete snapshots or wrong shot count')
    for index, row in enumerate(rows, 1):
        if (row['decision'] != index or row['sampler_seed'] != config['seed']
                or row['grid'] != config['grid'] or row['shots'] != 512
                or row['alpha_index'] != 7 or row['horizon_seconds'] != 600):
            raise ValueError('Snapshot protocol mismatch')
    if s['cutoff_seconds'] != 600 or result['energy']['num_decisions'] != 600:
        raise ValueError('Incomplete horizon or decision sequence')
    if not s['departure_accounting_ok'] or not s['arrival_accounting_ok']:
        raise ValueError('Vehicle accounting mismatch')
    if not Path(s['tripinfo_path']).is_file() or any(k not in s for k in METRICS):
        raise ValueError('Missing raw output or metrics')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--grids', nargs='+', choices=['2x2', '3x3'], default=['2x2', '3x3'])
    p.add_argument('--seeds', nargs='+', type=int, default=list(range(301, 321)))
    p.add_argument('--output', type=Path, default=ROOT / 'qaoa_evaluation_results')
    p.add_argument('--timeout', type=int, default=21600)
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    if min(args.seeds) < 0 or args.timeout < 1:
        p.error('Invalid seeds or timeout')
    if set(args.seeds) & {101, 102, 103, 201, 202, 203}:
        p.error('Evaluation seeds must exclude calibration seeds')
    output = args.output.resolve()
    configs = []
    for grid in dict.fromkeys(args.grids):
        folder = ROOT / f'grid_{grid}/qaoa_calibration'
        config = ROOT / ('sim2x2_a7.sumocfg' if grid == '2x2' else 'grid_3x3/sim3x3_a7.sumocfg')
        paths = [folder / 'a7.py', folder / ('annealer_quantum.py' if grid == '2x2' else 'annealer.py'), config,
                 ROOT / 'supplementary_traffic_metrics.py', Path(__file__),
                 ROOT / 'qaoa_calibration_recorder.py', ROOT / 'run_stochastic_evaluation.py']
        for node in ET.parse(config).findall('./input/*'):
            if node.tag in ('net-file', 'route-files', 'additional-files'):
                paths.extend(config.parent / name for name in node.attrib['value'].split(','))
        if grid == '3x3':
            paths.append(ROOT / 'grid_3x3/routes_3x3/routes3x3_a7.rou.xml')
        hashes = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
        for seed in dict.fromkeys(args.seeds):
            configs.append(dict(grid=grid, seed=seed, alpha_index=7, horizon_seconds=600,
                                controller='qaoa', shots=512, source_hashes=hashes, python=sys.executable))
    print(f'{len(configs)} QAOA runs; alpha .7; 600 seconds; 512 shots', flush=True)
    if args.dry_run:
        return 0
    output.mkdir(parents=True, exist_ok=True)
    manifest = dict(configurations=configs, role='evaluation', demand='fixed',
                    label='QAOA; fresh sampler seeds; existing per-grid algorithm unchanged')
    if (output / 'manifest.json').exists() and json.loads((output / 'manifest.json').read_text()) != manifest:
        p.error('Output protocol differs; choose a new output directory')
    save_json(output / 'manifest.json', manifest)
    results = []
    for index, config in enumerate(configs, 1):
        key = f'{config["grid"]}_a7_seed{config["seed"]}'
        destination = output / (key + '.json')
        print(f'[{index}/{len(configs)}] {key}', flush=True)
        if destination.exists():
            old = json.loads(destination.read_text())
            if old.get('status') == 'success' and old.get('config') == config:
                try:
                    validate(old)
                    results.append(old)
                    print('  verified; skipped', flush=True)
                    continue
                except (OSError, ValueError, KeyError):
                    pass
        result = dict(config=config, status='failed')
        started = time.perf_counter()
        log_path = output / (key + '.log')
        try:
            script = ROOT / f'grid_{config["grid"]}/qaoa_calibration/a7.py'
            snapshots = output / (key + '.snapshots.jsonl')
            result['snapshot_path'] = str(snapshots)
            env = dict(os.environ, QAOA_SEED=str(config['seed']), QAOA_HORIZON='600',
                       QAOA_SHOTS='512', QAOA_SNAPSHOT_PATH=str(snapshots),
                       SUPPLEMENTARY_OUTPUT_DIR=str(output / 'tripinfo'))
            with log_path.open('w', encoding='utf-8') as log:
                subprocess.run([sys.executable, '-u', str(script), '7'], cwd=ROOT, env=env,
                               stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout, check=True)
            for line in log_path.read_text(encoding='utf-8').splitlines():
                for prefix, field in [('ENERGY_JSON: ', 'energy'), ('SUPPLEMENTARY_JSON: ', 'supplementary')]:
                    if line.startswith(prefix):
                        result[field] = json.loads(line[len(prefix):])
            validate(result)
            result['status'] = 'success'
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            result['error'] = str(exc)
        result['elapsed_seconds'] = time.perf_counter() - started
        save_json(destination, result)
        results.append(result)
        write_tables(output, results)
        print('  ' + result['status'] + ': ' + result.get('error', 'accounting passed'), flush=True)
    write_tables(output, results)
    return int(any(r['status'] != 'success' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
