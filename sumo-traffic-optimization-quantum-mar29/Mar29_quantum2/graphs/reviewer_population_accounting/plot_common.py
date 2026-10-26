"""Shared plotting settings and run data for the population-accounting supplement."""
import json
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).resolve().parent
DATA = ROOT / 'data_analysis/population_accounting_comparison/extended_comparison.json'
CONTROLLERS = ['Classical global SA', 'Classical stochastic', 'QAOA']
COLORS = ['tab:green', 'tab:blue', 'tab:red']
LABELS = ['Global SA', 'Stochastic', 'QAOA']

def make_figure(metrics, filename, title, show=False):
    data = json.loads(DATA.read_text(encoding='utf-8'))
    if not all(r['complete'] and r['n'] == 20 for r in data['summary']):
        raise ValueError('Expected 20 complete runs for every grid/controller')
    groups = {(g['grid'],g['controller']):g['runs'] for g in data['groups']}
    plt.rcParams.update({'font.size':11, 'axes.titlesize':12, 'axes.labelsize':11,
                         'pdf.fonttype':42, 'ps.fonttype':42})
    rng = np.random.default_rng(20261025)
    fig, axes = plt.subplots(2,2,figsize=(10.8,7.2),layout='constrained')
    for row, grid in enumerate(('2x2','3x3')):
        for col, (metric,label) in enumerate(metrics):
            ax = axes[row,col]
            for x,(controller,color) in enumerate(zip(CONTROLLERS,COLORS)):
                values = np.array([r['metrics'][metric] for r in groups[(grid,controller)]],dtype=float)
                # Fixed offsets show every run without adding random plotting jitter.
                offsets = np.linspace(-.13,.13,len(values))
                ax.scatter(x+offsets,values,s=22,color=color,alpha=.28,edgecolors='none',zorder=2)
                ci = np.quantile(values[rng.integers(len(values),size=(50000,len(values)))].mean(axis=1), [.025,.975])
                ax.errorbar(x,values.mean(),yerr=np.array([[values.mean()-ci[0]],[ci[1]-values.mean()]]),fmt='o',color=color,
                            markersize=8,capsize=6,elinewidth=2.5,zorder=3)
            ax.set_xticks(range(3),LABELS)
            ax.set_xlim(-.5,2.5)
            ax.set_ylabel(label)
            ax.set_title(f'{grid.replace("x", " × ")} network')
            ax.grid(axis='y',alpha=.3)
            ax.ticklabel_format(axis='y',style='plain',useOffset=False)
            ax.margins(y=.14)
    fig.suptitle(title + r' ($\alpha=0.7$, horizon 600 s)',fontsize=14)
    fig.supxlabel('Dots: individual runs; large markers: means; error bars: pointwise 95% bootstrap CIs (20 optimizer seeds; fixed demand)',fontsize=10)
    for suffix in ('pdf','png'):
        fig.savefig(OUTPUT/f'{filename}.{suffix}',dpi=300,bbox_inches='tight')
    if show: plt.show()
    plt.close(fig)
