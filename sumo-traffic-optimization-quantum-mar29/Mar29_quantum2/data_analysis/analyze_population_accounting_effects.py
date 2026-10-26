"""Run-level independent bootstrap comparisons for fixed-demand evaluations."""
import json
from pathlib import Path
import numpy as np
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parents[1]
DRAWS = 50000
SEED = 20261025
PAIRS = [('QAOA','Classical global SA'),
         ('Classical stochastic','Classical global SA'),
         ('QAOA','Classical stochastic')]

def interval(a, b, rng, draws=DRAWS):
    a,b=np.asarray(a,dtype=float),np.asarray(b,dtype=float)
    if len(a)<2 or len(b)<2: raise ValueError('At least two runs per controller required')
    differences=(a[rng.integers(len(a),size=(draws,len(a)))].mean(axis=1)
                 -b[rng.integers(len(b),size=(draws,len(b)))].mean(axis=1))
    return np.quantile(differences,[.025,.975]).tolist()

def main():
    folder=ROOT/'data_analysis/population_accounting_comparison'
    data=json.loads((folder/'extended_comparison.json').read_text())
    if not all(row['complete'] and row['n']==20 for row in data['summary']):
        raise ValueError('Final analysis requires all 20 runs per controller and grid')
    groups={(g['grid'],g['controller']):g['runs'] for g in data['groups']}
    metrics=list(groups[('2x2','QAOA')][0]['metrics'])
    rng=np.random.default_rng(SEED)
    results=[]
    lines=['# Run-level controller differences','',
           'Each estimate is the first controller minus the comparator. Negative values favor the first controller for travel, waiting, delay, unfinished trips, removals and backlog; positive values favor it for completions and completion fraction. Unfinished counts still need to be interpreted with entry and completion populations.','',
           'Intervals are independent two-sample percentile bootstrap 95% confidence intervals using 50,000 resamples of whole runs (fixed random seed 20261025). Numeric seed labels are not treated as paired traffic scenarios. Demand is fixed; uncertainty concerns optimizer randomness only. These are pointwise exploratory intervals, without adjustment for multiple comparisons. An interval spanning zero does not establish equivalence. No per-decision or per-vehicle pseudoreplication is used.','']
    for grid in ('2x2','3x3'):
        for first,second in PAIRS:
            lines += [f'## {grid}: {first} minus {second}', '',
                      '| Metric | Mean difference | 95% CI | Relative to comparator |',
                      '|---|---:|---:|---:|']
            for metric in metrics:
                a=[r['metrics'][metric] for r in groups[(grid,first)]]
                b=[r['metrics'][metric] for r in groups[(grid,second)]]
                if any(v is None for v in a+b): raise ValueError('Missing value: '+metric)
                diff=float(np.mean(a)-np.mean(b))
                low,high=interval(a,b,rng)
                base=float(np.mean(b))
                relative=100*diff/base if base else None
                if base:
                    boot_a=np.asarray(a)[rng.integers(len(a),size=(DRAWS,len(a)))].mean(axis=1)
                    boot_b=np.asarray(b)[rng.integers(len(b),size=(DRAWS,len(b)))].mean(axis=1)
                    relative_ci=np.quantile(100*(boot_a/boot_b-1),[.025,.975]).tolist()
                else: relative_ci=[None,None]
                va=0.0 if np.ptp(a)==0 else float(np.var(a,ddof=1))/len(a)
                vb=0.0 if np.ptp(b)==0 else float(np.var(b,ddof=1))/len(b)
                if va+vb:
                    df=(va+vb)**2/(va**2/(len(a)-1)+vb**2/(len(b)-1))
                    pvalue=float(2*student_t.sf(abs(diff)/(va+vb)**.5,df))
                else: pvalue=None
                results.append(dict(grid=grid,first=first,comparator=second,metric=metric,
                                    difference=diff,ci95_low=low,ci95_high=high,
                                    relative_percent=relative,relative_ci95_low=relative_ci[0],relative_ci95_high=relative_ci[1],p_welch=pvalue,n_first=len(a),n_comparator=len(b)))
                rel='Undefined (zero comparator)' if relative is None else f'{relative:+.2f}%'
                lines.append(f'| {metric} | {diff:+.4f} | [{low:+.4f}, {high:+.4f}] | {rel} |')
            lines.append('')
    lines += ['## Reporting limits','',
              'All-zero removed-trip counts produce a degenerate interval for the observed runs, not evidence that removals are impossible. The zero-variance 2x2 global baseline is likewise conditional on this fixed demand and these optimizer settings. Report insertion backlog separately from SUMO timeLoss. Do not add overlapping waiting and timeLoss measures into a combined delay score.','',
              'These supplementary comparisons use the current instrumented global simulated-annealing baseline. They do not by themselves establish conclusions about a different exact action-selecting controller or historical metrics. The stochastic control was calibration-informed but did not pass all energy-distribution matching checks; it is not a validated distribution match.','']
    tested=sorted([r for r in results if r['p_welch'] is not None],key=lambda r:r['p_welch'])
    running=0.0
    for index,r in enumerate(tested):
        running=max(running,min(1.0,(len(tested)-index)*r['p_welch']))
        r['p_holm']=running
    for r in results: r.setdefault('p_holm',None)
    lines += ['Welch two-sample tests and Holm-adjusted p values are provided in the JSON and revised statistical tables. Holm adjustment spans all nonconstant metrics, grids, and controller pairs in this exploratory analysis. No primary outcome is claimed to have been prespecified. Welch tests are approximate with 20 potentially skewed optimizer outcomes; interpret alongside distributions and bootstrap estimates. Bootstrap intervals remain pointwise, not simultaneous.']
    (folder/'effect_estimates.md').write_text('\n'.join(lines),encoding='utf-8')
    (folder/'effect_estimates.json').write_text(json.dumps(dict(method='independent run-level percentile bootstrap',draws=DRAWS,seed=SEED,holm_family_size=len(tested),results=results),indent=2),encoding='utf-8')
    print(folder/'effect_estimates.md')
    for r in results:
        if r['first']=='QAOA' and r['metric'] in ('completed_mean_travel_seconds','completed_mean_waiting_seconds','completed_trips','network_time_loss_seconds','pending_insertion_vehicle_seconds_sampled'):
            print(r['grid'],r['comparator'],r['metric'],round(r['difference'],3),[round(r['ci95_low'],3),round(r['ci95_high'],3)])

if __name__=='__main__': main()
