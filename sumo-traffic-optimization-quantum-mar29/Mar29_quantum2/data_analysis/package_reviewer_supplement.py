"""Write LaTeX entrypoints and previews for the revised supplement."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'graphs/reviewer_population_accounting'
PREFIX='graphs/reviewer_population_accounting/'
EXTRA={
 'effects_qaoa_vs_global':r'QAOA minus global SA: relative mean differences with pointwise 95\% independent run-level bootstrap confidence intervals. Positive values mean more and negative values mean less; larger completed counts are favorable, while smaller travel, waiting and delay values are favorable. Intervals are not multiplicity-adjusted; corresponding Welch and Holm-adjusted tests are reported in the statistical tables.',
 'effects_stochastic_vs_global':r'Classical stochastic minus global SA: relative mean differences with pointwise 95\% independent run-level bootstrap confidence intervals. Intervals are not multiplicity-adjusted; see the adjusted-effects tables.',
 'effects_qaoa_vs_stochastic':r'QAOA minus classical stochastic: relative mean differences with pointwise 95\% independent run-level bootstrap confidence intervals. Intervals spanning zero do not establish equivalence. Corresponding multiplicity-adjusted tests are reported separately.',
 'energy_gaps':r'Raw and normalized energy-gap ECDFs along each controller\textquotesingle s own closed-loop trajectories. Normalization divides each gap by the absolute exact minimum energy for that decision (nonzero for all retained decisions). The symmetric-log horizontal scales preserve zero and display positive tails. The 2x2 panels zoom to ECDF values above 0.985 because almost all decisions recover the optimum. Pooled decisions are descriptive and not independent replications. These trajectories visit different Hamiltonians, so visual similarity does not certify distribution matching; saved common-state diagnostics are reported separately.',
 'energy_run_summary':r'Run-level mean energy gaps and exact-optimum recovery on the controllers\textquotesingle{} respective traffic trajectories. Small dots represent individual runs; large markers and bars show means and pointwise 95\% bootstrap confidence intervals across 20 runs.',
 'total_delay':r'Pre-entry delay and the supplementary sum of in-network time loss plus pre-entry delay. Pre-entry delay sums the SUMO departDelay field across entered and undeparted vehicles through the cutoff. The sum joins disjoint pre-entry and in-network phases. It does not add stopped waiting to time loss or add the sampled backlog integral again. Small dots show runs; mean markers have pointwise 95\% bootstrap confidence intervals.',
}

def main():
 lines=[]
 for key,caption in EXTRA.items():
  lines += [r'\begin{figure}[tbp]',r'\centering',r'\includegraphics[width=\linewidth]{'+PREFIX+'figure_'+key+'.pdf}',
            r'\caption{'+caption+r' All traffic results use fixed demand, $\alpha=0.7$ and a 600-s cutoff; uncertainty concerns optimizer randomness, not traffic-demand scenarios.}',
            r'\label{fig:revised-'+key.replace('_','-')+'}',r'\end{figure}','']
 (OUT/'additional_figures.tex').write_text('\n'.join(lines),encoding='utf-8')
 # The revised entry point uses the new adjusted effect tables instead of duplicating legacy effect tables.
 files=['table_population_accounting_2x2.tex','table_population_accounting_3x3.tex',
        'table_demand_audit.tex','table_optimizer_energy.tex','table_optimizer_budgets.tex','table_matching_diagnostics.tex']
 files += [f'table_adjusted_effects_{grid}_{pair}.tex' for grid in ('2x2','3x3') for pair in ('qaoa_global','stochastic_global','qaoa_stochastic')]
 (OUT/'revised_tables.tex').write_text('\n'.join(r'\input{'+PREFIX+f+'}' for f in files)+'\n')
 (OUT/'revised_figures.tex').write_text(r'\input{'+PREFIX+'supplementary_figures.tex}'+'\n'+r'\input{'+PREFIX+'additional_figures.tex}'+'\n')
 # Standalone previews use local relative image paths, so the folder compiles independently.
 tables='\n'.join((OUT/f).read_text(encoding='utf-8') for f in files)
 figures=((OUT/'supplementary_figures.tex').read_text()+'\n'+(OUT/'additional_figures.tex').read_text()).replace(PREFIX,'')
 preamble=r'\documentclass{article}'+'\n'+r'\usepackage[margin=1.5cm]{geometry}'+'\n'+r'\usepackage{booktabs,graphicx,textcomp}'+'\n'+r'\begin{document}'+'\n'
 (OUT/'preview_revised_tables.tex').write_text(preamble+tables+'\n'+r'\end{document}',encoding='utf-8')
 (OUT/'preview_revised_figures.tex').write_text(preamble+figures+'\n'+r'\end{document}',encoding='utf-8')
 print('Revised entrypoints and standalone previews saved.')

if __name__=='__main__':main()
