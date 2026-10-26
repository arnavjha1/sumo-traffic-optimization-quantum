"""Export LaTeX table fragments and reproduce the supplementary Matplotlib figures.

Reads completed evaluation data; never runs a controller or changes legacy tables.
"""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'graphs/reviewer_population_accounting'
CONTROLLERS = ['Classical global SA','Classical stochastic','QAOA']
METRICS = [
 ('completed_mean_travel_seconds','Completed-trip travel time (s)'),
 ('completed_mean_waiting_seconds','Completed-trip waiting time (s)'),
 ('completed_trips','Completed trips'),
 ('unfinished_trips','Unfinished trips at cutoff'),
 ('removed_trips','Removed trips'),
 ('completion_fraction_of_departed','Completion fraction of entered vehicles'),
 ('network_time_loss_seconds','Network-wide time loss (vehicle-s)'),
 ('network_waiting_seconds','Network-wide stopped waiting (vehicle-s)'),
 ('pending_insertion_at_cutoff','Pending insertion at cutoff'),
 ('pending_insertion_vehicle_seconds_sampled','Sampled insertion backlog integral (vehicle-s)'),
 ('all_insertion_delay_seconds','Total pre-entry delay (vehicle-s)'),
 ('time_loss_plus_insertion_delay_seconds','Time loss plus pre-entry delay (vehicle-s)'),
 ('realized_demand_trips','Realized demand by cutoff (vehicles)'),
]
EFFECT_LABELS = dict(METRICS)
SELECTED = ['completed_mean_travel_seconds','completed_mean_waiting_seconds','completed_trips',
            'unfinished_trips','network_time_loss_seconds','network_waiting_seconds']
SHORT = {'Classical global SA':'Global SA','Classical stochastic':'Stochastic','QAOA':'QAOA'}

def write(name, text):
    (OUTPUT/name).write_text(text+'\n',encoding='utf-8')

def main():
    data=json.loads((ROOT/'data_analysis/population_accounting_comparison/extended_comparison.json').read_text())
    effects=json.loads((ROOT/'data_analysis/population_accounting_comparison/effect_estimates.json').read_text())
    if not all(r['complete'] and r['n']==20 for r in data['summary']):
        raise ValueError('Tables require 20 successful runs per controller and grid')
    stats={(r['grid'],r['controller'],r['metric']):r for r in data['summary']}
    fragments=[]
    for grid in ('2x2','3x3'):
        grid_tex=grid.replace('x',r' $\times$ ')
        lines=[r'\begin{table}[tbp]',r'\centering',r'\small',
               r'\setlength{\tabcolsep}{4pt}',
               r'\caption{Supplementary population and delay accounting for the '+grid_tex+
               r' network at $\alpha=0.7$ and a 600-s cutoff. Values are means $\pm$ sample SD across 20 optimizer seeds per controller under fixed demand. Travel and waiting means describe completed trips. Network-wide time loss and stopped waiting include all entered vehicles, including unfinished trips, accumulated through the cutoff. Pending insertion and its sampled backlog integral are reported separately. Pre-entry delay sums departDelay over entered and undeparted vehicles; the supplementary composite adds it to in-network time loss over disjoint phases. The sampled backlog integral is not added again. The global SA controller uses simulated annealing.}',
               r'\label{tab:population-accounting-'+grid+'}',
               r'\resizebox{\linewidth}{!}{%',r'\begin{tabular}{lrrr}',r'\toprule',
               r'Measure & Global SA & Stochastic & QAOA \\',r'\midrule']
        for metric,label in METRICS:
            decimals=3 if metric=='completion_fraction_of_departed' else (2 if 'mean_' in metric else 1)
            cells=[]
            for controller in CONTROLLERS:
                r=stats[(grid,controller,metric)]
                cells.append(f"${r['mean']:,.{decimals}f} \\pm {r['sd']:,.{decimals}f}$")
            lines.append(label+' & '+' & '.join(cells)+r' \\')
        lines += [r'\bottomrule',r'\end{tabular}}',r'\end{table}']
        name=f'table_population_accounting_{grid}.tex'; write(name,'\n'.join(lines)); fragments.append(name)
        lines=[r'\begin{table}[tbp]',r'\centering',r'\scriptsize',
               r'\caption{Run-level controller differences for the '+grid_tex+
               r' network. Differences are first controller minus comparator in native metric units; negative differences favor the first controller except for completed trips. Intervals are pointwise exploratory 95\% independent two-sample percentile-bootstrap confidence intervals from 50,000 resamples of whole runs, without multiplicity adjustment. Demand is fixed; intervals quantify optimizer randomness.}',
               r'\label{tab:population-effects-'+grid+'}',r'\resizebox{\linewidth}{!}{%',
               r'\begin{tabular}{llrr}',r'\toprule',r'Comparison & Measure & Difference & 95\% CI \\',r'\midrule']
        previous=None
        for r in effects['results']:
            if r['grid']!=grid or r['metric'] not in SELECTED: continue
            pair=(r['first'],r['comparator'])
            if previous is not None and pair!=previous: lines.append(r'\addlinespace')
            comparison=SHORT[r['first']]+' minus '+SHORT[r['comparator']]
            lines.append(comparison+' & '+EFFECT_LABELS[r['metric']]+f" & ${r['difference']:+.2f}$ & $[{r['ci95_low']:+.2f}, {r['ci95_high']:+.2f}]$"+r' \\')
            previous=pair
        lines += [r'\bottomrule',r'\end{tabular}}',r'\end{table}']
        name=f'table_population_effects_{grid}.tex'; write(name,'\n'.join(lines)); fragments.append(name)
    prefix='graphs/reviewer_population_accounting/'
    write('supplementary_tables.tex','% Requires booktabs and graphicx. Paths assume this folder is copied under graphs/.\n'+
          '\n'.join(r'\input{'+prefix+name+'}' for name in fragments))
    captions={
      'population':r'Completed and unfinished vehicle populations at the 600-s cutoff.',
      'network_delay':r'Accumulated network-wide time loss and stopped waiting, including completed, unfinished, and any removed vehicles through the cutoff. Vehicles awaiting insertion are excluded and reported separately.',
      'trip_times':r'Completed-trip travel and waiting times. These averages are interpreted alongside population and network-wide delay accounting.',
      'insertion_backlog':r'Vehicles pending insertion at the cutoff and accumulated insertion backlog, measured as a discrete right-endpoint integral. These quantities are separate from in-network time loss.'}
    lines=[]
    for name,caption in captions.items():
        lines += [r'\begin{figure}[tbp]',r'\centering',
                  r'\includegraphics[width=\linewidth]{'+prefix+'figure_'+name+'.pdf}',
                  r'\caption{'+caption+r' All conditions use $\alpha=0.7$ and fixed demand. Small dots show individual optimizer runs; large markers show means and error bars show pointwise 95\% percentile-bootstrap confidence intervals across 20 optimizer runs. These are not confidence intervals for controller differences.}',
                  r'\label{fig:supplementary-'+name.replace('_','-')+'}',r'\end{figure}','']
    write('supplementary_figures.tex','\n'.join(lines))
    write('preview.tex',r'''\documentclass{article}
\usepackage[margin=1.5cm]{geometry}
\usepackage{booktabs,graphicx}
\begin{document}
'''+ '\n'.join((OUTPUT/name).read_text() for name in fragments)+r'\end{document}')
    for script in ('plot_population.py','plot_network_delay.py','plot_trip_times.py','plot_insertion_backlog.py'):
        subprocess.run([sys.executable,str(OUTPUT/script)],check=True,cwd=ROOT)
    print('Created four LaTeX tables, four PDF/PNG figures, and LaTeX inclusion files in '+str(OUTPUT))

if __name__=='__main__': main()
