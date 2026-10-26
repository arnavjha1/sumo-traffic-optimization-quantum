"""Plot controller differences with uncertainty; reads existing run-level analysis only."""
import json
import sys
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
from plot_common import ROOT, OUTPUT

METRICS=[('completed_mean_travel_seconds','Travel time'),('completed_mean_waiting_seconds','Waiting time'),
         ('completed_trips','Completed trips'),('unfinished_trips','Unfinished trips'),
         ('network_time_loss_seconds','In-network time loss'),('network_waiting_seconds','In-network waiting'),
         ('pending_insertion_at_cutoff','Pending insertion'),('all_insertion_delay_seconds','Pre-entry delay'),
         ('time_loss_plus_insertion_delay_seconds','Time loss + pre-entry delay')]
PAIRS=[('QAOA','Classical global SA','qaoa_vs_global'),
       ('Classical stochastic','Classical global SA','stochastic_vs_global'),
       ('QAOA','Classical stochastic','qaoa_vs_stochastic')]

def main(show=False):
    data=json.loads((ROOT/'data_analysis/population_accounting_comparison/effect_estimates.json').read_text())
    for first,second,name in PAIRS:
        fig,axes=plt.subplots(1,2,figsize=(12,6.3),layout='constrained')
        for ax,grid in zip(axes,('2x2','3x3')):
            for y,(metric,label) in enumerate(METRICS):
                r=next(r for r in data['results'] if r['grid']==grid and r['first']==first and r['comparator']==second and r['metric']==metric)
                mean,low,high=r['relative_percent'],r['relative_ci95_low'],r['relative_ci95_high']
                color='tab:red' if first=='QAOA' else 'tab:blue'
                ax.errorbar(mean,y,xerr=np.array([[mean-low],[high-mean]]),fmt='o',color=color,capsize=4,elinewidth=2)
            ax.set_yticks(range(len(METRICS)),[label for _,label in METRICS])
            ax.invert_yaxis();ax.axvline(0,color='.4',linestyle='--',linewidth=1)
            ax.set_title(grid.replace('x',' × ')+' network')
            ax.set_xlabel('Mean difference relative to comparator (%)')
            ax.grid(axis='x',alpha=.25);ax.margins(x=.18,y=.08)
        fig.suptitle(f'{first} minus {second}',fontsize=14)
        fig.supxlabel('Pointwise 95% bootstrap CIs of relative differences; 20 optimizer runs per group; fixed demand.\nPositive means more, negative means less. Intervals are not adjusted for multiple comparisons.',fontsize=9)
        for suffix in ('pdf','png'):fig.savefig(OUTPUT/f'figure_effects_{name}.{suffix}',dpi=300,bbox_inches='tight')
        if show:plt.show()
        plt.close(fig)

if __name__=='__main__':main('--show' in sys.argv)
