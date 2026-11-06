"""Exact Match and token F1 (SQuAD-style normalisation) across the 1,000 questions, plus corpus counts; eval.jsonl."""
import csv,json,re,string,collections,statistics as st
from pathlib import Path
csv.field_size_limit(10**8)
ROOT=Path(__import__('os').environ.get('SINGLAW_ROOT','.')).resolve(); B=ROOT/'data/export/benchmark'; D=ROOT/'data/export/submission/deliverables'
rows=list(csv.DictReader(open(D/'q4_eval/final_results_1000.csv',encoding='utf-8-sig')))
L={r['question_id']:r for r in csv.DictReader(open(B/'annotation_labels.csv',encoding='utf-8-sig'))}
def norm(s):
    s=re.sub(r'\[CITE:\d+\]',' ',s or '').lower(); s=re.sub(r'^\s*as at \d{4}-\d{2}-\d{2},?',' ',s.strip())
    s=''.join(c if c not in string.punctuation+'“”‘’–—' else ' ' for c in s); s=re.sub(r'\b(a|an|the)\b',' ',s); return ' '.join(s.split())
def f1(p,g):
    P,G=norm(p).split(),norm(g).split()
    if not P or not G: return 0.0,0.0,0.0
    c=sum((collections.Counter(P)&collections.Counter(G)).values())
    if not c: return 0.0,0.0,0.0
    pr,re_=c/len(P),c/len(G); return pr,re_,2*pr*re_/(pr+re_)
out=[];
for r in rows:
    p,re_,f=f1(r['system_answer'],r['reference_answer']); out.append({**r,'em':float(norm(r['system_answer'])==norm(r['reference_answer'])) if r['system_answer'].strip() else 0.0,'tp':p,'tr':re_,'tf':f})
def agg(x): return {'n':len(x),'exact_match':round(sum(y['em'] for y in x)/len(x),4),'token_precision':round(sum(y['tp'] for y in x)/len(x),4),'token_recall':round(sum(y['tr'] for y in x)/len(x),4),'token_f1':round(sum(y['tf'] for y in x)/len(x),4)}
S={'overall':agg(out),'by_person':{p:agg([y for y in out if y['person']==p]) for p in ['badr','binyao','darien','huang','sumo']},'by_type':{t:agg([y for y in out if y['question_type']==t]) for t in ['provision_lookup','lay_language','case_law','multi_hop']},'clean_908':agg([y for y in out if L[y['question_id']]['reference_label']=='correct' and L[y['question_id']]['answerable']=='yes' and L[y['question_id']]['standalone']=='yes'])}
S['note']='Answers are long, cited explanations (median chars below); reference answers are 1-3 sentences. Token precision is structurally low, so these read lower than judged correctness.'
S['median_answer_chars']=st.median(int(r['answer_chars']) for r in rows); S['median_reference_chars']=st.median(len(r['reference_answer']) for r in rows)
(D/'q4_eval/exact_match_f1.json').write_text(json.dumps(S,indent=1)); print(json.dumps({k:S[k] for k in('overall','by_type','clean_908','median_answer_chars','median_reference_chars')}))
# eval.jsonl
S_=B/'work/combined/src'; ev=[]
for p in ['badr','binyao','darien','huang','sumo']:
    for r in csv.DictReader(open(B/'badr.csv' if p=='badr' else S_/p/f'{p}.csv',encoding='utf-8-sig',newline='')):
        l=L[r['question_id']]; ev.append({'question_id':r['question_id'],'partition':p,'question':r['question'],'reference_answer':r['answer'],'question_type':r['question_type'],'source_type_as_written':r['source_type'],'gold_doc_ids':r['gold_doc_ids'].split('|'),'gold_citations':r['gold_citations'].split('|'),'evidence_quotes':r['evidence_quote'].split('|'),'reference_label':l['reference_label'],'answerable':l['answerable'],'standalone':l['standalone'],'annotator_votes':{'reference_label':l['reference_label_votes'],'answerable':l['answerable_votes'],'standalone':l['standalone_votes']},'reannotated_with_full_section':l['reannotated_with_full_section']=='True','annotator_notes':l['notes']})
with open(D/'q4_eval/eval.jsonl','w',encoding='utf-8') as f:
    for e in ev: f.write(json.dumps(e,ensure_ascii=False)+'\n')
print('eval rows',len(ev),'unique questions',len({e['question'].strip().lower() for e in ev}))
# corpus stats + word counts per type
W=collections.Counter();dt=collections.Counter();docs=collections.defaultdict(set);words=collections.Counter();lens=[]
for l in open(B/'work/chunks.jsonl',encoding='utf-8'):
    c=json.loads(l);t=c.get('doc_type');dt[t]+=1;docs[t].add(c['doc_id']);tok=re.findall(r"[a-z0-9]+(?:['’-][a-z0-9]+)*",(c.get('text') or '').lower());W.update(tok);words[t]+=len(tok);lens.append(len(tok))
lens.sort()
stats={'documents':{k:len(v) for k,v in docs.items()},'documents_total':sum(len(v) for v in docs.values()),'chunks':dict(dt),'chunks_total':sum(dt.values()),'words':dict(words),'words_total':sum(W.values()),'types_unique_words':len(W),'chunk_words_p10_p50_p90':[lens[len(lens)//10],lens[len(lens)//2],lens[len(lens)*9//10]],'tokenizer':"lowercase regex [a-z0-9]+(?:['’-][a-z0-9]+)*",'source_passages_judgments':10000,'source':{'acts':'Kaidon-Ng/singapore-statutes @ 8b81a0c','judgments':'badlaldh/singapore-judgments @ 290e968','index':'badlaldh/singlaw-vdb @ aecbff9'}}
(D/'q1_corpus/corpus_stats.json').write_text(json.dumps(stats,indent=1)); print(json.dumps(stats))
