"""Ablation results: retrieval for all runs, judged scores for A-E, with paired bootstrap CIs on the differences."""
import csv,glob,json,math,random,re,sys
from pathlib import Path
AB=Path(__file__).resolve().parent; B=AB.parent; W=B/'work'; ROOT=B.parents[2]; sys.path.insert(0,str(W/'darien'))
import judge_claude as jc, run_ragas_benchmark as rb
S={r['question_id']:r for r in csv.DictReader(open(AB/'sample.csv',encoding='utf-8',newline=''))}
part=json.loads((ROOT/'eval/benchmark_partition/partition.json').read_text())['people']
acts={p:{a['doc_id'] for a in part[p]['acts']} for p in part}
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
RUNS=['R1_bm25_only','R2_dense_only','A_hybrid','B_rerank','C_rewrite','D_rerank_rewrite','E_no_grounding_rules']
R={run:{} for run in RUNS}
for run in RUNS:
    for f in glob.glob(str(AB/f'{run}_shard*.jsonl')):
        for l in open(f,encoding='utf-8'):
            if l.strip(): d=json.loads(l); R[run][d['question_id']]=d
Q=sorted(S)
M={}
for run in RUNS:
    for q in Q:
        if q not in R[run]: continue
        rk=[]
        for c in R[run][q]['retrieved']:
            u=rb.unit_of(c)
            if u not in rk: rk.append(u)
        M.setdefault(run,{})[q]=rb.retrieval_metrics(rk,gold(S[q]))
keys=['P@1','P@5','P@10','R@5','R@10','R@20','Hit@1','Hit@10','MRR','nDCG@10']
rng=random.Random(7)
def mean(v): return sum(v)/len(v)
def pdiff(a,b):
    d=[x-y for x,y in zip(a,b)]; n=len(d); bs=sorted(mean(rng.choices(d,k=n)) for _ in range(5000)); return round(mean(d),3),round(bs[125],3),round(bs[4874],3)
out={'retrieval':{r:{k:round(mean([M[r][q][k] for q in Q if q in M[r]]),3) for k in keys} for r in RUNS},'n':{r:len(R[r]) for r in RUNS}}
for r in RUNS: print(r,out['n'][r],out['retrieval'][r])
def rlat(r,k):
    v=sorted(x[k] for x in R[r].values() if k in x); return round(v[len(v)//2],1) if v else None
out['latency']={r:{'retrieve_p50':rlat(r,'latency_retrieve_s'),'answer_p50':rlat(r,'latency_answer_s')} for r in RUNS}; print(out['latency'])
out['rewrite_timeouts']={r:sum('rewrite_hyde_timed_out' in (x.get('done',{}).get('timings_ms') or {}) for x in R[r].values()) for r in RUNS}; print('rewrite timeouts',out['rewrite_timeouts'])
out['blank']={r:sum(not x.get('generated_answer','x').strip() for x in R[r].values()) for r in RUNS}; print('blank',out['blank'])
out['validator_flagged']={r:sum(not x.get('validation',{'grounded':True})['grounded'] for x in R[r].values() if x.get('generated_answer','').strip()) for r in RUNS[2:]}; print('validator flagged',out['validator_flagged'])
pairs=[('Hybrid vs BM25 only','A_hybrid','R1_bm25_only'),('Hybrid vs dense only','A_hybrid','R2_dense_only'),('Reranker alone','B_rerank','A_hybrid'),('Rewriting alone','C_rewrite','A_hybrid'),('Both vs baseline','D_rerank_rewrite','A_hybrid'),('Rewriting on top of reranker','D_rerank_rewrite','B_rerank'),('Reranker on top of rewriting','D_rerank_rewrite','C_rewrite')]
out['retrieval_gain']={n:{k:pdiff([M[a][q][k] for q in Q],[M[b][q][k] for q in Q]) for k in('MRR','nDCG@10','Hit@10','R@10')} for n,a,b in pairs if len(M.get(a,{}))==100 and len(M.get(b,{}))==100}
for n,v in out['retrieval_gain'].items(): print(n,v)
J=AB/'judge'
if (J/'key.json').exists() and glob.glob(str(J/'out/*.jsonl')):
    key=json.loads((J/'key.json').read_text()); bl=json.loads((J/'blank.json').read_text()); V={}
    for f in glob.glob(str(J/'out/*.jsonl')):
        for l in open(f):
            if l.strip(): d=json.loads(l); V[d['id']]=d['judge']
    print('judged',len(V),'of',len(key),'blank',len(bl))
    sc={r:{} for r in RUNS[2:]}
    for jid,k in key.items():
        if jid in V:
            r=R[k['run']][k['question_id']]; sc[k['run']][k['question_id']]={**jc.score({**r,'context_recall':None},V[jid]),'reason':V[jid].get('reason','')}
    for run,q in bl: sc[run][q]={'faithfulness':0.0,'answer_correctness':0.0,'answer_relevancy':0.0,'context_precision':0.0,'refused':False,'reason':'blank answer'}
    keysj=['answer_correctness','faithfulness','answer_relevancy','context_precision']
    out['judged']={r:{'n':len(sc[r]),**{k:round(mean([float(sc[r][q][k]) for q in sc[r]]),3) for k in keysj},'refused':sum(sc[r][q].get('refused',False) for q in sc[r])} for r in sc if sc[r]}
    for r,v in out['judged'].items(): print(r,v)
    jp=[('Reranker alone','B_rerank','A_hybrid'),('Rewriting alone','C_rewrite','A_hybrid'),('Both vs baseline','D_rerank_rewrite','A_hybrid'),('Rewriting on top of reranker','D_rerank_rewrite','B_rerank'),('Reranker on top of rewriting','D_rerank_rewrite','C_rewrite'),('Citation rules on vs off','D_rerank_rewrite','E_no_grounding_rules')]
    out['judged_gain']={}
    for n,a,b in jp:
        qs=sorted(set(sc[a])&set(sc[b]))
        out['judged_gain'][n]={k:pdiff([float(sc[a][q][k]) for q in qs],[float(sc[b][q][k]) for q in qs]) for k in keysj}; out['judged_gain'][n]['n']=len(qs); print(n,out['judged_gain'][n])
    with open(AB/'ablation_per_question.csv','w',encoding='utf-8',newline='') as f:
        w=csv.writer(f); w.writerow('run question_id question_type answer_correctness faithfulness answer_relevancy context_precision MRR Hit@10 R@10 nDCG@10 latency_answer_s blank reason'.split())
        for r in RUNS[2:]:
            for q in sorted(sc[r]):
                s=sc[r][q];m=M[r][q];w.writerow([r,q,S[q]['question_type'],s['answer_correctness'],round(s['faithfulness'],3),s['answer_relevancy'],round(s['context_precision'],3),round(m['MRR'],3),m['Hit@10'],round(m['R@10'],3),round(m['nDCG@10'],3),R[r][q].get('latency_answer_s'),not R[r][q]['generated_answer'].strip(),s['reason']])
    out['changed']={n:{'better':sum(float(sc[a][q]['answer_correctness'])>float(sc[b][q]['answer_correctness']) for q in set(sc[a])&set(sc[b])),'worse':sum(float(sc[a][q]['answer_correctness'])<float(sc[b][q]['answer_correctness']) for q in set(sc[a])&set(sc[b]))} for n,a,b in jp}; print('correctness moves',out['changed'])
out['by_type_retrieval']={r:{t:{'MRR':round(mean([M[r][q]['MRR'] for q in Q if S[q]['question_type']==t]),3),'Hit@10':round(mean([M[r][q]['Hit@10'] for q in Q if S[q]['question_type']==t]),3)} for t in('provision_lookup','lay_language','case_law','multi_hop')} for r in RUNS if len(M.get(r,{}))==100}
(AB/'ablation_summary.json').write_text(json.dumps(out,indent=1))
print('by type',json.dumps(out['by_type_retrieval']))
