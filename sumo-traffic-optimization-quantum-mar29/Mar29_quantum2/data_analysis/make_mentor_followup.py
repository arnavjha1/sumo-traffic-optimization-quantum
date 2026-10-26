"""Export common-instance replay and outlier-audit tables for the mentor follow-up."""
import json
from pathlib import Path
import numpy as np
from make_additional_reviewer_tables import table
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'graphs/reviewer_population_accounting'
DATA=ROOT/'data_analysis/population_accounting_comparison'

def main():
 common=json.loads((ROOT/'common_hamiltonian_evaluation_results/summary.json').read_text())
 closed=json.loads((DATA/'extended_comparison.json').read_text())
 energy=json.loads((DATA/'optimizer_diagnostics.json').read_text())
 fragments=[];rows=[]
 for g in common['summaries']:
  for method,count in [('classical',36000),('qaoa',12000)]:
   r=g[method]
   rows.append(' & '.join([g['grid'],'Classical replay' if method=='classical' else 'Recorded QAOA',f'{count:,}',f"{r['mean']:.5f}",f"{r['median']:.4f}",f"[{r['q25']:.4f}, {r['q75']:.4f}]",f"{100*r['recovery']:.3f}\\% "]))
 fragments.append(table('table_common_hamiltonian_energy.tex',r'Common-instance energy comparison on fresh QAOA-evaluation recordings. The frozen classical stochastic optimizer is replayed on the same 12,000 Hamiltonians per grid using three fresh replay seeds (701--703) per state. QAOA energies are the recorded selected energies, not new QAOA draws. All exact minima and selected energies were independently checked. Pooled decisions/replays are descriptive; the inference unit is a full source trajectory. No retuning, traffic simulations or computational-budget matching is performed.','common-hamiltonian-energy','llrrrrr',r'Grid & Method & Selected states & Mean gap & Median & $[Q_{25},Q_{75}]$ & Recovery',rows))
 rows=[]
 for g in common['summaries']:
  for key,label in [('mean_gap_difference','Mean energy gap'),('recovery_difference_pp','Recovery (percentage points)')]:
   r=g['paired'][key];lo,hi=r['ci95']
   rows.append(' & '.join([g['grid'],label,f"{r['mean']:+.5f}",f'[{lo:+.5f}, {hi:+.5f}]','20']))
 fragments.append(table('table_common_hamiltonian_paired.tex',r'Classical replay minus recorded QAOA on identical states. Pointwise 95\% paired trajectory-cluster bootstrap intervals use 50,000 resamples of 20 complete QAOA source trajectories per grid. The three classical replays are averaged within each trajectory; they do not create 60 independent traffic replications. This post-hoc analysis characterizes quality on QAOA-visited states, not a symmetric sample from both controllers or an equivalence test.','common-hamiltonian-paired','llrrr',r'Grid & Measure & Mean difference & 95\% CI & Trajectories',rows))
 rows=[]
 for g in common['summaries']:
  d=g['diagnostics'];c=g['engineering_checks']
  rows.append(' & '.join([g['grid'],f"{d['recovery_difference_pp']:+.3f}",f"{100*d['mean_gap_relative_error']:.2f}\\%",f"{100*d['wasserstein_relative']:.2f}\\%",f"{100*d['nonzero_quantile_relative_error']:.2f}\\%",'/'.join('Pass' if c[k] else 'Fail' for k in ['recovery','mean_gap','gap_distribution','mistake_sizes'])]))
 fragments.append(table('table_common_hamiltonian_screen.tex',r'Post-hoc application of the earlier engineering tolerances to common-state evaluation replay: recovery within 3 percentage points, relative mean-gap error at most 20\%, Wasserstein distance divided by QAOA mean gap at most 25\%, and mean distance across 101 nonzero-gap quantiles divided by QAOA mean nonzero gap at most 25\%. These descriptive screens are not statistical equivalence bounds and do not certify matched distributions. Earlier diagnostic calibration validation failed on both grids; the new 3x3 screen does not erase that history.','common-hamiltonian-screen','lrrrrl',r'Grid & Recovery diff. (pp) & Mean error & Relative W1 & Tail distance & Checks: recovery/mean/W1/tail',rows))
 qgroup=next(g for g in energy['groups'] if g['grid']=='3x3' and g['controller']=='QAOA')
 byseed={r['seed']:r for r in qgroup['runs']}
 paramgroups={};audits=[]
 for seed in range(301,321):
  saved=json.loads((ROOT/f'qaoa_evaluation_results/3x3_a7_seed{seed}.json').read_text())
  records=[json.loads(line) for line in Path(saved['snapshot_path']).read_text().splitlines()]
  assert len(records)==600 and saved['status']=='success' and saved['energy']['num_decisions']==600
  assert saved['supplementary']['departure_accounting_ok'] and saved['supplementary']['arrival_accounting_ok']
  settings=records[-1]['qaoa'];key=(settings['gamma'],settings['beta'],settings['p'])
  paramgroups.setdefault(key,[]).append(seed)
  audits.append(dict(seed=seed,final_params=dict(gamma=key[0],beta=key[1],p=key[2]),
                     mean_gap=byseed[seed]['mean'],recovery=byseed[seed]['recovery'],status='success',decisions=600))
 rows=[]
 for (gamma,beta,p),seeds in paramgroups.items():
  rows.append(' & '.join(['312 (retained)' if seeds==[312] else 'Other 19 runs',str(len(seeds)),f'{gamma:.6f}',f'{beta:.6f}',str(p),f"{np.mean([byseed[s]['mean'] for s in seeds]):.4f}",f"{100*np.mean([byseed[s]['recovery'] for s in seeds]):.2f}\\% "]))
 fragments.append(table('table_qaoa_outlier_audit.tex',r'Investigation of the 3x3 QAOA energy-quality outlier. Seed 312 completed all 600 decisions with valid vehicle accounting and independently verified selected/exact energies. It selected different fixed circuit angles during the existing within-run calibration; the other 19 runs share another parameter set. This association does not establish the cause of its energy or traffic outcomes. Seed 312 remains in every primary result.','qaoa-outlier-audit','lrrrrrr',r'Runs & $n$ & Final $\gamma$ & Final $\beta$ & $p$ & Mean run gap & Recovery',rows))
 qtraffic=next(g for g in closed['groups'] if g['grid']=='3x3' and g['controller']=='QAOA')['runs']
 ctraffic=next(g for g in closed['groups'] if g['grid']=='3x3' and g['controller']=='Classical stochastic')['runs']
 keys=[('mean','Run-average energy gap'),('recovery','Optimum recovery (fraction)'),('completed_trips','Completed trips'),('network_time_loss_seconds','In-network time loss (vehicle-s)'),('time_loss_plus_insertion_delay_seconds','Time loss plus pre-entry delay (vehicle-s)')]
 cenergy=next(g for g in energy['groups'] if g['grid']=='3x3' and g['controller']=='Classical stochastic')['runs']
 rows=[];sensitivity=[];rng=np.random.default_rng(20261025)
 for metric,label in keys:
  if metric in ('mean','recovery'):
   values=np.array([byseed[seed][metric] for seed in range(301,321)]);base=np.array([r[metric] for r in cenergy])
  else:
   lookup={r['seed']:r for r in qtraffic};values=np.array([lookup[seed]['metrics'][metric] for seed in range(301,321)]);base=np.array([r['metrics'][metric] for r in ctraffic])
  reduced=np.delete(values,11)
  differences=[]
  for x in (values,reduced):
   boot=x[rng.integers(len(x),size=(50000,len(x)))].mean(axis=1)-base[rng.integers(len(base),size=(50000,len(base)))].mean(axis=1)
   differences.append(dict(mean=float(x.mean()-base.mean()),ci95=np.quantile(boot,[.025,.975]).tolist()))
  full,loo=differences
  rows.append(' & '.join([label,f"{full['mean']:+.4f}",f"[{full['ci95'][0]:+.4f}, {full['ci95'][1]:+.4f}]",f"{loo['mean']:+.4f}",f"[{loo['ci95'][0]:+.4f}, {loo['ci95'][1]:+.4f}]"]))
  sensitivity.append(dict(metric=metric,full=full,without_seed312=loo))
 fragments.append(table('table_qaoa_outlier_sensitivity.tex',r'Post-hoc sensitivity analysis: 3x3 QAOA minus classical stochastic, using either all 20 QAOA runs or the other 19 runs after omitting seed 312. The comparator retains all 20 runs. Pointwise independent-run bootstrap 95\% intervals are descriptive and not multiplicity-adjusted; omission was not prespecified and does not replace any primary result. Energy summaries here are from each controller\textquotesingle s own trajectories, not the common-state replay.','qaoa-outlier-sensitivity','lrrrr',r'Measure & Full difference & Full 95\% CI & Without 312 & Without 312 95\% CI',rows))
 (OUT/'mentor_followup_tables.tex').write_text('\n'.join(r'\input{graphs/reviewer_population_accounting/'+f+'}' for f in fragments)+'\n')
 (DATA/'outlier_audit.json').write_text(json.dumps(dict(runs=audits,sensitivity=sensitivity),indent=2))
 print('Wrote three common-Hamiltonian tables and two outlier-audit/sensitivity tables.')

if __name__=='__main__':main()
