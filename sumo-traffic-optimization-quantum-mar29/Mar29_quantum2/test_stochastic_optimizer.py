"""Objective, budget, and reproducibility checks independent of SUMO."""
import importlib.util
import itertools
from pathlib import Path
import unittest

import numpy as np


class StochasticOptimizerTests(unittest.TestCase):
    def test_objective_budget_and_seed_on_both_grids(self):
        for grid, width in [('2x2', 2), ('3x3', 3)]:
            path = Path(__file__).parent / f'grid_{grid}/2_classical_global_stochastic/annealer_stochastic.py'
            spec = importlib.util.spec_from_file_location('optimizer', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            n = width * width
            neighbors = [[j for j in range(n) if abs(i // width - j // width)
                          + abs(i % width - j % width) == 1] for i in range(n)]
            fixture_rng = np.random.default_rng(92)
            for _ in range(10):
                biases = fixture_rng.uniform(-20, 20, n)
                previous = fixture_rng.integers(0, 2, n)

                def energy(bits):
                    spins = 2 * np.asarray(bits) - 1
                    return -np.dot(biases + 10 * (2 * previous - 1), spins) - sum(
                        2 * spins[i] * spins[j] for i in range(n) for j in neighbors[i] if i < j)

                exact = min(energy(bits) for bits in itertools.product([0, 1], repeat=n))
                for budget in [2, 8, 17, 64]:
                    kwargs = dict(evaluation_budget=budget, restarts=min(4, budget // 2), return_metadata=True)
                    state, meta = module.stochastic_decision(biases, previous, neighbors,
                        rng=np.random.default_rng(101), **kwargs)
                    repeat, repeat_meta = module.stochastic_decision(biases, previous, neighbors,
                        rng=np.random.default_rng(101), **kwargs)
                    self.assertEqual(state, repeat)
                    self.assertEqual(meta['selected_energy'], repeat_meta['selected_energy'])
                    self.assertEqual(meta['energy_evaluations'], budget)
                    self.assertAlmostEqual(meta['selected_energy'], energy(list(map(int, state))))
                    self.assertGreaterEqual(meta['selected_energy'] + 1e-8, exact)


if __name__ == '__main__':
    unittest.main()
