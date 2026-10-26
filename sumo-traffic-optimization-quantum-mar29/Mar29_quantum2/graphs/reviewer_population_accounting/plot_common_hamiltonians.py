"""Visualize frozen optimizer replay on identical QAOA-evaluation Hamiltonians."""
import json
import sys
import numpy as np
import matplotlib.pyplot as plt
from plot_common import ROOT,OUTPUT

def main(show=False):
 data=json.loads((ROOT/'common_hamiltonian_evaluation_results/summary.json').read_text())
 fig,axes=plt.subplots(2,2,figsize=(11,7.5),layout='constrained')
 for row,g in enumerate(data['summaries']):
  for col,(qkey,ckey,label,threshold) in enumerate([
      ('qaoa_gaps','classical_gaps','Energy gap',.01),
      ('normalized_qaoa_gaps','normalized_classical_gaps',r'Energy gap / $|E_{min}|$',.001)]):
   ax=axes[row,col]
   for key,color,label_method in [(ckey,'tab:blue','Classical replay (3 seeds)'),(qkey,'tab:red','Recorded QAOA')]:
    values=np.sort(g[key]);ax.step(values,np.arange(1,len(values)+1)/len(values),where='post',color=color,linewidth=2,label=label_method)
   ax.set_xscale('symlog',linthresh=threshold);ax.set_xlabel(label);ax.set_ylabel('Fraction of decisions')
   ax.set_title(g['grid'].replace('x',' × ')+' common Hamiltonians')
   if g['grid']=='2x2':
    ax.set_ylim(.985,1.0005);ax.text(.02,.04,'Truncated y-axis: 0.985 to 1.0005',transform=ax.transAxes,fontsize=8,bbox=dict(facecolor='white',alpha=.85,edgecolor='none'))
   else:ax.set_ylim(0,1.03)
   ax.grid(alpha=.25);ax.legend(fontsize=9)
 fig.suptitle('Energy gaps on identical recorded Hamiltonians',fontsize=14)
 fig.supxlabel('Frozen classical settings; QAOA evaluation snapshots only; no retuning or SUMO reruns.\n12,000 states per grid; 3 classical replays per state. Pooled ECDFs are descriptive, not equivalence tests.',fontsize=9)
 for suffix in ('pdf','png'):fig.savefig(OUTPUT/f'figure_common_hamiltonian_gaps.{suffix}',dpi=300,bbox_inches='tight')
 if show:plt.show()
 plt.close(fig)
 fig,axes=plt.subplots(2,2,figsize=(11,7.4),layout='constrained')
 for row,g in enumerate(data['summaries']):
  for col,(metric,label) in enumerate([('mean_gap_difference','Mean energy-gap difference'),('recovery_difference_pp','Recovery difference (percentage points)')]):
   ax=axes[row,col]
   values=np.array([r[metric] for r in g['trajectories']]);seeds=[r['qaoa_seed'] for r in g['trajectories']]
   summary=g['paired'][metric];low,high=summary['ci95'];mean=summary['mean']
   ax.axhspan(low,high,color='tab:blue',alpha=.13,label='95% CI of mean difference')
   ax.axhline(mean,color='tab:blue',linewidth=2,label='Mean difference')
   ax.scatter(seeds,values,color='tab:blue',alpha=.7,s=30,zorder=3,label='Trajectory difference')
   ax.axhline(0,color='.4',linestyle='--',linewidth=1)
   ax.set_title(g['grid'].replace('x',' × ')+' source trajectories')
   ax.set_xticks([301,306,311,316,320]);ax.set_xlabel('QAOA source-trajectory seed')
   ax.set_ylabel(label);ax.grid(axis='y',alpha=.25);ax.margins(y=.12)
   if row==0 and col==0:ax.legend(fontsize=8,loc='best')
 fig.suptitle('Common-state classical replay minus recorded QAOA',fontsize=14)
 fig.supxlabel('20 paired trajectory summaries per grid; each averages 3 classical replays per state.\nBands: pointwise 95% paired trajectory-cluster bootstrap CIs of the mean, not prediction intervals.',fontsize=9)
 for suffix in ('pdf','png'):fig.savefig(OUTPUT/f'figure_common_hamiltonian_differences.{suffix}',dpi=300,bbox_inches='tight')
 if show:plt.show()
 plt.close(fig)

if __name__=='__main__':main('--show' in sys.argv)
