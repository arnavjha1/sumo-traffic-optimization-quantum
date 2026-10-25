"""Validation checks for the QAOA evaluation protocol."""
import json
from pathlib import Path
import tempfile
import unittest
from run_qaoa_evaluation import validate
from run_stochastic_evaluation import METRICS

class EvaluationValidationTests(unittest.TestCase):
    def test_complete_record_and_protocol_corruption(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            path = Path(tmp)
            raw = path / 'tripinfo.xml'
            raw.write_text('<tripinfos/>')
            snapshots = path / 'snapshots.jsonl'
            rows = [dict(decision=i, sampler_seed=301, grid='2x2', shots=512,
                         alpha_index=7, horizon_seconds=600) for i in range(1,601)]
            def save():
                snapshots.write_text('\n'.join(json.dumps(r) for r in rows))
            save()
            result = dict(config=dict(grid='2x2', seed=301), snapshot_path=str(snapshots),
                          energy=dict(shots=512,num_decisions=600),
                          supplementary=dict.fromkeys(METRICS,0))
            result['supplementary'].update(cutoff_seconds=600, departure_accounting_ok=True,
                                          arrival_accounting_ok=True,tripinfo_path=str(raw))
            validate(result)
            rows[20]['sampler_seed']=201
            save()
            with self.assertRaises(ValueError): validate(result)
            rows[20]['sampler_seed']=301
            rows.pop()
            save()
            with self.assertRaises(ValueError): validate(result)

if __name__ == '__main__': unittest.main()

