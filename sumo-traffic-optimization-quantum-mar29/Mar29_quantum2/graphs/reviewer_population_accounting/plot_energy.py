"""Descriptive energy-gap ECDFs and independent run-level quality summaries."""
import json
import sys
import numpy as np
import matplotlib.pyplot as plt
from plot_common import ROOT, OUTPUT

def main(show=False):
    data=json.loads((ROOT/'data_analysis/population_accounting_comparison/optimizer_diagnostics.json').read_text())
    fig,axes=plt.subplots(2,2,figsize=(11,7.5),layout='constrained')
    for row,grid in enumerate(('2x2','3x3')):
        for col,(key,label,threshold) in enumerate([('gaps','Energy gap',.01),('relative_gaps',r'Energy gap / $|E_{min}|$',.001)]):
            ax=axes[row,col]
            for controller,color in [('Classical stochastic','tab:blue'),('QAOA','tab:red')]:
                group=next(g for g in data['groups'] if g['grid']==grid and g['controller']==controller)
                values=np.sort(group[key]); ax.step(values,np.arange(1,len(values)+1)/len(values),where='post',color=color,linewidth=2,label=controller)
            ax.set_xscale('symlog',linthresh=threshold)
            ax.set_ylim(0,1.03);ax.set_ylabel('Fraction of decisions');ax.set_xlabel(label)
            ax.set_title(grid.replace('x',' × ')+' network'+(' (upper-tail zoom)' if grid=='2x2' else ''))
            if grid=='2x2':
                ax.set_ylim(.985,1.0005)
                ax.text(.02,.04,'Truncated y-axis: 0.985 to 1.0005',transform=ax.transAxes,fontsize=8,
                        bbox=dict(facecolor='white',alpha=.85,edgecolor='none'))
            ax.grid(alpha=.25);ax.legend(fontsize=9)
    fig.suptitle('Energy quality on each controller’s own closed-loop trajectories',fontsize=13)
    fig.supxlabel('12,000 decisions per controller/grid; pooled ECDFs are descriptive, not independent replications.\nDifferent visited states: these curves do not establish matched energy-gap distributions.',fontsize=9)
    for suffix in ('pdf','png'):fig.savefig(OUTPUT/f'figure_energy_gaps.{suffix}',dpi=300,bbox_inches='tight')
    if show:plt.show()
    plt.close(fig)
    rng=np.random.default_rng(20261025)
    fig,axes=plt.subplots(2,2,figsize=(10.8,7.2),layout='constrained')
    for row,grid in enumerate(('2x2','3x3')):
        for col,(metric,label) in enumerate([('mean','Run-average energy gap'),('recovery','Exact-optimum recovery (%)')]):
            ax=axes[row,col]
            for x,(controller,color) in enumerate([('Classical stochastic','tab:blue'),('QAOA','tab:red')]):
                g=next(g for g in data['groups'] if g['grid']==grid and g['controller']==controller)
                values=np.array([r[metric] for r in g['runs']])*(100 if metric=='recovery' else 1)
                ci=np.quantile(values[rng.integers(len(values),size=(50000,len(values)))].mean(axis=1),[.025,.975])
                ax.scatter(x+np.linspace(-.13,.13,len(values)),values,color=color,alpha=.3,s=25)
                ax.errorbar(x,values.mean(),yerr=[[values.mean()-ci[0]],[ci[1]-values.mean()]],fmt='o',color=color,capsize=5,elinewidth=2.5,markersize=8)
                if grid=='3x3' and controller=='QAOA':
                    j=next(i for i,r in enumerate(g['runs']) if r['seed']==312)
                    text_y=values[j]+(5 if metric=='mean' else -6)
                    ax.annotate('Seed 312 (retained)',xy=(1+np.linspace(-.13,.13,len(values))[j],values[j]),
                                xytext=(.25,text_y),fontsize=8,arrowprops=dict(arrowstyle='->',color='.35'))
            ax.set_xticks([0,1],['Stochastic','QAOA']);ax.set_xlim(-.5,1.5)
            ax.set_ylabel(label);ax.set_title(grid.replace('x',' × ')+' network');ax.grid(axis='y',alpha=.25);ax.margins(y=.15)
    fig.suptitle('Run-level energy quality under fixed demand',fontsize=14)
    fig.supxlabel('Dots: 20 optimizer runs; mean markers with pointwise 95% bootstrap CIs.\nEach controller visits its own traffic states; no matching or equivalence claim.',fontsize=9)
    for suffix in ('pdf','png'):fig.savefig(OUTPUT/f'figure_energy_run_summary.{suffix}',dpi=300,bbox_inches='tight')
    if show:plt.show()
    plt.close(fig)

if __name__=='__main__':main('--show' in sys.argv)
