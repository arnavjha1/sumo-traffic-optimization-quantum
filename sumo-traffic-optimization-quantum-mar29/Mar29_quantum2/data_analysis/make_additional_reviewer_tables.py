"""Additional LaTeX diagnostics and multiplicity-aware statistical tables."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'graphs/reviewer_population_accounting'
DATA=ROOT/'data_analysis/population_accounting_comparison'
LABEL={'Classical global SA':'Global SA','Classical stochastic':'Stochastic','QAOA':'QAOA'}

def table(name,caption,label,columns,header,rows):
    text='\n'.join([r'\begin{table}[tbp]',r'\centering',r'\small',r'\caption{'+caption+'}',
                    r'\label{tab:'+label+'}',r'\resizebox{\linewidth}{!}{%',r'\begin{tabular}{'+columns+'}',
                    r'\toprule',header+r' \\',r'\midrule',*[r+' \\\\' for r in rows],
                    r'\bottomrule',r'\end{tabular}}',r'\end{table}'])
    (OUT/name).write_text(text+'\n',encoding='utf-8')
    return name

def pformat(value):
    if value is None:return '--'
    return '$<0.0001$' if value<.0001 else f'{value:.4f}'

def main():
    energy=json.loads((DATA/'optimizer_diagnostics.json').read_text())
    audits=json.loads((DATA/'demand_accounting_audit.json').read_text())
    effects=json.loads((DATA/'effect_estimates.json').read_text())
    data=json.loads((DATA/'extended_comparison.json').read_text())
    fragments=[]; rows=[]
    for group in data['groups']:
        runs=group['runs']; sums=lambda key:sum(r['metrics'][key] for r in runs)/len(runs)
        residual=[r['population_residual'] for r in audits['runs'] if r['grid']==group['grid'] and r['controller']==group['controller']]
        rows.append(' & '.join([group['grid'],LABEL[group['controller']],str(len(runs)),f"{sums('realized_demand_trips'):.0f}",f"{sums('completed_trips'):.2f}",f"{sums('unfinished_trips'):.2f}",f"{sums('removed_trips'):.0f}",f"{sums('pending_insertion_at_cutoff'):.2f}",str(max(abs(x) for x in residual))]))
    fragments.append(table('table_demand_audit.tex',r'Demand and vehicle accounting at 600 s. Counts are means over 20 runs. Realized demand equals completed plus unfinished plus removed plus pending vehicles in every individual run (residual zero). Effective network/route hashes, vehicle identities, types and speed factors match across controllers within each grid. Intended departure times match within 0.021 s of XML rounding. This is realized demand, not a continuous-rate estimate of generated flows.', 'demand-accounting-audit','llrrrrrrr',r'Grid & Controller & Runs & Demand & Completed & Unfinished & Removed & Pending & Max residual',rows))
    rows=[]
    for g in energy['groups']:
        p=g['pooled'];rows.append(' & '.join([g['grid'],LABEL[g['controller']],f"{p['mean']:.4f}",f"{p['median']:.4f}",f"{p['sd']:.4f}",f"[{p['q25']:.4f}, {p['q75']:.4f}]",f"{100*p['recovery']:.2f}\\%",'12,000']))
    fragments.append(table('table_optimizer_energy.tex',r'Energy gaps along the respective closed-loop trajectories of each controller. Each controller/grid contributes 20 runs of 600 decisions. Pooled decision distributions are descriptive, not independent replications for inference. Gap is selected energy minus exact minimum energy. Recovery uses a numerical tolerance of $10^{-8}$. Different visited Hamiltonians mean these summaries do not demonstrate distribution matching.','optimizer-energy-summary','llrrrrrr',r'Grid & Controller & Mean gap & Median & SD & $[Q_{25},Q_{75}]$ & Recovery & Decisions',rows))
    rows=[]
    for g in energy['groups']:
        def ran(key):
            v=g[key];return '--' if v is None else (f'{v[0]:,}' if v[0]==v[1] else f'{v[0]:,}--{v[1]:,}')
        rows.append(' & '.join([g['grid'],LABEL[g['controller']],ran('energy_evaluations_range'),ran('circuit_count_range'),ran('total_shots_range'),('--' if g['total_shots_mean'] is None else f"{g['total_shots_mean']:,.1f}")]))
    fragments.append(table('table_optimizer_budgets.tex',r'Observed work counters per decision. SA counts each restart initialization and proposed state as an energy evaluation. QAOA uses 512 shots per circuit; total shots include every circuit evaluated during parameter search, not just the selected circuit. The 3x3 controller retains its within-run parameter calibration. Counts exclude exhaustive diagnostic enumeration. Circuit shots and classical evaluations are different costs; this table does not establish matched budgets, equal runtime or a quantum speedup.','optimizer-budget-accounting','llrrrr',r'Grid & Controller & SA evaluations & QAOA circuits & Total shots & Mean shots',rows))
    rows=[]
    for r in energy['matching']:
        checks=r['checks'];rows.append(' & '.join([r['grid'],r['stage'],f"{100*r['stochastic']['recovery_rate']:.2f}\\%",f"{100*r['qaoa']['recovery_rate']:.2f}\\%",f"{r['stochastic']['mean_gap']:.4f}",f"{r['qaoa']['mean_gap']:.4f}",'/'.join('Pass' if checks[k] else 'Fail' for k in ['recovery','mean_gap','gap_distribution','mistake_sizes']), 'Yes' if r['passes'] else 'No']))
    fragments.append(table('table_matching_diagnostics.tex',r'Saved common-Hamiltonian calibration diagnostics for the tuning-selected stochastic settings. Tuning used QAOA seeds 201/202; diagnostic validation used seed 203, which had previously been inspected. Classical seeds were 101--103. The four checks are recovery, mean gap, full gap distribution and nonzero-gap tails, in that order. Engineering tolerances are not an equivalence test. Neither grid passed all validation checks; no alternative candidate was substituted after validation.','common-state-matching','llrrrrll',r'Grid & Stage & SA recovery & QAOA recovery & SA gap & QAOA gap & Four checks & All pass',rows))
    keys=[('completed_mean_travel_seconds','Travel time (s)'),('completed_mean_waiting_seconds','Waiting time (s)'),('completed_trips','Completed trips'),('unfinished_trips','Unfinished trips'),('network_time_loss_seconds','Time loss (vehicle-s)'),('network_waiting_seconds','Network waiting (vehicle-s)'),('pending_insertion_at_cutoff','Pending insertion'),('all_insertion_delay_seconds','Pre-entry delay (vehicle-s)'),('time_loss_plus_insertion_delay_seconds','Time loss + pre-entry delay (vehicle-s)')]
    for grid in ['2x2','3x3']:
        for first,second,key in [('QAOA','Classical global SA','qaoa_global'),('Classical stochastic','Classical global SA','stochastic_global'),('QAOA','Classical stochastic','qaoa_stochastic')]:
            rows=[]
            for metric,label in keys:
                r=next(r for r in effects['results'] if r['grid']==grid and r['first']==first and r['comparator']==second and r['metric']==metric)
                rows.append(' & '.join([label,f"{r['difference']:+.2f}",f"[{r['ci95_low']:+.2f}, {r['ci95_high']:+.2f}]",f"{r['relative_percent']:+.2f}\\%",f"[{r['relative_ci95_low']:+.2f}, {r['relative_ci95_high']:+.2f}]",pformat(r['p_welch']),pformat(r['p_holm'])]))
            caption=(f'{grid}: {LABEL[first]} minus {LABEL[second]}. '+r'Absolute and relative mean differences have pointwise 95\% independent run-level percentile-bootstrap intervals (50,000 resamples). Relative intervals bootstrap the ratio of means. Welch tests are approximate; Holm adjustment spans all '+str(effects['holm_family_size'])+r' nonconstant comparisons in the exploratory family, including outcomes not shown here. No outcome was prespecified as primary. Positive differences favor the first controller only for completed trips; fewer unfinished vehicles must be interpreted jointly with entry and completion counts. Pointwise intervals are not multiplicity-adjusted. Demand is fixed; $n=20$ per group.')
            fragments.append(table(f'table_adjusted_effects_{grid}_{key}.tex',caption,f'adjusted-effects-{grid}-{key}','lrrrrrr',r'Metric & Difference & 95\% CI & Relative & Relative 95\% CI (\%) & $p$ & Holm $p$',rows))
    prefix='graphs/reviewer_population_accounting/'
    (OUT/'additional_tables.tex').write_text('\n'.join(r'\input{'+prefix+f+'}' for f in fragments)+'\n')
    (OUT/'preview_additional.tex').write_text(r'\documentclass{article}'+'\n'+r'\usepackage[margin=1.5cm]{geometry}'+'\n'+r'\usepackage{booktabs,graphicx,textcomp}'+'\n'+r'\begin{document}'+'\n'+'\n'.join((OUT/f).read_text() for f in fragments)+'\n'+r'\end{document}')
    print('Wrote demand, energy, budget, matching and six adjusted-effects LaTeX tables.')

if __name__=='__main__':main()
