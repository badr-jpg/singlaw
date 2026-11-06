"""Ablation sample: 100 questions that passed all three annotator checks; 20 per person, 6/6/4/4 by type. Fixed seed."""
import csv,random,collections
from pathlib import Path
csv.field_size_limit(10**8)
AB=Path(__file__).resolve().parent; B=AB.parent; S=B/'work/combined/src'
L={r['question_id']:r for r in csv.DictReader(open(B/'annotation_labels.csv',encoding='utf-8-sig'))}
Q={'provision_lookup':6,'lay_language':6,'case_law':4,'multi_hop':4}
rng=random.Random(20261107); out=[]
for p in ['badr','binyao','darien','huang','sumo']:
    rows=list(csv.DictReader(open(B/'badr.csv' if p=='badr' else S/p/f'{p}.csv',encoding='utf-8-sig',newline='')))
    clean=[r for r in rows if L[r['question_id']]['reference_label']=='correct' and L[r['question_id']]['answerable']=='yes' and L[r['question_id']]['standalone']=='yes']
    for t,n in Q.items():
        c=[r for r in clean if r['question_type']==t]; out+=rng.sample(c,n)
rng.shuffle(out)
with open(AB/'sample.csv','w',encoding='utf-8',newline='') as f:
    w=csv.DictWriter(f,list(out[0].keys())); w.writeheader(); w.writerows(out)
print(len(out),collections.Counter(r['question_id'].split('-')[0] for r in out),collections.Counter(r['question_type'] for r in out),'unique',len({r['question_id'] for r in out}))
