"""One bounded finer sweep; energy criteria are fixed before execution."""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path

import numpy as np
from replay_stochastic_calibration import load_instances, summarize

ROOT = Path(__file__).resolve().parent


def compare(gaps, reference):
    values = np.asarray(gaps)
    target = np.tile(reference, 3)
    positive = values[values > 1e-8]
    target_positive = target[target > 1e-8]
    scale = max(float(target.mean()), 1e-8)
    recovery_difference = abs(float(np.mean(values <= 1e-8) - np.mean(target <= 1e-8)))
    mean_relative_error = abs(float(values.mean() - target.mean())) / scale
    wasserstein_relative = float(np.mean(np.abs(np.sort(values) - np.sort(target)))) / scale
    if len(positive) and len(target_positive):
        # Descriptive quantile distance on mistakes only, separate from hit rate.
        quantiles = np.linspace(0, 1, 101)
        nonzero_distance = float(np.mean(np.abs(np.quantile(positive, quantiles)
                                               - np.quantile(target_positive, quantiles))))
        nonzero_relative = nonzero_distance / max(float(target_positive.mean()), 1e-8)
    else:
        nonzero_relative = None
    checks = dict(recovery=recovery_difference <= .03,
                  mean_gap=mean_relative_error <= .2,
                  gap_distribution=wasserstein_relative <= .25,
                  mistake_sizes=nonzero_relative is not None and nonzero_relative <= .25)
    violations = [recovery_difference / .03, mean_relative_error / .2,
                  wasserstein_relative / .25,
                  nonzero_relative / .25 if nonzero_relative is not None else 1e9]
    return dict(stochastic=summarize(values), qaoa=summarize(target),
                stochastic_mistakes=len(positive), qaoa_unique_mistakes=len(target_positive) // 3,
                recovery_difference=recovery_difference, mean_relative_error=mean_relative_error,
                wasserstein_relative=wasserstein_relative, nonzero_relative_distance=nonzero_relative,
                checks=checks, passes_screen=all(checks.values()),
                selection_score=[max(violations), sum(violations)])


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
                raise ValueError('Optimizer energy or budget mismatch')
            gaps.append(max(0., gap))
    return compare(gaps, [r['optimality_gap'] for r in rows])


def main():
    output = ROOT / 'stochastic_fine_matching_results'
    output.mkdir(exist_ok=True)
    candidates = {
        '2x2': list(itertools.product([24, 32, 40], [1, 2, 4], [20., 50.], [0., .25])),
        '3x3': list(itertools.product([20, 28, 36], [2, 3, 4], [35., 50., 70.], [.5, .75, 1.])),
    }
    protocol = dict(tuning_seeds=[201, 202], diagnostic_validation_seed=203,
                    classical_seeds=[101, 102, 103], candidate_grid=candidates,
                    criteria=dict(recovery_absolute=.03, mean_gap_relative=.20,
                                  wasserstein_relative=.25, nonzero_quantile_distance_relative=.25),
                    selection='Minimize worst threshold ratio, break ties with sum of ratios; tuning only.',
                    caveats='Exploratory tolerances, not proof of equivalence. Seed 203 has been inspected '
                            'previously and is diagnostic only. Rare 2x2 mistakes limit precision. '
                            'A passing candidate needs a fresh QAOA seed after settings freeze. No traffic outcomes used.')
    (output / 'protocol.json').write_text(json.dumps(protocol, indent=2))
    rows, sources = load_instances(ROOT / 'qaoa_calibration_results')
    sources['refine_stochastic_matching.py'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    for grid, combinations in candidates.items():
        path = ROOT / f'grid_{grid}/2_classical_global_stochastic/annealer_stochastic.py'
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        spec = importlib.util.spec_from_file_location('optimizer', path)
        optimizer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(optimizer)
        train = [r for r in rows if r['grid'] == grid and r['sampler_seed'] in [201, 202]]
        validation = [r for r in rows if r['grid'] == grid and r['sampler_seed'] == 203]
        if len(train) != 1200 or len(validation) != 600:
            raise ValueError('Unexpected input split')
        results = []
        for budget, restarts, temperature, probability in combinations:
            settings = dict(evaluation_budget=budget, restarts=restarts,
                            initial_temperature=temperature, final_temperature=.01,
                            random_start_probability=probability)
            result = dict(settings=settings, tuning=evaluate(optimizer, train, settings))
            results.append(result)
            # Checkpoint every candidate so progress and partial evidence survive interruption.
            (output / f'{grid}_candidates.json').write_text(json.dumps(results, indent=2, allow_nan=False))
            print(f'{grid}: {len(results)}/{len(combinations)}; passing tuning candidates: '
                  f'{sum(r["tuning"]["passes_screen"] for r in results)}', flush=True)
        winner = min(results, key=lambda r: r['tuning']['selection_score'])
        winner = dict(winner, validation=evaluate(optimizer, validation, winner['settings']))
        (output / f'{grid}.json').write_text(json.dumps(dict(protocol=protocol, sources=sources,
            winner=winner, candidates=results), indent=2, allow_nan=False))
        print(grid, 'selected:', winner['settings'], 'tuning:', winner['tuning']['passes_screen'],
              'diagnostic validation:', winner['validation']['passes_screen'], flush=True)


if __name__ == '__main__':
    main()
