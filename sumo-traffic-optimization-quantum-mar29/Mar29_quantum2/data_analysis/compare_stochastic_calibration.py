"""Compare saved alpha-0.7 calibration summaries; does not select a winner."""
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]


def summarize(grid, controller, runs, sources, budget=None):
    decisions = sum(r['num_decisions'] for r in runs)
    misses = sum(r['num_decisions'] - r['optimal_hits'] for r in runs)
    return dict(grid=grid, controller=controller, budget=budget, runs=len(runs),
        recovery_percent=100 * statistics.mean(r['optimum_recovery_rate'] for r in runs),
        recovery_sd_percentage_points=100 * statistics.stdev(r['optimum_recovery_rate'] for r in runs),
        mean_gap=statistics.mean(r['average_optimality_gap'] for r in runs),
        mean_gap_sd=statistics.stdev(r['average_optimality_gap'] for r in runs),
        pooled_nonzero_gap_mean_approx=(sum(r['average_optimality_gap'] * r['num_decisions'] for r in runs) / misses
                                       if misses else None),
        decisions=decisions, sources=sources)


def main():
    rows = []
    for grid, source in [('2x2', 'quantum_data/quantum_simulation_results.json'),
                         ('3x3', 'quantum_data_3x3/quantum_3x3_simulation_results.json')]:
        qaoa = json.loads((ROOT / source).read_text())['a7']['runs']
        assert len(qaoa) == 20 and all(r['num_decisions'] == 600 for r in qaoa)
        rows.append(summarize(grid, 'QAOA (512 shots)', qaoa, [source]))
        for budget in [8, 16, 32, 64, 128]:
            paths = [ROOT / 'stochastic_calibration_results' / f'{grid}_a7_budget{budget}_seed{s}.json'
                     for s in [101, 102, 103]]
            records = [json.loads(p.read_text()) for p in paths]
            assert all(r['status'] == 'success' and r['restarts'] == 4 for r in records)
            rows.append(summarize(grid, 'Classical stochastic', [r['energy'] for r in records],
                                  [str(p.relative_to(ROOT)) for p in paths], budget))
    directory = ROOT / 'data_analysis' / 'stochastic_calibration_comparison'
    directory.mkdir(exist_ok=True)
    (directory / 'comparison.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    lines = ['# Alpha 0.7: QAOA and stochastic calibration', '',
        'Each run contains 600 decisions. Means and sample standard deviations are across runs.', '',
        '| Network | Controller | Budget | Runs | Recovery % (mean ± SD) | Gap (mean ± SD) | Approx. mean nonzero gap |',
        '|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        lines.append(f"| {r['grid']} | {r['controller']} | {r['budget'] or '—'} | {r['runs']} | "
                     f"{r['recovery_percent']:.2f} ± {r['recovery_sd_percentage_points']:.2f} | "
                     f"{r['mean_gap']:.5f} ± {r['mean_gap_sd']:.5f} | {r['pooled_nonzero_gap_mean_approx']:.3f} |")
    lines += ['', '## Interpretation and limitations', '',
        '- QAOA budgets are shots; stochastic budgets count energy evaluations. These are not equal-cost budgets.',
        '- The approximate pooled nonzero-gap mean is total gap divided by non-optimal decisions, reconstructed from summaries. It assumes optimal-hit gaps are numerically zero; it is not a recovered distribution.',
        '- Saved QAOA records contain run-level energy summaries and selected-energy logs, but no per-decision exact-minimum sequence or Hamiltonian snapshots. Gap quantiles and distribution matching cannot be established.',
        '- These controllers encounter different closed-loop Hamiltonians. These numbers screen candidates; they do not establish matching on common instances.',
        '- 2x2 budget 32 approximately matches recovery but has smaller gaps. Budget 16 has a higher mean gap and substantially lower recovery.',
        '- 3x3 budget 16 approximately matches recovery but has much smaller gaps. Budget 8 approximately matches mean gap but has much lower recovery.',
        '- No tested budget matches both QAOA summary targets closely. Do not choose by traffic outcomes.',
        '- All 30 inspected stochastic result JSON files lack the supplementary vehicle-accounting block; they remain useful for energy calibration, not the reviewer population/delay comparison.',
        '', '## QAOA sources', '',
        '- quantum_data/quantum_simulation_results.json, a7, 20 runs',
        '- quantum_data_3x3/quantum_3x3_simulation_results.json, a7, 20 runs',
        '', 'Per-row source paths are retained in comparison.json.']
    (directory / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines[:18]))


if __name__ == '__main__':
    main()
