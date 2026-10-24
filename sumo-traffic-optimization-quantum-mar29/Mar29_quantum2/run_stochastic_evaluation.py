"""Evaluate frozen stochastic controllers on independent optimizer seeds.

Default: alpha .7, 600 seconds, two grids, 20 seeds each. No retuning.
Traffic demand remains fixed: optimizer seeds are not traffic replications.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

from run_stochastic_calibration import fingerprint, parse_output, save_json

ROOT = Path(__file__).resolve().parent
METRICS = ('completed_mean_travel_seconds', 'completed_mean_waiting_seconds',
           'completed_trips', 'unfinished_trips', 'removed_trips',
           'network_time_loss_seconds', 'network_waiting_seconds',
           'pending_insertion_at_cutoff', 'pending_insertion_vehicle_seconds_sampled')


def validate_result(result, settings, seed):
    energy, decisions, supplementary = (result[k] for k in ('energy', 'decisions', 'supplementary'))
    if energy['seed'] != seed or energy['num_decisions'] != 600 or len(decisions) != 600:
        raise ValueError('Wrong seed or incomplete decision sequence')
    for decision in decisions:
        if any(decision[key] != value for key, value in settings.items()
               if key != 'evaluation_budget'):
            raise ValueError('Actual optimizer settings differ from frozen settings')
        if decision['energy_evaluations'] != settings['evaluation_budget']:
            raise ValueError('Wrong evaluation budget')
    if supplementary['cutoff_seconds'] != 600:
        raise ValueError('Wrong simulation cutoff')
    if not all(supplementary[k] for k in ('departure_accounting_ok', 'arrival_accounting_ok')):
        raise ValueError('Vehicle accounting mismatch')
    if not Path(supplementary['tripinfo_path']).is_file():
        raise ValueError('Raw tripinfo file is missing')
    for metric in METRICS:
        if metric not in supplementary:
            raise ValueError('Missing traffic metric: ' + metric)


def write_tables(output, results):
    fields = ['grid', 'seed', 'status', 'error', *METRICS,
              'optimum_recovery_rate', 'average_optimality_gap']
    with (output / 'runs.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            writer.writerow(dict(grid=result['config']['grid'], seed=result['config']['seed'],
                status=result['status'], error=result.get('error', ''),
                **{k: result.get('supplementary', {}).get(k) for k in METRICS},
                **{k: result.get('energy', {}).get(k) for k in fields[-2:]}))
    summary = []
    for grid in sorted({r['config']['grid'] for r in results}):
        group = [r for r in results if r['config']['grid'] == grid]
        successful = [r for r in group if r['status'] == 'success']
        for metric in METRICS:
            values = [r['supplementary'][metric] for r in successful
                      if r['supplementary'][metric] is not None]
            summary.append(dict(grid=grid, metric=metric, successful_runs=len(successful),
                failed_runs=len(group)-len(successful), nonnull_runs=len(values),
                mean=statistics.mean(values) if values else None,
                sd=statistics.stdev(values) if len(values) > 1 else None))
    with (output / 'summary.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['grid', 'metric', 'successful_runs',
            'failed_runs', 'nonnull_runs', 'mean', 'sd'])
        writer.writeheader()
        writer.writerows(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grids', nargs='+', choices=['2x2', '3x3'], default=['2x2', '3x3'])
    parser.add_argument('--seeds', nargs='+', type=int, default=list(range(301, 321)))
    parser.add_argument('--output', type=Path, default=ROOT / 'stochastic_evaluation_results')
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    settings_path = ROOT / 'stochastic_evaluation_settings.json'
    frozen = json.loads(settings_path.read_text())
    if frozen['alpha_index'] != 7 or frozen['horizon_seconds'] != 600:
        parser.error('This protocol supports alpha .7 and 600 seconds only')
    if min(args.seeds) < 0 or args.timeout < 1:
        parser.error('Seeds must be nonnegative and timeout positive')
    if set(args.seeds) & set(frozen['calibration_optimizer_seeds'] + frozen['calibration_qaoa_seeds']):
        parser.error('Evaluation seeds must be separate from calibration seeds')
    output = args.output.resolve()
    configs = []
    for grid in dict.fromkeys(args.grids):
        for seed in dict.fromkeys(args.seeds):
            configs.append(dict(grid=grid, seed=seed, settings=frozen['grids'][grid],
                alpha_index=7, horizon_seconds=600, python=sys.executable,
                fingerprint=fingerprint(grid, 7),
                settings_hash=hashlib.sha256(settings_path.read_bytes()).hexdigest(),
                runner_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print(f'{len(configs)} runs; frozen approximate stochastic control; output: {output}', flush=True)
    if args.dry_run:
        for config in configs:
            print(config['grid'], config['seed'], config['settings'])
        return 0
    output.mkdir(parents=True, exist_ok=True)
    manifest = dict(protocol=frozen, configurations=configs)
    manifest_path = output / 'manifest.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()) != manifest:
        parser.error('Output has a different protocol, source version, or seed list; use a new output folder')
    save_json(manifest_path, manifest)
    results = []
    for index, config in enumerate(configs, 1):
        grid, seed, settings = (config[k] for k in ('grid', 'seed', 'settings'))
        key = f'{grid}_a7_seed{seed}'
        destination = output / (key + '.json')
        print(f'[{index}/{len(configs)}] {key}', flush=True)
        if destination.exists():
            old = json.loads(destination.read_text())
            if old.get('status') == 'success' and old.get('config') == config:
                try:
                    validate_result(old, settings, seed)
                    results.append(old)
                    print('  verified existing result; skipped', flush=True)
                    continue
                except (ValueError, KeyError):
                    pass
        env = dict(os.environ, STOCHASTIC_SEED=str(seed),
            STOCHASTIC_BUDGET=str(settings['evaluation_budget']),
            STOCHASTIC_RESTARTS=str(settings['restarts']),
            STOCHASTIC_RANDOM_START=str(settings['random_start_probability']),
            STOCHASTIC_INITIAL_TEMPERATURE=str(settings['initial_temperature']),
            SUPPLEMENTARY_OUTPUT_DIR=str(output / 'tripinfo'))
        result = dict(config=config, status='failed')
        log_path = output / (key + '.log')
        started = time.perf_counter()
        try:
            script = ROOT / f'grid_{grid}/2_classical_global_stochastic/a7.py'
            with log_path.open('w', encoding='utf-8') as log:
                subprocess.run([sys.executable, '-u', str(script), '7'], cwd=ROOT,
                    env=env, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout, check=True)
            result['energy'], result['decisions'] = parse_output(
                log_path, settings['evaluation_budget'], seed, settings['restarts'])
            result['supplementary'] = next(json.loads(line[len('SUPPLEMENTARY_JSON: '):])
                for line in log_path.read_text(encoding='utf-8').splitlines()
                if line.startswith('SUPPLEMENTARY_JSON: '))
            validate_result(result, settings, seed)
            result['status'] = 'success'
        except (OSError, ValueError, KeyError, StopIteration, subprocess.SubprocessError) as exc:
            result['error'] = str(exc) or type(exc).__name__
        result['elapsed_seconds'] = time.perf_counter() - started
        save_json(destination, result)
        results.append(result)
        write_tables(output, results)
        print('  ' + result['status'] + ': ' + result.get('error', '600 decisions; accounting passed'), flush=True)
    write_tables(output, results)
    return int(any(r['status'] != 'success' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
