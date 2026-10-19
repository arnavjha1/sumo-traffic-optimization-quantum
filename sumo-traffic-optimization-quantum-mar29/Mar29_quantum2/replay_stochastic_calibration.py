"""Compare classical annealing and QAOA on identical recorded Hamiltonians.

Uses only successful, full-horizon recorder runs by default. Does not select
settings using traffic outcomes or equate energy evaluations with QAOA shots.
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def load_instances(folder, allow_smoke=False):
    instances = []
    sources = {}
    for path in sorted(folder.glob('*.json')):
        result = json.loads(path.read_text(encoding='utf-8'))
        if result.get('status') != 'success' or 'snapshot_path' not in result:
            continue
        config = result['config']
        if config['horizon'] < 600 and not allow_smoke:
            raise ValueError(f'{path.name}: short run; use --allow-smoke only for validation')
        snapshots = folder / Path(result['snapshot_path']).name
        rows = [json.loads(line) for line in snapshots.read_text().splitlines()]
        if len(rows) != result['energy']['num_decisions'] or not rows:
            raise ValueError(f'{path.name}: incomplete snapshots')
        sources[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        sources[snapshots.name] = hashlib.sha256(snapshots.read_bytes()).hexdigest()
        for index, row in enumerate(rows, 1):
            if (row['decision'] != index or row['grid'] != config['grid']
                    or row['sampler_seed'] != config['seed']
                    or row['alpha_index'] != config['alpha']
                    or row['switching_penalty'] != 10):
                raise ValueError(f'{snapshots.name}: inconsistent snapshot context')
            # Independently check the reference minimum and selected QAOA energy.
            states = np.asarray(list(itertools.product([0, 1], repeat=len(row['biases']))))
            spins = 2 * states - 1
            fields = np.asarray(row['biases']) + 10 * (2 * np.asarray(row['previous_state']) - 1)
            energies = -spins @ fields
            for i, adjacent in enumerate(row['neighbors']):
                for j in adjacent:
                    if i < j:
                        energies -= row['coupling_strength'] * spins[:, i] * spins[:, j]
            selected = int(row['selected_state'], 2)
            if not (np.isclose(energies.min(), row['exact_min_energy'], atol=1e-8, rtol=0)
                    and np.isclose(energies[selected], row['selected_energy'], atol=1e-8, rtol=0)
                    and np.isclose(row['selected_energy'] - energies.min(), row['optimality_gap'], atol=1e-8, rtol=0)):
                raise ValueError(f'{snapshots.name}: energy convention mismatch')
            instances.append(row)
    if not instances:
        raise ValueError('No successful recorder runs found')
    return instances, sources


def summarize(gaps):
    values = np.asarray(gaps)
    return dict(decisions=len(values), recovery_rate=float(np.mean(values <= 1e-8)),
                mean_gap=float(values.mean()),
                gap_quantiles=dict(zip(['q25', 'q50', 'q75', 'q90', 'q95', 'q99'],
                                      map(float, np.quantile(values, [.25, .5, .75, .9, .95, .99])))))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'qaoa_calibration_results')
    parser.add_argument('--output', type=Path, default=ROOT / 'stochastic_replay_results')
    parser.add_argument('--budgets', type=int, nargs='+', default=[8, 16, 32, 64, 128])
    parser.add_argument('--seeds', type=int, nargs='+', default=[101, 102, 103])
    parser.add_argument('--allow-smoke', action='store_true')
    args = parser.parse_args()
    if min(args.budgets) < 2 or min(args.seeds) < 0:
        parser.error('Budgets must be >= 2 and seeds nonnegative')
    rows, sources = load_instances(args.input, args.allow_smoke)
    args.output.mkdir(parents=True, exist_ok=True)
    summaries = []
    for grid in sorted({r['grid'] for r in rows}):
        optimizer_path = ROOT / f'grid_{grid}/2_classical_global_stochastic/annealer_stochastic.py'
        sources[str(optimizer_path.relative_to(ROOT))] = hashlib.sha256(optimizer_path.read_bytes()).hexdigest()
        spec = importlib.util.spec_from_file_location('optimizer', optimizer_path)
        optimizer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(optimizer)
        for alpha in sorted({r['alpha_index'] for r in rows if r['grid'] == grid}):
            subset = [r for r in rows if r['grid'] == grid and r['alpha_index'] == alpha]
            reference = summarize([r['optimality_gap'] for r in subset])
            for budget, seed in itertools.product(dict.fromkeys(args.budgets), dict.fromkeys(args.seeds)):
                rng = np.random.default_rng(seed)
                decisions = []
                for row in subset:
                    state, metadata = optimizer.stochastic_decision(
                        row['biases'], row['previous_state'], row['neighbors'], row['coupling_strength'],
                        rng=rng, evaluation_budget=budget, restarts=min(4, budget // 2), return_metadata=True)
                    gap = metadata['selected_energy'] - row['exact_min_energy']
                    if gap < -1e-8 or metadata['energy_evaluations'] != budget:
                        raise ValueError('Invalid optimizer energy or budget')
                    decisions.append(dict(qaoa_seed=row['sampler_seed'], decision=row['decision'],
                                          state=state, gap=max(0., gap), qaoa_gap=row['optimality_gap']))
                summaries.append(dict(grid=grid, alpha=alpha, budget=budget, seed=seed,
                                      stochastic=summarize([d['gap'] for d in decisions]), qaoa=reference))
                destination = args.output / f'{grid}_a{alpha}_budget{budget}_seed{seed}.json'
                destination.write_text(json.dumps(dict(summary=summaries[-1], decisions=decisions), indent=2, allow_nan=False))
    (args.output / 'summary.json').write_text(json.dumps(dict(
        validation_only=args.allow_smoke, sources=sources, summaries=summaries,
        interpretation='Paired common-instance energy calibration only; decisions are dependent within trajectories. '
                       'Energy evaluations are not equal-cost QAOA shots. No traffic-based setting selection.'), indent=2, allow_nan=False))
    print(f'Wrote {len(summaries)} replay comparisons to {args.output}')


if __name__ == '__main__':
    main()
