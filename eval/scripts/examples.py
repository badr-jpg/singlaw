"""Concrete before/after examples for Q3 and Q5, from the ablation runs. Rank = position of the first gold unit among the sources."""
import csv,glob,json,re,sys
from pathlib import Path
csv.field_size_limit(10**8)
ROOT=Path(__import__('os').environ.get('SINGLAW_ROOT','.')).resolve(); AB=ROOT/'data/export/benchmark/ablation'; W=AB.parent/'work'; D=ROOT/'data/export/submission/deliverables'; sys.path.insert(0,str(W/'darien'))
import run_ragas_benchmark as rb
S={r['question_id']:r for r in csv.DictReader(open(AB/'sample.csv',encoding='utf-8',newline=''))}
part=json.loads((ROOT/'eval/benchmark_partition/partition.json').read_text())['people']; acts={p:{a['doc_id'] for a in part[p]['acts']} for p in part}
_,pas=rb.load_export(W/'chunks.jsonl')
def secs(c):
    m=re.search(r',\s*(?:ss?|sections?)\.?\s*(.+)$',c,re.I); loc=re.sub(r'\([^)]*\)','',m.group(1) if m else c.rsplit(',',1)[-1]); o=[]
    for a,b in re.findall(r'(\d+[A-Z]*)(?:\s*[-–—]\s*(\d+[A-Z]*))?',loc):
        if b and a.isdigit() and b.isdigit(): o+=[str(n) for n in range(int(a),int(b)+1)]
        else: o+=[a]+([b] if b else [])
    return o
def gold(r):
    g=set();A=acts[r['question_id'].split('-')[0]]
    for d,c in zip(r['gold_doc_ids'].split('|'),r['gold_citations'].split('|')):
        if d in A: g|={f'{d}:s{n}' for n in secs(c)}
        elif d in pas: g.add(pas[d])
    return g
R={}
for run in ['R1_bm25_only','R2_dense_only','A_hybrid','B_rerank','C_rewrite','D_rerank_rewrite','E_no_grounding_rules']:
    R[run]={}
    for f in glob.glob(str(AB/f'{run}_shard*.jsonl')):
        for l in open(f,encoding='utf-8'):
            if l.strip(): d=json.loads(l); R[run][d['question_id']]=d
def rank(run,q):
    rk=[]
    for c in R[run][q]['retrieved']:
        u=rb.unit_of(c)
        if u not in rk: rk.append(u)
    g=gold(S[q]); return next((i for i,u in enumerate(rk,1) if u in g),None)
J={r['run']+'|'+r['question_id']:r for r in csv.DictReader(open(AB/'ablation_per_question.csv',encoding='utf-8'))} if (AB/'ablation_per_question.csv').exists() else {}
out={}
def pick(a,b,key,n):
    c=[]
    for q in S:
        ra,rb_=rank(a,q),rank(b,q)
        if rb_ and (ra is None or ra>=rb_+3): c.append((0 if ra is None else 1,-(ra or 99)+rb_,q,ra,rb_))
    c.sort(); 
    out[key]=[{'question_id':q,'question_type':S[q]['question_type'],'question':S[q]['question'],'gold':S[q]['gold_citations'],'rank_before':ra,'rank_after':rb_,'correctness_before':(J.get(f'{a}|{q}') or {}).get('answer_correctness'),'correctness_after':(J.get(f'{b}|{q}') or {}).get('answer_correctness')} for _,_,q,ra,rb_ in c[:n]]
    print(key,len(c),'candidates'); [print(' ',x['question_id'],x['question_type'],x['rank_before'],'->',x['rank_after'],x['correctness_before'],x['correctness_after'],'|',x['question'][:95]) for x in out[key]]
pick('R1_bm25_only','A_hybrid','bm25_to_hybrid',5); pick('R2_dense_only','A_hybrid','dense_to_hybrid',5); pick('A_hybrid','B_rerank','hybrid_to_reranker',6); pick('A_hybrid','C_rewrite','hybrid_to_rewriting',4); pick('B_rerank','A_hybrid','reranker_made_worse',4)
# answer-level changes
ans=[]
for a,b,name in [('A_hybrid','B_rerank','reranker'),('A_hybrid','C_rewrite','rewriting'),('E_no_grounding_rules','D_rerank_rewrite','citation_rules')]:
    for q in S:
        x,y=J.get(f'{a}|{q}'),J.get(f'{b}|{q}')
        if x and y and x['blank']=='False' and y['blank']=='False' and x['answer_correctness']!=y['answer_correctness']:
            ans.append({'feature':name,'question_id':q,'question':S[q]['question'],'before':x['answer_correctness'],'after':y['answer_correctness'],'reason_before':x['reason'],'reason_after':y['reason']})
out['answer_changes']=ans; print('answer changes',len(ans),[(a['feature'],a['question_id'],a['before'],a['after']) for a in ans])
(D/'q3_retrieval/before_after_examples.json').write_text(json.dumps(out,indent=1,ensure_ascii=False))
