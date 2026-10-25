"""Show all evaluation runs; use --watch for a refreshing progress display."""
import argparse
import json
import os
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parent
BATCHES = [('QAOA','qaoa_evaluation_results'),
           ('Classical global','classical_global_accounting_results'),
           ('Classical stochastic','stochastic_evaluation_results')]

def display():
    print('EVALUATION PROGRESS  '+time.strftime('%H:%M:%S'))
    print('Step counts are simulation seconds/decisions, not elapsed wall time.\n')
    for label,folder in BATCHES:
        directory=ROOT/folder
        manifest=directory/'manifest.json'
        if not manifest.exists():
            print(label+': not started\n'); continue
        configs=json.loads(manifest.read_text())['configurations']
        rows=[]
        for config in configs:
            key=f'{config["grid"]}_a7_seed{config["seed"]}'
            result=directory/(key+'.json')
            log=directory/(key+'.log')
            status='QUEUED'; progress='-'
            if result.exists():
                try:
                    data=json.loads(result.read_text())
                    status='DONE' if data.get('status')=='success' else 'FAILED'
                    progress=str(data.get('energy',{}).get('num_decisions','?'))+'/600'
                except (OSError,ValueError): status='WRITING'
            elif log.exists():
                status='STARTED'
                try:
                    with log.open('rb') as handle:
                        handle.seek(max(0,log.stat().st_size-65536))
                        tail=handle.read().decode('utf-8',errors='replace')
                    steps=re.findall(r'^\s*(\d+(?:\.\d+)?)\s*$',tail,re.MULTILINE)
                    progress=(steps[-1] if steps else '?')+'/600'
                except OSError: pass
            rows.append((config['grid'],config['seed'],status,progress))
        done=sum(row[2]=='DONE' for row in rows)
        failed=sum(row[2]=='FAILED' for row in rows)
        print(f'{label}: {done}/{len(rows)} complete; {failed} failed')
        print('  Grid   Seed   Status     Step')
        for grid,seed,status,progress in rows:
            print(f'  {grid:<6} {seed:<6} {status:<10} {progress}')
        print()
    print('STARTED means a log exists; it does not prove the process is still running.')
    print('The population/delay comparison reuses these outputs; it is not another simulation batch.')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--watch',action='store_true')
    args=p.parse_args()
    try:
        while True:
            if args.watch: os.system('cls' if os.name=='nt' else 'clear')
            display()
            if not args.watch: break
            time.sleep(10)
    except KeyboardInterrupt: pass

if __name__=='__main__': main()
