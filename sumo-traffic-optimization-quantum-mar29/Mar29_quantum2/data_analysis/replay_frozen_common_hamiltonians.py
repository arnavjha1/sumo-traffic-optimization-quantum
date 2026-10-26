"""Replay frozen stochastic settings on fresh QAOA-evaluation Hamiltonians.
No SUMO, QAOA reruns, retuning, or controller edits. Paired inference clusters by trajectory.
"""
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import numpy as np
from scipy.stats import wasserstein_distance
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from run_stochastic_calibration import save_json
OUT=ROOT/'common_hamiltonian_evaluation_results'
REPLAY_SEEDS=[701,702,703]

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def describe(x):
 x=np.asarray(x,dtype=float)
 return dict(mean=float(x.mean()),median=float(np.median(x)),sd=float(x.std(ddof=1)),
             recovery=float(np.mean(x<=1e-8)),q25=float(np.quantile(x,.25)),q75=float(np.quantile(x,.75)))

def main():
 frozen_path=ROOT/'stochastic_evaluation_settings.json'
 frozen=json.loads(frozen_path.read_text())
 sources={str(frozen_path.relative_to(ROOT)):digest(frozen_path),str(Path(__file__).relative_to(ROOT)):digest(Path(__file__))}
 for grid in ('2x2','3x3'):
  optimizer=ROOT/f'grid_{grid}/2_classical_global_stochastic/annealer_stochastic.py'
  sources[str(optimizer.relative_to(ROOT))]=digest(optimizer)
  for seed in range(301,321):
   for suffix in ('.json','.snapshots.jsonl'):
    p=ROOT/f'qaoa_evaluation_results/{grid}_a7_seed{seed}{suffix}'
    sources[str(p.relative_to(ROOT))]=digest(p)
 protocol=dict(role='post-hoc common-instance evaluation diagnostic; not retuning or equivalence certification',
               settings=frozen['grids'],replay_seeds=REPLAY_SEEDS,qaoa_seeds=list(range(301,321)),
               snapshots='QAOA evaluation trajectories only; reverse replay unavailable because stochastic recordings omit Hamiltonian coefficients',
               rng='independent SeedSequence([replay_seed, grid_width, qaoa_seed, decision]) per instance',
               bootstrap='50000 paired trajectory-cluster resamples; 20 trajectories per grid; average three classical replays within each trajectory',
               sources=sources)
 OUT.mkdir(exist_ok=True)
 manifest=OUT/'manifest.json'
 if manifest.exists() and json.loads(manifest.read_text())!=protocol:raise ValueError('Changed replay protocol: use a separate output folder')
 save_json(manifest,protocol)
 summaries=[]
 for grid,width in [('2x2',2),('3x3',3)]:
  n=width*width;states=np.asarray(list(itertools.product([-1,1],repeat=n)))
  module_path=ROOT/f'grid_{grid}/2_classical_global_stochastic/annealer_stochastic.py'
  spec=importlib.util.spec_from_file_location('frozen_optimizer',module_path)
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  settings=frozen['grids'][grid]
  pooled_q=[];pooled_c=[];norm_q=[];norm_c=[];trajectories=[]
  for seed in range(301,321):
   destination=OUT/f'{grid}_seed{seed}.json'
   if destination.exists():
    result=json.loads(destination.read_text())
    if result.get('status')!='success' or len(result['decisions'])!=600:raise ValueError('Invalid cached replay')
   else:
    saved=json.loads((ROOT/f'qaoa_evaluation_results/{grid}_a7_seed{seed}.json').read_text())
    assert saved['status']=='success'
    rows=[json.loads(line) for line in (ROOT/f'qaoa_evaluation_results/{grid}_a7_seed{seed}.snapshots.jsonl').read_text().splitlines()]
    assert len(rows)==600
    decisions=[]
    for index,row in enumerate(rows,1):
     assert row['decision']==index and row['sampler_seed']==seed and row['grid']==grid
     assert row['switching_penalty']==10 and row['coupling_strength']==2
     fields=np.asarray(row['biases'])+10*(2*np.asarray(row['previous_state'])-1)
     edges=[(i,j) for i,adj in enumerate(row['neighbors']) for j in adj if i<j]
     energies=-states@fields-sum(2*states[:,i]*states[:,j] for i,j in edges)
     exact=float(energies.min())
     def energy(bitstring):
      spins=2*np.array([int(b) for b in bitstring])-1
      return float(-spins@fields-sum(2*spins[i]*spins[j] for i,j in edges))
     assert abs(exact-row['exact_min_energy'])<1e-6
     assert abs(energy(row['selected_state'])-row['selected_energy'])<1e-6
     cgaps=[];cstates=[]
     for replay_seed in REPLAY_SEEDS:
      state,metadata=module.stochastic_decision(row['biases'],row['previous_state'],row['neighbors'],2,
          rng=np.random.default_rng(np.random.SeedSequence([replay_seed,width,seed,index])),
          return_metadata=True,**settings)
      assert metadata['energy_evaluations']==settings['evaluation_budget']
      assert abs(energy(state)-metadata['selected_energy'])<1e-6
      gap=metadata['selected_energy']-exact
      assert gap>=-1e-8
      cgaps.append(0. if gap<=1e-8 else gap);cstates.append(state)
     qgap=row['selected_energy']-exact
     assert qgap>=-1e-8
     decisions.append(dict(decision=index,exact_min_energy=exact,qaoa_gap=0. if qgap<=1e-8 else qgap,
                           classical_gaps=cgaps,classical_states=cstates,qaoa_state=row['selected_state']))
    result=dict(status='success',grid=grid,qaoa_seed=seed,decisions=decisions)
    save_json(destination,result)
   q=np.array([r['qaoa_gap'] for r in result['decisions']]);c=np.array([r['classical_gaps'] for r in result['decisions']])
   scale=np.abs([r['exact_min_energy'] for r in result['decisions']]);assert np.all(scale>1e-9)
   pooled_q.extend(q.tolist());pooled_c.extend(c.ravel().tolist())
   norm_q.extend((q/scale).tolist());norm_c.extend((c/scale[:,None]).ravel().tolist())
   trajectories.append(dict(qaoa_seed=seed,qaoa=describe(q),classical=describe(c.ravel()),
                            mean_gap_difference=float(c.mean()-q.mean()),
                            recovery_difference_pp=float(100*(np.mean(c<=1e-8)-np.mean(q<=1e-8)))))
   print(f'{grid} trajectory {seed}: complete',flush=True)
  q=np.array(pooled_q);c=np.array(pooled_c)
  qnon=q[q>1e-8];cnon=c[c>1e-8]
  diagnostics=dict(recovery_difference_pp=100*(np.mean(c<=1e-8)-np.mean(q<=1e-8)),
      mean_gap_relative_error=abs(c.mean()-q.mean())/q.mean(),
      wasserstein_raw=float(wasserstein_distance(q,c)),wasserstein_relative=float(wasserstein_distance(q,c)/q.mean()),
      nonzero_quantile_relative_error=float(np.mean(np.abs(np.quantile(qnon,np.linspace(0,1,101))-np.quantile(cnon,np.linspace(0,1,101))))/qnon.mean()))
  # Retain the earlier engineering tolerances, without claiming an equivalence test.
  checks=dict(recovery=abs(diagnostics['recovery_difference_pp'])<=3,
              mean_gap=diagnostics['mean_gap_relative_error']<=.20,
              gap_distribution=diagnostics['wasserstein_relative']<=.25,
              mistake_sizes=diagnostics['nonzero_quantile_relative_error']<=.25)
  checks={k:bool(v) for k,v in checks.items()}
  paired={};rng=np.random.default_rng([20261025,width])
  for metric in ('mean_gap_difference','recovery_difference_pp'):
   values=np.array([r[metric] for r in trajectories]);ci=np.quantile(values[rng.integers(20,size=(50000,20))].mean(axis=1),[.025,.975])
   paired[metric]=dict(mean=float(values.mean()),ci95=ci.tolist())
  summaries.append(dict(grid=grid,trajectories=trajectories,qaoa=describe(q),classical=describe(c),
                        qaoa_gaps=q.tolist(),classical_gaps=c.tolist(),normalized_qaoa_gaps=norm_q,
                        normalized_classical_gaps=norm_c,diagnostics=diagnostics,engineering_checks=checks,
                        passes_engineering_screen=all(checks.values()),paired=paired))
 save_json(OUT/'summary.json',dict(protocol=protocol,summaries=summaries))
 print('Common-Hamiltonian replay complete. Engineering screens are not equivalence certification.',flush=True)

if __name__=='__main__':main()
