"""Consolidate: full retrieval (P@K, R@K, MRR, nDCG) and RAG metrics for all 1,000 questions.
Runs: badr, darien, binyao, sumo = first run; huang = rerun on the published index.
RAG judge: Haiku for badr, binyao, sumo, huang; Opus for darien (original), with 40 of darien's re-judged by Haiku to compare."""
import csv,glob,json,random,re,sys,collections
from pathlib import Path
csv.field_size_limit(10**8)
R=Path(__file__).resolve().parent; W=R.parent; B=W.parent; ROOT=B.parents[2]; S=W/'combined/src'; D=ROOT/'data/export/submission/deliverables'; sys.path.insert(0,str(W/'darien'))
import judge_claude as jc, run_ragas_benchmark as rb
text,pas=rb.load_export(W/'chunks.jsonl')
def jl(p): return [json.loads(l) for l in open(p,encoding='utf-8') if l.strip()]
part=json.loads((ROOT/'eval/benchmark_partition/partition.json').read_text())['people']; acts={p:{a['doc_id'] for a in part[p]['acts']} for p in part}
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
C={r['question_id']:r for r in csv.DictReader(open(B/'combined_results.csv',encoding='utf-8-sig'))}
L={r['question_id']:r for r in csv.DictReader(open(B/'annotation_labels.csv',encoding='utf-8-sig'))}
run={}
for x in jl(B/'badr_run/badr_results.jsonl'): run[x['question_id']]=dict(ans=x['generated_answer'],ids=x['retrieved'],src=x['sources'],lat=x['latency_answer_s'])
for x in jl(S/'darien/darien_results.original.jsonl'): run[x['question_id']]=dict(ans=x['generated_answer'],ids=x['retrieved'],src=x['sources'],lat=x['latency_answer_s'])
for p in('binyao','sumo'):
    for x in jl(S/p/f'{p}_run_minimax.jsonl'): run[x['question_id']]=dict(ans=x['answer'],ids=[s['chunk_id'] for s in x['sources']],src=x['sources'],lat=x.get('t_total'))
for f in glob.glob(str(B/'huang_rerun/shard_*.jsonl')):
    for x in jl(f): run[x['question_id']]=dict(ans=x['generated_answer'],ids=x['retrieved'],src=x['sources'],lat=x['latency_answer_s'])
assert len(run)==1000
J={}
for x in jl(B/'badr_run/badr_judged.jsonl'): J[x['question_id']]={**x['scores'],'judge_model':'claude-haiku-5-5','reason':x['judge'].get('reason','')}
for x in jl(S/'darien/darien_judged.original.jsonl'): J[x['question_id']]={**x['scores'],'judge_model':'claude-opus-5-5','reason':x['judge'].get('reason','')}
key=json.loads((R/'key.json').read_text()); V={}
for f in glob.glob(str(R/'out/*.jsonl')):
    for x in jl(f): V[x['id']]=x['judge']
missing=[k for k in key if k not in V]; print('rag judged',len(V),'of',len(key),'missing',len(missing))
cal=[]
for jid,k in key.items():
    if jid not in V: continue
    q=k['question_id']; sc=jc.score({'sources':run[q]['src'],'context_recall':None},V[jid])
    if k['set']=='darien_calibration': cal.append((q,sc,V[jid].get('reason','')))
    else: J[q]={**sc,'judge_model':'claude-haiku-5-5','reason':V[jid].get('reason','')}
for tag,q in json.loads((R/'blank.json').read_text()):
    if tag!='darien_calibration': J[q]={'faithfulness':0.0,'answer_correctness':0.0,'answer_relevancy':0.0,'context_precision':0.0,'refused':False,'judge_model':'blank, not judged','reason':'blank answer'}
print('rag rows',len(J))
rows=[]
for q,c in C.items():
    r=run[q]; rk=[]
    for i in r['ids']:
        u=rb.unit_of(i)
        if u not in rk: rk.append(u)
    m=rb.retrieval_metrics(rk,gold(c))
    ctx=re.sub(r'\s+','',' '.join(text.get(i,'')[:2500] for i in r['ids']))
    # evidence quotes come from the question csv via combined sources
    rows.append({'c':c,'m':m,'r':r})
ev={}
for p in part:
    if p=='haotien': continue
    for x in csv.DictReader(open(B/'badr.csv' if p=='badr' else S/p/f'{p}.csv',encoding='utf-8-sig',newline='')): ev[x['question_id']]=x
out=[];keys=['P@1','P@5','P@10','R@5','R@10','R@20','Hit@1','Hit@5','Hit@10','Hit@20','MRR','nDCG@10']
for x in rows:
    c=x['c'];q=c['question_id'];ctx=re.sub(r'\s+','',' '.join(text.get(i,'')[:2500] for i in x['r']['ids'])); qs=ev[q]['evidence_quote'].split('|'); cr=sum(re.sub(r'\s+','',z) in ctx for z in qs)/len(qs)
    s=J.get(q)
    out.append({'person':c['person'],'question_id':q,'question_type':c['question_type'],'source_kind':c['source_kind'],'multi_document':c['multi_document'],'reference_label':L[q]['reference_label'],'answerable':L[q]['answerable'],'standalone':L[q]['standalone'],'clean_question':L[q]['reference_label']=='correct' and L[q]['answerable']=='yes' and L[q]['standalone']=='yes','run':'rerun on published index' if c['person']=='huang' else 'first run','reranker':'Qwen3-Reranker-0.6B' if c['person'] in('badr','darien','huang') else 'ms-marco-MiniLM-L-6-v2','answer_blank':not x['r']['ans'].strip(),'answer_chars':len(x['r']['ans'].strip()),'latency_answer_s':x['r']['lat'],**{k:round(x['m'][k],4) for k in keys},'context_recall':round(cr,4),'rag_judge':s['judge_model'],'answer_correctness':s['answer_correctness'],'faithfulness':round(s['faithfulness'],4),'answer_relevancy':s['answer_relevancy'],'context_precision':round(s['context_precision'],4),'refused':s.get('refused'),'judge_reason':s['reason'],'original_headline_correctness':c['correctness_norm'],'original_judge':c['judge'],'question':c['question'],'reference_answer':c['reference_answer'],'system_answer':x['r']['ans'],'gold_doc_ids':c['gold_doc_ids'],'gold_citations':c['gold_citations']})
with open(D/'q4_eval/final_results_1000.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,list(out[0].keys())); w.writeheader(); w.writerows(out)
rng=random.Random(20261107)
def ci(v):
    b=sorted(sum(rng.choices(v,k=len(v)))/len(v) for _ in range(2000)); return [round(b[50],3),round(b[1949],3)]
M=keys+['context_recall','answer_correctness','faithfulness','answer_relevancy','context_precision']
def agg(rs):
    o={'n':len(rs),'blank':sum(r['answer_blank'] for r in rs),'refused':sum(bool(r['refused']) for r in rs)}
    for k in M: o[k]=round(sum(float(r[k]) for r in rs)/len(rs),4)
    o['answer_correctness_ci95']=ci([float(r['answer_correctness']) for r in rs]); nb=[r for r in rs if not r['answer_blank']]
    o['answer_correctness_excl_blank']=round(sum(float(r['answer_correctness']) for r in nb)/len(nb),4); o['faithfulness_excl_blank']=round(sum(float(r['faithfulness']) for r in nb)/len(nb),4)
    l=sorted(float(r['latency_answer_s']) for r in rs if r['latency_answer_s'] not in(None,'')); o['latency_p50']=round(l[len(l)//2],1); o['latency_p90']=round(l[int(len(l)*.9)],1); return o
T=['provision_lookup','lay_language','case_law','multi_hop']; P=['badr','binyao','darien','huang','sumo']
SUM={'overall':agg(out),'clean_908':agg([r for r in out if r['clean_question']]),'by_person':{p:agg([r for r in out if r['person']==p]) for p in P},'by_type':{t:agg([r for r in out if r['question_type']==t]) for t in T},'by_source_kind':{k:agg([r for r in out if r['source_kind']==k]) for k in('act','judgment','mixed')},'multi_document':{str(k):agg([r for r in out if str(r['multi_document'])==str(k)]) for k in(True,False)},'by_reranker':{k:agg([r for r in out if r['reranker']==k]) for k in('Qwen3-Reranker-0.6B','ms-marco-MiniLM-L-6-v2')},'by_reference_label':{k:agg([r for r in out if r['reference_label']==k]) for k in('correct','partial')}}
# Opus vs Haiku on the same answers
dj={x['question_id']:x for x in jl(S/'darien/darien_judged.original.jsonl')}
pairs=[(dj[q]['scores'],s,q) for q,s,_ in cal]
n=len(pairs); agreeC=sum(a['answer_correctness']==b['answer_correctness'] for a,b,_ in pairs)/n; agreeR=sum(a['answer_relevancy']==b['answer_relevancy'] for a,b,_ in pairs)/n
SUM['judge_calibration_darien_40']={'n':n,'correctness_opus':round(sum(a['answer_correctness'] for a,_,_ in pairs)/n,4),'correctness_haiku':round(sum(b['answer_correctness'] for _,b,_ in pairs)/n,4),'correctness_agreement':round(agreeC,4),'relevancy_opus':round(sum(a['answer_relevancy'] for a,_,_ in pairs)/n,4),'relevancy_haiku':round(sum(b['answer_relevancy'] for _,b,_ in pairs)/n,4),'relevancy_agreement':round(agreeR,4),'faithfulness_opus':round(sum(a['faithfulness'] for a,_,_ in pairs)/n,4),'faithfulness_haiku':round(sum(b['faithfulness'] for _,b,_ in pairs)/n,4),'context_precision_opus':round(sum(a['context_precision'] for a,_,_ in pairs)/n,4),'context_precision_haiku':round(sum(b['context_precision'] for _,b,_ in pairs)/n,4),'correctness_disagreements':[q for a,b,q in pairs if a['answer_correctness']!=b['answer_correctness']]}
hu=[r for r in out if r['person']=='huang']; SUM['huang_original_vs_rerun']={'original_headline_correctness_sonnet':round(sum(float(r['original_headline_correctness']) for r in hu)/200,4),'rerun_correctness_haiku':round(sum(float(r['answer_correctness']) for r in hu)/200,4),'note':'Different index and models, different judges and scales.'}
(D/'q4_eval/final_metrics.json').write_text(json.dumps(SUM,indent=1))
for k in('overall','clean_908'): print(k,SUM[k])
for g in('by_person','by_type','by_reranker','multi_document','by_reference_label'):
    print('==',g)
    for k,v in SUM[g].items(): print(k,{x:v[x] for x in('n','blank','answer_correctness','answer_correctness_excl_blank','faithfulness','answer_relevancy','context_precision','context_recall','P@5','R@10','Hit@10','MRR','nDCG@10','latency_p50')})
print(SUM['judge_calibration_darien_40']); print(SUM['huang_original_vs_rerun'])
