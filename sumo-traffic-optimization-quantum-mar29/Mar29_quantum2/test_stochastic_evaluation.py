"""Evaluation must reject wrong settings and inconsistent traffic accounting."""
import copy
from pathlib import Path
import tempfile
import unittest

from run_stochastic_evaluation import validate_result


class EvaluationValidationTests(unittest.TestCase):
    def test_success_and_corruption_rejection(self):
        settings = dict(evaluation_budget=28, restarts=4, random_start_probability=.5,
                        initial_temperature=50., final_temperature=.01)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            raw = Path(directory) / 'tripinfo.xml'
            raw.write_text('<tripinfos/>')
            decision = dict(settings, energy_evaluations=28)
            result = dict(energy=dict(seed=301, num_decisions=600),
                decisions=[decision.copy() for _ in range(600)],
                supplementary=dict(cutoff_seconds=600, departure_accounting_ok=True,
                    arrival_accounting_ok=True, tripinfo_path=str(raw),
                    completed_mean_travel_seconds=10, completed_mean_waiting_seconds=2,
                    completed_trips=5, unfinished_trips=3, removed_trips=0,
                    network_time_loss_seconds=15, network_waiting_seconds=8,
                    pending_insertion_at_cutoff=0, pending_insertion_vehicle_seconds_sampled=0))
            validate_result(result, settings, 301)
            corrupted = copy.deepcopy(result)
            corrupted['decisions'][0]['random_start_probability'] = 0
            with self.assertRaises(ValueError):
                validate_result(corrupted, settings, 301)
            corrupted = copy.deepcopy(result)
            corrupted['supplementary']['arrival_accounting_ok'] = False
            with self.assertRaises(ValueError):
                validate_result(corrupted, settings, 301)
            corrupted = copy.deepcopy(result)
            corrupted['supplementary']['cutoff_seconds'] = 599
            with self.assertRaises(ValueError):
                validate_result(corrupted, settings, 301)
            raw.unlink()
            with self.assertRaises(ValueError):
                validate_result(result, settings, 301)


if __name__ == '__main__':
    unittest.main()
