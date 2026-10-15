"""Small energy-quality calibration sweep. Run from any working directory.

Defaults: two grids, alpha index 7, five budgets, three optimizer seeds (30 runs).
Results are exploratory; choose settings using energy quality, not traffic scores.
This runner does not claim QAOA distribution matching or select a final setting.
"""
import argparse
import csv
import hashlib
import itertools
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
VERSION = 1


def save_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def fingerprint(grid, alpha):
    folder = ROOT / f'grid_{grid}' / '2_classical_global_stochastic'
    config = ROOT / (f'sim2x2_a{alpha}.sumocfg' if grid == '2x2'
                     else f'grid_3x3/sim3x3_a{alpha}.sumocfg')
    paths = [folder / 'a7.py', folder / 'annealer_stochastic.py', config]
    for node in ET.parse(config).findall('./input/*'):
        if node.tag in ('net-file', 'route-files', 'additional-files'):
            paths.extend(config.parent / name for name in node.attrib['value'].split(','))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def parse_output(path, budget, seed, restarts):
    records = {}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        for prefix in ('ENERGY_JSON', 'OPTIMIZER_DECISIONS_JSON'):
            if line.startswith(prefix + ': '):
                records[prefix] = json.loads(line.split(': ', 1)[1])
    energy = records['ENERGY_JSON']
    decisions = records['OPTIMIZER_DECISIONS_JSON']
    if not decisions or len(decisions) != energy['num_decisions']:
        raise ValueError('Missing or inconsistent decision records')
    if energy['evaluation_budget'] != budget or energy['seed'] != seed:
        raise ValueError('Controller settings differ from requested settings')
    for decision in decisions:
        if decision['energy_evaluations'] != budget or decision['restarts'] != restarts:
            raise ValueError('Decision budget/restarts differ from requested settings')
        if decision['optimality_gap'] < -1e-8:
            raise ValueError('Selected energy is below the exact minimum')
    gaps = [d['optimality_gap'] for d in decisions]
    nonzero = [g for g in gaps if g > 1e-9]
    energy['nonzero_gap_count'] = len(nonzero)
    energy['mean_nonzero_gap'] = statistics.mean(nonzero) if nonzero else None
    energy['median_nonzero_gap'] = statistics.median(nonzero) if nonzero else None
    return energy, decisions


def summarize(output, results):
    fields = ['grid', 'alpha', 'budget', 'restarts', 'successful_runs',
              'recovery_rate_mean', 'recovery_rate_sd', 'mean_gap_mean',
              'mean_gap_sd', 'pooled_nonzero_gap_mean', 'pooled_nonzero_gap_median']
    rows = []
    keys = sorted({(r['grid'], r['alpha'], r['budget'], r['restarts']) for r in results})
    for key in keys:
        runs = [r for r in results if (r['grid'], r['alpha'], r['budget'], r['restarts']) == key
                and r['status'] == 'success']
        rates = [r['energy']['optimum_recovery_rate'] for r in runs]
        gaps = [r['energy']['average_optimality_gap'] for r in runs]
        nonzero = [d['optimality_gap'] for r in runs for d in r['decisions']
                   if d['optimality_gap'] > 1e-9]
        rows.append(dict(zip(fields, [*key, len(runs),
            statistics.mean(rates) if rates else None,
            statistics.stdev(rates) if len(rates) > 1 else None,
            statistics.mean(gaps) if gaps else None,
            statistics.stdev(gaps) if len(gaps) > 1 else None,
            statistics.mean(nonzero) if nonzero else None,
            statistics.median(nonzero) if nonzero else None])))
    with (output / 'summary.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--grids', nargs='+', choices=['2x2', '3x3'], default=['2x2', '3x3'])
    parser.add_argument('--budgets', nargs='+', type=int, default=[8, 16, 32, 64, 128])
    parser.add_argument('--seeds', nargs='+', type=int, default=[101, 102, 103])
    parser.add_argument('--alpha', type=int, choices=range(11), default=7)
    parser.add_argument('--timeout', type=float, default=600, help='Seconds per run')
    parser.add_argument('--output', type=Path, default=ROOT / 'stochastic_calibration_results')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--force', action='store_true', help='Repeat even successful matching runs')
    args = parser.parse_args()
    if min(args.budgets) < 2 or min(args.seeds) < 0 or args.timeout <= 0:
        parser.error('Budgets must be >= 2, seeds >= 0, timeout > 0')
    output = args.output.resolve()
    jobs = list(itertools.product(dict.fromkeys(args.grids), dict.fromkeys(args.budgets),
                                  dict.fromkeys(args.seeds)))
    fingerprints = {g: fingerprint(g, args.alpha) for g in args.grids}
    print(f'{len(jobs)} runs; alpha index {args.alpha}; outputs: {output}', flush=True)
    results = []
    for grid, budget, seed in jobs:
        restarts = min(4, budget // 2)
        key = f'{grid}_a{args.alpha}_budget{budget}_seed{seed}'
        config = dict(version=VERSION, grid=grid, alpha=args.alpha, budget=budget,
                      seed=seed, restarts=restarts, fingerprint=fingerprints[grid],
                      python=sys.executable)
        print(f'{key}: restarts={restarts}', flush=True)
        if args.dry_run:
            continue
        output.mkdir(parents=True, exist_ok=True)
        result_path = output / (key + '.json')
        if result_path.exists() and not args.force:
            old = json.loads(result_path.read_text(encoding='utf-8'))
            if old.get('config') == config and old.get('status') == 'success':
                print('  already complete; skipped', flush=True)
                results.append(old)
                continue
        env = os.environ.copy()
        env.update(STOCHASTIC_SEED=str(seed), STOCHASTIC_BUDGET=str(budget),
                   STOCHASTIC_RESTARTS=str(restarts))
        script = ROOT / f'grid_{grid}' / '2_classical_global_stochastic' / 'a7.py'
        result = dict(config=config, grid=grid, alpha=args.alpha, budget=budget,
                      seed=seed, restarts=restarts, status='failed')
        started = time.perf_counter()
        log_path = output / (key + '.log')
        try:
            with log_path.open('w', encoding='utf-8') as log:
                completed = subprocess.run([sys.executable, '-u', str(script), str(args.alpha)],
                    cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
            if completed.returncode:
                raise RuntimeError(f'Controller exited with code {completed.returncode}; see {log_path}')
            result['energy'], result['decisions'] = parse_output(log_path, budget, seed, restarts)
            result['status'] = 'success'
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
            result['error'] = str(exc)
        result['elapsed_seconds'] = time.perf_counter() - started
        save_json(result_path, result)
        results.append(result)
        summarize(output, results)
        print('  ' + result['status'] + ': ' + result.get('error', str(result.get('energy', {}))), flush=True)
    if not args.dry_run:
        summarize(output, results)
    return int(any(r['status'] != 'success' for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
