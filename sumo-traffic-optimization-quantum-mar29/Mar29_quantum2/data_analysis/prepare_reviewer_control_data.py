"""Export provenance-separated reviewer control data; do not mix metric definitions."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIELDS = ['grid', 'controller', 'role', 'seed_or_run', 'source', 'metric_basis',
          'travel_seconds', 'waiting_seconds', 'completed_trips', 'unfinished_trips',
          'network_time_loss_seconds', 'network_waiting_seconds', 'pending_insertion_at_cutoff']


def main():
    rows = []
    for folder, controller, role in [
        ('qaoa_evaluation_results', 'QAOA', 'evaluation'),
        ('stochastic_evaluation_results', 'Classical stochastic', 'evaluation'),
        ('classical_global_accounting_results', 'Classical global SA', 'evaluation'),
        ('qaoa_calibration_results', 'QAOA', 'calibration_descriptive_only')]:
        for path in sorted((ROOT / folder).glob('*.json')):
            data = json.loads(path.read_text())
            if data.get('status') != 'success' or 'supplementary' not in data:
                continue
            config, s = data['config'], data['supplementary']
            if s['cutoff_seconds'] != 600 or not all(s[k] for k in ['departure_accounting_ok', 'arrival_accounting_ok']):
                raise ValueError(f'Invalid accounting: {path}')
            rows.append(dict(grid=config['grid'], controller=controller, role=role,
                seed_or_run=config['seed'], source=str(path.relative_to(ROOT)),
                metric_basis='SUMO tripinfo; completed-trip duration and full-trip waiting',
                travel_seconds=s['completed_mean_travel_seconds'],
                waiting_seconds=s['completed_mean_waiting_seconds'],
                **{k: s[k] for k in FIELDS[9:]}))
            rows[-1]['completed_trips'] = s['completed_trips']
    for grid, filename in [('2x2', 'quantum_data/quantum_simulation_results.json'),
                           ('3x3', 'quantum_data_3x3/quantum_3x3_simulation_results.json')]:
        data = json.loads((ROOT / filename).read_text())
        for run in data['a7']['runs']:
            rows.append(dict(grid=grid, controller='QAOA', role='historical_evaluation',
                seed_or_run=run['run'], source=filename,
                metric_basis='Legacy printed metrics; not interchangeable with full-trip waiting',
                travel_seconds=run['average_travel_time'], waiting_seconds=run['average_waiting_time'],
                completed_trips=run['throughput']))
    data = json.loads((ROOT / 'all_alpha_results.json').read_text())
    # Preserve complete original records for baseline provenance rather than guessing fields.
    baselines = [r for r in data['runs'] if r['controller'] == 'classical_global' and r['alpha_index'] == 7]
    output = ROOT / 'data_analysis/reviewer_control_comparison'
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'available_runs.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    (output / 'historical_global_baseline_records.json').write_text(json.dumps(baselines, indent=2))
    (output / 'README.md').write_text(
        '# Reviewer comparison readiness\n\n'
        'available_runs.csv separates fresh evaluation, calibration, and historical data. '
        'Do not pool these roles or compare legacy waiting means directly with full-trip waiting.\n\n'
        'QAOA calibration recordings provide descriptive supplementary metrics only; '
        'fresh QAOA evaluation is read from qaoa_evaluation_results when available. Current baseline scripts implement '
        'simulated annealing, not exact action selection. Their new accounting runs must be '
        'labeled accordingly; historical equivalence has not been established.\n\n'
        'New baseline output is picked up from classical_global_accounting_results on rerun. '
        'Validation folders are intentionally excluded. Final inference and figures are pending '
        'comparable controller data.\n', encoding='utf-8')
    print(f'Exported {len(rows)} records to {output}')


if __name__ == '__main__':
    main()
