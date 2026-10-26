"""Rebuild the entire reviewer supplement from existing saved runs; no simulations."""
from pathlib import Path
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=[
 'data_analysis/build_population_accounting_comparison.py',
 'data_analysis/extend_population_accounting.py',
 'data_analysis/analyze_population_accounting_effects.py',
 'data_analysis/build_optimizer_diagnostics.py',
 'data_analysis/make_population_accounting_artifacts.py',
 'data_analysis/make_additional_reviewer_tables.py',
 'graphs/reviewer_population_accounting/plot_effects.py',
 'graphs/reviewer_population_accounting/plot_energy.py',
 'graphs/reviewer_population_accounting/plot_total_delay.py',
 'data_analysis/package_reviewer_supplement.py',
]
if __name__=='__main__':
 for script in SCRIPTS:
  print('Building '+script,flush=True)
  subprocess.run([sys.executable,str(ROOT/script)],cwd=ROOT,check=True)
