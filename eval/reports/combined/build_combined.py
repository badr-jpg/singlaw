"""Combine the benchmark results from every teammate's run into one CSV and one summary JSON.

Inputs: data/export/benchmark/work/combined/src/<person>/ (files taken from each PR or branch),
        data/export/benchmark/badr_run/, data/export/benchmark/work/chunks.jsonl
Outputs: data/export/benchmark/combined_results.csv (contains legal text; gitignored)
         eval/reports/combined/summary.json (aggregates only)

Each person's headline run is used: the first run, with no retries. Retrieval is recomputed for all
four runs on the published index with one parser, so those numbers are comparable. Judge scores are
kept raw and also normalised to 0-1, but they came from different judges and rubrics.
"""
import csv,json,random,re,statistics as st,collections
from pathlib import Path
csv.field_size_limit(10**8)
ROOT=Path(__file__).resolve().parents[3]; B=ROOT/'data/export/benchmark'; S=B/'work/combined/src'
PEOPLE=['badr','binyao','darien','huang','sumo']
part=json.loads((ROOT/'eval/benchmark_partition/partition.json').read_text())['people']
def rd(p): return list(csv.DictReader(open(p,encoding='utf-8-sig',newline='')))
def jl(p): return [json.loads(l) for l in open(p,encoding='utf-8') if l.strip()]
# ---- index: chunk text, passage id -> chunk id
text={};pas={}
for c in jl(B/'work/chunks.jsonl'):
    text[c['chunk_id']]=c.get('text') or ''
    if c.get('doc_type')=='judgment' and ':part' in c['chunk_id']:
        gd=(c.get('source_url') or '').rstrip('/').rsplit('/',1)[-1]; pas[f"{gd}-{int(c['chunk_id'].rsplit(':part',1)[1]):04d}"]=c['chunk_id']
def unit(cid):
    m=re.match(r'^(.*?:s[0-9A-Za-z]+?)(?:\.\d+)?$',cid)
    return m.group(1) if m and ':part' not in cid else cid
UNITS={unit(c) for c in text}
def sections(cite):
    """'Act 1967, ss 3(2) and 4' -> 3, 4; 'ss 57-58' -> 57, 58; 's 7 (Rule 2)' -> 7."""
    m=re.search(r',\s*(?:ss?|sections?)\.?\s*(.+)$',cite,re.I)
    loc=re.sub(r'\([^)]*\)','',m.group(1) if m else cite.rsplit(',',1)[-1])
    out=[]
    for a,b in re.findall(r'(\d+[A-Z]*)(?:\s*[-–—]\s*(\d+[A-Z]*))?',loc):
        if b and a.isdigit() and b.isdigit(): out+=[str(n) for n in range(int(a),int(b)+1)]
        else: out+=[a]+([b] if b else [])
    return out
def gold(row,acts):
    units=set();docs=set();bad=[]
    for d,c in zip(row['gold_doc_ids'].split('|'),row['gold_citations'].split('|')):
        if d in acts:
            docs.add(d); ss=sections(c)
            for n in ss: units.add(f'{d}:s{n}')
            if not ss: bad.append(d)
        elif d in pas:
            units.add(pas[d]); docs.add(pas[d].split(':',1)[0])
        else: bad.append(d)
    return units,docs,bad
def retr(ids,row,acts):
    g,docs,bad=gold(row,acts); r=[]
    for c in ids:
        u=unit(c)
        if u not in r: r.append(u)
    hit=lambda k:float(bool(g&set(r[:k])))
    rr=next((1/i for i,u in enumerate(r,1) if u in g),0.0)
    ctx=re.sub(r'\s+','',' '.join(text.get(c,'')[:2500] for c in ids))
    q=row['evidence_quote'].split('|')
    return {'hit_at_1':hit(1),'hit_at_5':hit(5),'hit_at_10':hit(10),'hit_at_20':hit(20),'mrr':round(rr,4),
            'recall_at_10':round(len(g&set(r[:10]))/len(g),4) if g else 0.0,
            'doc_hit_at_20':float(bool(docs&{c.split(':',1)[0] for c in ids})),
            'context_recall':round(sum(re.sub(r'\s+','',x) in ctx for x in q)/len(q),4),
            'gold_units_missing_from_index':len([u for u in g if u not in UNITS])+len(bad)}
TRUNCATED={'sumo-006','sumo-018'}  # stopped after a few words (sumo's report)
rows=[]
for p in PEOPLE:
    q=rd(B/f'{p}.csv') if p=='badr' else rd(S/p/f'{p}.csv')
    acts={a['doc_id'] for a in part[p]['acts']}
    if p in('badr','darien'):
        run={r['question_id']:r for r in jl(B/'badr_run/badr_results.jsonl' if p=='badr' else S/p/'darien_results.original.jsonl')}
        jd={r['question_id']:r for r in jl(B/'badr_run/badr_judged.jsonl' if p=='badr' else S/p/'darien_judged.original.jsonl')}
    elif p in('binyao','sumo'):
        run={r['question_id']:r for r in jl(S/p/f'{p}_run_minimax.jsonl')}
        jd={r['question_id']:r for r in jl(S/p/f'{p}_judge_minimax.jsonl')}
    else:
        ans={r['question_id']:r['system_answer'] for r in rd(S/p/'huang_minimax_answers.csv')}
        jd={r['question_id']:r for r in rd(S/p/'huang_claude_scores.csv')}
    for row in q:
        i=row['question_id']; o={'person':p,**{k:row[k] for k in('question_id','question_type','source_type','question','gold_doc_ids','gold_citations')},'reference_answer':row['answer']}
        faith=rel=None
        if p in('badr','darien'):
            ra=run[i]; a=ra['generated_answer']; s=jd[i]['scores']; raw=s['answer_correctness']; norm=float(raw); faith=s['faithfulness']; rel=s['answer_relevancy']; reason=jd[i]['judge'].get('reason','') or ''; lat=ra['latency_answer_s']; ids=ra['retrieved']
            scale='1/0.5/0'; refused=bool(s.get('refused'))
        elif p in('binyao','sumo'):
            ra=run[i]; a=ra['answer']; raw=jd[i]['correct']; norm=raw/2; reason=jd[i].get('note',''); lat=ra.get('t_total'); ids=[x['chunk_id'] for x in ra['sources']]; scale='2/1/0'; refused=None
        else:
            a=ans.get(i,''); d=jd[i]; raw=int(d['correctness']); norm=raw/4; rel=int(d['answer_relevance'])/4; faith=int(d['faithfulness'])/4 if d['faithfulness'] not in('','None','null','N/A','n/a') else None; reason=d['reason']; lat=None; ids=None; scale='0-4'; refused=None
        kinds={'act' if d in acts else 'judgment' for d in row['gold_doc_ids'].split('|')}
        o.update(source_kind='mixed' if len(kinds)>1 else next(iter(kinds)),multi_document=len(set(row['gold_doc_ids'].split('|')))>1,truncated=i in TRUNCATED,system_answer=a,answer_chars=len(a.strip()),blank=len(a.strip())==0,correctness_raw=raw,correctness_scale=scale,correctness_norm=round(norm,4),faithfulness_norm=None if faith is None else round(faith,4),relevancy_norm=rel,refused_by_judge=refused,judge_reason=reason,latency_answer_s=lat)
        o.update(retr(ids,row,acts) if ids is not None else dict.fromkeys(['hit_at_1','hit_at_5','hit_at_10','hit_at_20','mrr','recall_at_10','doc_hit_at_20','context_recall','gold_units_missing_from_index']))
        rows.append(o)
CONFIG={'badr':dict(judge='Claude Haiku 5.5 (subagents)',rubric='judge_claude.py',reranker='Qwen3-Reranker-0.6B',fusion_top=50,embedding='Qwen3-Embedding-0.6B',index='singlaw-vdb',llm='MiniMax-M3',machine='M4 Max, 2 workers x 4'),
 'binyao':dict(judge='Claude, model not recorded (manual)',rubric='2/1/0',reranker='ms-marco-MiniLM-L-6-v2',fusion_top='not stated (default 150)',embedding='Qwen3-Embedding-0.6B',index='singlaw-vdb',llm='MiniMax-M3',machine='Windows CPU, 5 at once'),
 'darien':dict(judge='Claude Opus 5.5 (in chat)',rubric='judge_claude.py',reranker='Qwen3-Reranker-0.6B',fusion_top=50,embedding='Qwen3-Embedding-0.6B',index='singlaw-vdb',llm='MiniMax-M3',machine='MacBook Air, 1 at a time'),
 'huang':dict(judge='Claude Sonnet 5.5',rubric='0-4 dimensions',reranker='ms-marco-MiniLM-L-6-v2',fusion_top='not stated (default 150)',embedding='all-MiniLM-L6-v2 (rebuilt index)',index='rebuilt from export, no citation graph',llm='MiniMax-M3',machine='dev profile; sources not saved'),
 'sumo':dict(judge='Claude, model not recorded (manual; run by binyao)',rubric='2/1/0',reranker='ms-marco-MiniLM-L-6-v2',fusion_top='not stated (default 150)',embedding='Qwen3-Embedding-0.6B',index='singlaw-vdb',llm='MiniMax-M3',machine='Windows CPU, 5 at once')}
for r in rows: r['judge']=CONFIG[r['person']]['judge']; r['reranker']=CONFIG[r['person']]['reranker']
cols=['person','question_id','question_type','source_type','source_kind','multi_document','truncated','correctness_norm','correctness_raw','correctness_scale','faithfulness_norm','relevancy_norm','blank','answer_chars','refused_by_judge','hit_at_1','hit_at_5','hit_at_10','hit_at_20','mrr','recall_at_10','doc_hit_at_20','context_recall','gold_units_missing_from_index','latency_answer_s','judge','reranker','judge_reason','question','reference_answer','system_answer','gold_doc_ids','gold_citations']
with open(B/'combined_results.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,cols,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
# ---- aggregates
rng=random.Random(20261106)
def ci(v):
    if not v: return None
    b=sorted(sum(rng.choices(v,k=len(v)))/len(v) for _ in range(2000)); return [round(b[50],3),round(b[1949],3)]
def agg(rs):
    o={'n':len(rs)}
    c=[r['correctness_norm'] for r in rs]
    o.update(correctness=round(sum(c)/len(c),4),correctness_ci95=ci(c),fully_correct=round(sum(x==1 for x in c)/len(c),4),partial=round(sum(0<x<1 for x in c)/len(c),4),zero=round(sum(x==0 for x in c)/len(c),4),blank=sum(r['blank'] for r in rs))
    nb=[r['correctness_norm'] for r in rs if not r['blank']]; o['correctness_excl_blank']=round(sum(nb)/len(nb),4)
    for k in('faithfulness_norm','relevancy_norm','hit_at_1','hit_at_5','hit_at_10','hit_at_20','mrr','recall_at_10','doc_hit_at_20','context_recall'):
        v=[float(r[k]) for r in rs if r[k] is not None]; o[k]=round(sum(v)/len(v),4) if v else None
    l=[r['latency_answer_s'] for r in rs if r['latency_answer_s'] is not None]; o['latency_p50']=round(st.median(l),1) if l else None
    return o
SUM={'config':CONFIG,'overall_all':agg(rows),'overall_same_index':agg([r for r in rows if r['person']!='huang']),
 'by_person':{p:agg([r for r in rows if r['person']==p]) for p in PEOPLE},
 'by_type':{t:agg([r for r in rows if r['question_type']==t]) for t in('provision_lookup','lay_language','case_law','multi_hop')},
 'by_type_same_index':{t:agg([r for r in rows if r['question_type']==t and r['person']!='huang']) for t in('provision_lookup','lay_language','case_law','multi_hop')},
 'person_by_type':{p:{t:agg([r for r in rows if r['person']==p and r['question_type']==t]) for t in('provision_lookup','lay_language','case_law','multi_hop')} for p in PEOPLE},
 'by_reranker_same_index':{k:agg([r for r in rows if r['person'] in v]) for k,v in {'Qwen3 (badr, darien)':('badr','darien'),'ms-marco (binyao, sumo)':('binyao','sumo')}.items()},
 'source_type_counts':{p:dict(collections.Counter(r['source_type'] for r in rows if r['person']==p)) for p in PEOPLE}}
SUM['source_kind_counts']={p:dict(collections.Counter(r['source_kind'] for r in rows if r['person']==p)) for p in PEOPLE}
SUM['multi_doc_counts']={p:sum(r['multi_document'] for r in rows if r['person']==p) for p in PEOPLE}
SUM['by_kind_same_index']={k:agg([r for r in rows if r['source_kind']==k and r['person']!='huang']) for k in('act','judgment','mixed')}
SUM['by_multi_doc_same_index']={str(k):agg([r for r in rows if r['multi_document']==k and r['person']!='huang']) for k in(True,False)}
buck=collections.defaultdict(collections.Counter);ids=collections.defaultdict(lambda:collections.defaultdict(list))
for r in rows:
    if r['correctness_norm']>=1: continue
    sev='zero' if r['correctness_norm']==0 else 'partial'
    if r['blank']: b='blank answer'
    elif r['hit_at_20'] is None: b='not classifiable (sources not saved)'
    elif r['doc_hit_at_20']==0: b='gold document not retrieved'
    elif r['hit_at_20']==0: b='right document, gold passage or section missed'
    elif r['context_recall'] is not None and r['context_recall']<1: b='multi-source: some gold evidence missing'
    else: b='all gold evidence retrieved, answer still short or wrong'
    buck[sev][b]+=1; ids[sev][b].append(r['question_id'])
SUM['failures']={k:dict(v.most_common()) for k,v in buck.items()}; SUM['failure_ids']={s:{k:v for k,v in d.items()} for s,d in ids.items()}
SUM['blank_ids']={p:[r['question_id'] for r in rows if r['person']==p and r['blank']] for p in PEOPLE}
SUM['short_nonblank_under_80_chars']=[(r['question_id'],r['answer_chars']) for r in rows if 0<r['answer_chars']<80]
SUM['gold_units_missing_from_index']={p:sum((r['gold_units_missing_from_index'] or 0)>0 for r in rows if r['person']==p) for p in PEOPLE}
(ROOT/'eval/reports/combined/summary.json').write_text(json.dumps(SUM,indent=1,ensure_ascii=False))
print('rows',len(rows),'->',B/'combined_results.csv')
h=['n','correctness','correctness_ci95','correctness_excl_blank','fully_correct','partial','zero','blank','faithfulness_norm','relevancy_norm','hit_at_1','hit_at_5','hit_at_10','hit_at_20','mrr','recall_at_10','doc_hit_at_20','context_recall','latency_p50']
for name,d in [('person',SUM['by_person']),('type all',SUM['by_type']),('type same-index',SUM['by_type_same_index']),('reranker',SUM['by_reranker_same_index'])]:
    print('\n==',name)
    for k,v in d.items(): print(k,{x:v[x] for x in h})
print('\noverall',SUM['overall_all']); print('same',SUM['overall_same_index'])
print('person_by_type correctness / mrr');
for p in PEOPLE: print(p,{t[:4]:(SUM['person_by_type'][p][t]['correctness'],SUM['person_by_type'][p][t]['mrr']) for t in SUM['by_type']})
print('source types',SUM['source_type_counts']); print('failures',SUM['failures']); print('blank',{k:len(v) for k,v in SUM['blank_ids'].items()}); print('short',SUM['short_nonblank_under_80_chars']); print('gold missing',SUM['gold_units_missing_from_index'])
