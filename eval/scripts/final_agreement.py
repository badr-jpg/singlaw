"""Final inter-annotator agreement: first-pass labels, with the 135 items whose evidence was incomplete replaced by the corrected pass."""
import csv,json,glob,collections,itertools,re
from pathlib import Path
csv.field_size_limit(10**8)
A=Path(__file__).resolve().parent; B=A.parents[1]
def load(root):
    L={a:{} for a in 'ABC'}
    for a in L:
        for f in glob.glob(str(root/a/'out/*.jsonl')):
            for l in open(f):
                if l.strip(): d=json.loads(l); L[a][d['id']]=d
    return L
first=load(A); fix=load(A/'fix')
fixed=set(fix['A']); assert fixed==set(fix['B'])==set(fix['C'])
L={a:{**first[a],**fix[a]} for a in 'ABC'}
ids=sorted(L['A'])
def fleiss(rows,cats):
    n=3;N=len(rows);P=[(sum(r.count(c)**2 for c in cats)-n)/(n*(n-1)) for r in rows];pb=sum(P)/N;pc=[sum(r.count(c) for r in rows)/(N*n) for c in cats];pe=sum(x*x for x in pc);return (pb-pe)/(1-pe)
def kap(x,y,cats):
    N=len(x);po=sum(a==b for a,b in zip(x,y))/N;pe=sum(x.count(c)/N*y.count(c)/N for c in cats);return po,(po-pe)/(1-pe)
def stats(ids,L):
    o={}
    for k,cats in [('reference_label',['correct','partial','incorrect']),('answerable',['yes','no']),('standalone',['yes','no'])]:
        rows=[[L[a][i][k] for a in 'ABC'] for i in ids]; pair={}
        for a,b in itertools.combinations('ABC',2):
            po,kp=kap([L[a][i][k] for i in ids],[L[b][i][k] for i in ids],cats); pair[a+b]={'agreement':round(po,4),'cohen_kappa':round(kp,4)}
        o[k]={'pairwise':pair,'mean_pairwise_agreement':round(sum(v['agreement'] for v in pair.values())/3,4),'all_three_agree':round(sum(len(set(r))==1 for r in rows)/len(rows),4),'fleiss_kappa':round(fleiss(rows,cats),4),'counts':{a:dict(collections.Counter(L[a][i][k] for i in ids)) for a in 'ABC'}}
    return o
out={'n':len(ids),'items_reannotated':len(fixed),'final':stats(ids,L),'first_pass':stats(ids,first),'unchanged_items_only':stats([i for i in ids if i not in fixed],L),'reannotated_items_first_pass':stats(sorted(fixed),first),'reannotated_items_corrected':stats(sorted(fixed),L)}
final=[]
for i in ids:
    r={'question_id':i,'person':i.split('-')[0],'reannotated_with_full_section':i in fixed}
    for k in('reference_label','answerable','standalone'):
        v=[L[a][i][k] for a in 'ABC'];c=collections.Counter(v).most_common(1)[0];r[k]=c[0] if c[1]>=2 else 'disputed';r[k+'_votes']='/'.join(v)
    r['notes']=' | '.join(f"{a}: {L[a][i]['note']}" for a in 'ABC' if (L[a][i].get('note') or '').strip())
    final.append(r)
with open(B/'annotation_labels.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,list(final[0].keys()));w.writeheader();w.writerows(final)
C={r['question_id']:r for r in csv.DictReader(open(B/'combined_results.csv',encoding='utf-8-sig'))}
m={k:dict(collections.Counter(r[k] for r in final)) for k in('reference_label','answerable','standalone')}
out['majority']=m
clean=[r['question_id'] for r in final if r['reference_label']=='correct' and r['answerable']=='yes' and r['standalone']=='yes']
out['clean_items']=len(clean)
mean=lambda q:round(sum(float(C[x]['correctness_norm']) for x in q)/len(q),4)
out['singlaw_correctness']={'all_1000':mean(ids),'clean_items':mean(clean),**{f'label_{k}':(mean([r['question_id'] for r in final if r['reference_label']==k]),sum(r['reference_label']==k for r in final)) for k in m['reference_label']}}
out['clean_by_person']=dict(collections.Counter(x.split('-')[0] for x in clean))
out['by_person']={p:{k:dict(collections.Counter(r[k] for r in final if r['person']==p)) for k in('reference_label','answerable','standalone')} for p in ['badr','binyao','darien','huang','sumo']}
out['flagged_incorrect']=[r['question_id'] for r in final if r['reference_label']=='incorrect']
out['partial_unanimous']=sum(r['reference_label_votes']=='partial/partial/partial' for r in final)
(A/'agreement.json').write_text(json.dumps(out,indent=1))
for k in('final','first_pass','unchanged_items_only','reannotated_items_first_pass','reannotated_items_corrected'):
    print(k,{x:(out[k][x]['mean_pairwise_agreement'],out[k][x]['all_three_agree'],out[k][x]['fleiss_kappa']) for x in out[k]})
print(json.dumps({k:out[k] for k in('majority','clean_items','singlaw_correctness','clean_by_person','flagged_incorrect','partial_unanimous')}))
print(json.dumps(out['final']['reference_label']['pairwise']))
print(json.dumps(out['by_person']))
for q in out['flagged_incorrect']: 
    r=next(x for x in final if x['question_id']==q); print(q,r['reference_label_votes'],'SingLaw',C[q]['correctness_norm'],'|Q',C[q]['question'][:130],'|REF',C[q]['reference_answer'][:150],'|',r['notes'][:300])
print('badr-189',next(x for x in final if x['question_id']=='badr-189')['reference_label_votes'])
print('first 5 flagged now',{q:next(x for x in final if x['question_id']==q)['reference_label'] for q in ['badr-002','badr-189','binyao-027','binyao-062','sumo-060']})
