"""Export descriptive energy/budget diagnostics and saved common-state matching checks."""
import json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data_analysis/population_accounting_comparison'

def stats(values):
    x=np.asarray(values,dtype=float)
    return dict(mean=float(x.mean()),median=float(np.median(x)),sd=float(x.std(ddof=1)),
                q25=float(np.quantile(x,.25)),q75=float(np.quantile(x,.75)),
                recovery=float(np.mean(x<=1e-8)))

def main():
    groups=[]; matching=[]
    for grid in ('2x2','3x3'):
        for controller,folder in [('Classical stochastic','stochastic_evaluation_results'),('QAOA','qaoa_evaluation_results')]:
            runs=[]; pooled=[]; normalized=[];circuits=[];shots=[];evaluations=[]
            for seed in range(301,321):
                p=ROOT/folder/f'{grid}_a7_seed{seed}.json'
                result=json.loads(p.read_text())
                assert result['status']=='success'
                if controller=='QAOA':
                    decisions=[json.loads(line) for line in Path(result['snapshot_path']).read_text().splitlines()]
                    circuits.extend(d['qaoa']['circuit_count'] for d in decisions)
                    shots.extend(d['qaoa']['total_shots'] for d in decisions)
                else:
                    decisions=result['decisions']
                    evaluations.extend(d['energy_evaluations'] for d in decisions)
                assert len(decisions)==600
                gaps=[max(0.,d['optimality_gap']) for d in decisions]
                assert all(d['optimality_gap']>=-1e-8 for d in decisions)
                assert all(abs(d['selected_energy']-d['exact_min_energy']-d['optimality_gap'])<1e-6 for d in decisions)
                normalized.extend(d['optimality_gap']/abs(d['exact_min_energy']) for d in decisions if abs(d['exact_min_energy'])>1e-9)
                pooled.extend(gaps)
                runs.append(dict(seed=seed,**stats(gaps)))
            groups.append(dict(grid=grid,controller=controller,pooled=stats(pooled),runs=runs,
                               gaps=pooled,relative_gaps=normalized,
                               circuit_count_range=[min(circuits),max(circuits)] if circuits else None,
                               circuit_count_mean=float(np.mean(circuits)) if circuits else None,
                               total_shots_range=[min(shots),max(shots)] if shots else None,
                               total_shots_mean=float(np.mean(shots)) if shots else None,
                               energy_evaluations_range=[min(evaluations),max(evaluations)] if evaluations else None))
        record=json.loads((ROOT/f'stochastic_fine_matching_results/{grid}.json').read_text())
        for stage in ('tuning','validation'):
            d=record['winner'][stage]
            matching.append(dict(grid=grid,stage=stage,settings=record['winner']['settings'],
                                 stochastic=d['stochastic'],qaoa=d['qaoa'],checks=d['checks'],
                                 recovery_difference=d['recovery_difference'],passes=d['passes_screen']))
    (OUT/'optimizer_diagnostics.json').write_text(json.dumps(dict(groups=groups,matching=matching),indent=2))
    print('Saved energy diagnostics: 12,000 decisions per controller/grid; pooled distributions are descriptive only.')

if __name__=='__main__':main()
