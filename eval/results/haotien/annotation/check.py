"""python3 -I check.py <annotator> <batch>"""
import json,sys
from pathlib import Path
A=Path(__file__).resolve().parent; a,b=sys.argv[1:3]; want=json.loads((A/'manifest.json').read_text())[a][b]
errs=[];seen=[]
for n,l in enumerate((A/a/'out'/f'{b}.jsonl').read_text().splitlines(),1):
    if not l.strip(): continue
    try: d=json.loads(l)
    except Exception as e: errs.append(f'line {n}: bad JSON {e}'); continue
    seen.append(d.get('id'))
    if d.get('reference_label') not in('correct','partial','incorrect'): errs.append(f"{d.get('id')}: bad reference_label")
    for k in('answerable','standalone'):
        if d.get(k) not in('yes','no'): errs.append(f"{d.get('id')}: bad {k}")
    if (d.get('reference_label')!='correct' or 'no' in(d.get('answerable'),d.get('standalone'))) and not (d.get('note') or '').strip(): errs.append(f"{d.get('id')}: note required")
if sorted(seen)!=sorted(want): errs.append(f'ids wrong: missing {sorted(set(want)-set(seen))[:8]}, extra {sorted(set(seen)-set(want))[:8]}, duplicates {len(seen)-len(set(seen))}')
print(*errs,sep='\n'); print('OK' if not errs else f'{len(errs)} problems',len(seen))
