"""Build a population-aware supplement without modifying any controller."""
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from supplementary_traffic_metrics import summarize_tripinfo
SOURCES = [('classical_global_accounting_results', 'Classical global SA'),
           ('stochastic_evaluation_results', 'Classical stochastic'),
           ('qaoa_evaluation_results', 'QAOA')]
METRICS = {
    'completed_mean_travel_seconds': 'Completed-trip travel (s)',
    'completed_mean_waiting_seconds': 'Completed-trip waiting (s)',
    'completed_trips': 'Completed trips',
    'unfinished_trips': 'Unfinished trips',
    'removed_trips': 'Removed trips',
    'completion_fraction_of_departed': 'Completion fraction of entered vehicles',
    'network_time_loss_seconds': 'In-network time loss (vehicle-s)',
    'network_waiting_seconds': 'In-network stopped waiting (vehicle-s)',
    'pending_insertion_at_cutoff': 'Pending insertion at cutoff',
    'pending_insertion_vehicle_seconds_sampled': 'Insertion backlog integral (vehicle-s)',
}

def load_runs():
    groups = {}
    for folder, label in SOURCES:
        manifest_path = ROOT / folder / 'manifest.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        configs = manifest.get('configurations', [])
        for grid in ('2x2', '3x3'):
            expected = [c for c in configs if c['grid'] == grid]
            runs, failures = [], []
            for config in expected:
                path = ROOT / folder / f'{grid}_a7_seed{config["seed"]}.json'
                if not path.exists(): continue
                result = json.loads(path.read_text())
                if result.get('status') != 'success':
                    failures.append(config['seed'])
                    continue
                if result['config'] != config: raise ValueError(f'Provenance mismatch: {path}')
                s = result['supplementary']
                if s['cutoff_seconds'] != 600 or not all(s[k] for k in ('departure_accounting_ok','arrival_accounting_ok')):
                    raise ValueError(f'Invalid accounting: {path}')
                raw = summarize_tripinfo(s['tripinfo_path'])
                for key, value in raw.items():
                    if value != s[key]: raise ValueError(f'Raw tripinfo mismatch: {path}: {key}')
                if s['departed_trips'] != s['completed_trips'] + s['unfinished_trips'] + s['removed_trips']:
                    raise ValueError(f'Population mismatch: {path}')
                runs.append(dict(seed=config['seed'], source=str(path.relative_to(ROOT)), metrics={k:s[k] for k in METRICS}))
            groups[(grid,label)] = dict(expected=len(expected), successful=len(runs), failed_seeds=failures, runs=runs)
    return groups

def main():
    groups = load_runs()
    output = ROOT / 'data_analysis/population_accounting_comparison'
    output.mkdir(parents=True,exist_ok=True)
    lines = ['# Supplementary traffic population and delay comparison', '',
             'WORKING RESULTS: QAOA collection may be incomplete. This report reads only completed, successful evaluation runs; calibration and validation runs are excluded.', '',
             'All runs use alpha 0.7 and a 600-second cutoff. Entries are the mean ± sample SD across optimizer seeds. These are fixed-demand optimizer replications, not independent traffic-demand replications. No controller decisions are modified.', '']
    if all(g['successful'] == g['expected'] == 20 for g in groups.values()):
        lines[2] = 'COMPLETE EVALUATION: 20 successful runs per controller and grid. Calibration and validation runs are excluded. Confidence intervals for controller differences are provided in effect_estimates.md.'
    records = []
    for grid in ('2x2','3x3'):
        labels = [label for _,label in SOURCES]
        lines += [f'## {grid}', '', '| Measure | ' + ' | '.join(labels) + ' |', '|---|' + '---:|'*len(labels)]
        lines.append('| Successful / planned runs | '+' | '.join(f"{groups[(grid,l)]['successful']} / {groups[(grid,l)]['expected']}" for l in labels)+' |')
        for key, title in METRICS.items():
            cells=[]
            for label in labels:
                group = groups[(grid,label)]
                values=[r['metrics'][key] for r in group['runs'] if r['metrics'][key] is not None]
                mean=statistics.mean(values) if values else None
                sd=statistics.stdev(values) if len(values)>1 else None
                cells.append('Pending' if not values else f'{mean:.3f}' + (f' ± {sd:.3f}' if sd is not None else ' (n=1)'))
                records.append(dict(grid=grid,controller=label,metric=key,n=len(values),mean=mean,sd=sd,complete=group['successful']==group['expected'] and group['expected']>0))
            lines.append('| '+title+' | '+' | '.join(cells)+' |')
        lines += ['', 'Failed seeds: '+ '; '.join(f"{label}: {groups[(grid,label)]['failed_seeds']}" for label in labels), '']
    lines += ['## Definitions and interpretation', '',
              '- Completed-trip averages describe only vehicles arriving before the cutoff. Unfinished-trip eventual travel times are not imputed.',
              '- In-network time loss is SUMO timeLoss accumulated by all entered vehicles, including completed, unfinished, and removed vehicles. It differs from stopped waiting.',
              '- In-network stopped waiting sums SUMO waitingTime over the same entered population.',
              '- Pending vehicles have not entered the network. Their backlog is reported separately; the backlog integral is a discrete right-endpoint sum and must not be described as SUMO timeLoss.',
              '- Completion fraction uses entered vehicles as its denominator; it excludes vehicles pending insertion and future demand.',
              '- Assess trip averages together with completions, unfinished trips, total delay, and backlog. Lower completed-trip means alone do not establish a system-level improvement.',
              '- The current instrumented global baseline is labeled simulated annealing according to its implementation. Exhaustive energy diagnostics do not make action selection exact.',
              '- Controller differences and uncertainty are reported separately in effect_estimates.md; interpret pointwise intervals alongside multiplicity-adjusted tests. A zero SD describes the observed seeds only; it does not imply certainty under other demand scenarios.', '']
    (output/'comparison.md').write_text('\n'.join(lines),encoding='utf-8')
    (output/'comparison.json').write_text(json.dumps(dict(summary=records,groups=[dict(grid=g,controller=l,**v) for (g,l),v in groups.items()]),indent=2),encoding='utf-8')
    print(output/'comparison.md')
    for (grid,label),group in groups.items(): print(grid,label,group['successful'],'/',group['expected'])

if __name__=='__main__': main()
