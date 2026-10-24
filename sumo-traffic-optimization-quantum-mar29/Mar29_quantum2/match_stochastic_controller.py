"""Tune energy distributions on seeds 201/202; validate winners on seed 203."""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path

import numpy as np
from replay_stochastic_calibration import load_instances, summarize

ROOT = Path(__file__).resolve().parent


def comparison(gaps, reference):
    # Equal-size pooled samples allow exact 1D empirical Wasserstein distance.
    reference = np.tile(reference, 3)
    scale = max(float(np.mean(reference)), 1.)
    distance = float(np.mean(np.abs(np.sort(gaps) - np.sort(reference))))
    recovery_difference = abs(float(np.mean(np.asarray(gaps) <= 1e-8)
                                    - np.mean(reference <= 1e-8)))
    mean_difference = abs(float(np.mean(gaps) - np.mean(reference))) / scale
    return dict(stochastic=summarize(gaps), qaoa=summarize(reference),
                wasserstein_gap=distance, scale=scale,
                recovery_difference=recovery_difference,
                normalized_mean_difference=mean_difference,
                score=distance / scale + recovery_difference,
                passes_screen=bool(recovery_difference <= .03 and
                                   mean_difference <= .2 and distance / scale <= .25))


def evaluate(optimizer, rows, settings):
    gaps = []
    for seed in [101, 102, 103]:
        rng = np.random.default_rng(seed)
        for row in rows:
            _, meta = optimizer.stochastic_decision(
                row['biases'], row['previous_state'], row['neighbors'], row['coupling_strength'],
                rng=rng, return_metadata=True, **settings)
            gap = meta['selected_energy'] - row['exact_min_energy']
            if gap < -1e-8 or meta['energy_evaluations'] != settings['evaluation_budget']:
                raise ValueError('Optimizer objective or budget mismatch')
            gaps.append(max(0., gap))
    return comparison(gaps, [r['optimality_gap'] for r in rows])


def main():
    rows, sources = load_instances(ROOT / 'qaoa_calibration_results')
    output = ROOT / 'stochastic_matching_results'
    output.mkdir(exist_ok=True)
    protocol = dict(tuning_qaoa_seeds=[201, 202], validation_qaoa_seeds=[203],
                    classical_seeds=[101, 102, 103], budgets=[2, 4, 8, 16, 32],
                    random_start_probabilities=[0., .5, 1.], temperatures=[5., 50.],
                    selection='minimum normalized Wasserstein distance plus absolute recovery-rate difference',
                    acceptance='recovery difference <= .03; mean difference / scale <= .20; Wasserstein / scale <= .25',
                    scale='max(QAOA mean gap, 1 energy unit)',
                    caveat='Exploratory screen, not a statistical equivalence test. Seed 203 was previously included in baseline replay summaries; it was not fully unseen. No traffic outcomes used.')
    (output / 'protocol.json').write_text(json.dumps(protocol, indent=2))
    for grid in ['2x2', '3x3']:
        path = ROOT / f'grid_{grid}/2_classical_global_stochastic/annealer_stochastic.py'
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        spec = importlib.util.spec_from_file_location('optimizer', path)
        optimizer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(optimizer)
        train = [r for r in rows if r['grid'] == grid and r['sampler_seed'] in [201, 202]]
        validation = [r for r in rows if r['grid'] == grid and r['sampler_seed'] == 203]
        if len(train) != 1200 or len(validation) != 600:
            raise ValueError('Unexpected calibration split')
        candidates = []
        for budget, probability, temperature in itertools.product(
                protocol['budgets'], protocol['random_start_probabilities'], protocol['temperatures']):
            settings = dict(evaluation_budget=budget, restarts=min(4, budget // 2),
                            random_start_probability=probability,
                            initial_temperature=temperature, final_temperature=.01)
            result = dict(settings=settings, tuning=evaluate(optimizer, train, settings))
            candidates.append(result)
            print(grid, len(candidates), '/ 30', flush=True)
        winner = min(candidates, key=lambda c: c['tuning']['score'])
        winner['validation'] = evaluate(optimizer, validation, winner['settings'])
        destination = output / f'{grid}.json'
        destination.write_text(json.dumps(dict(protocol=protocol, sources=sources,
            winner=winner, candidates=candidates), indent=2, allow_nan=False))
        print(grid, 'winner:', winner['settings'], 'validation passes:',
              winner['validation']['passes_screen'], flush=True)


if __name__ == '__main__':
    main()
