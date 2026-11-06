"""One benchmark worker. Reuses the scoring/gold code from Darien's eval/run_ragas_benchmark.py (PR #7) unchanged;
adds sharding and in-process concurrency. usage: run_worker.py <csv> <out.jsonl> <shard> <nshards> <concurrency>
Env: DATA_DIR (a private copy of the index), FUSION_TOP."""
import asyncio,csv,json,sys,time
from pathlib import Path
W=Path(__file__).resolve().parent; ROOT=Path(__import__('os').environ.get('SINGLAW_ROOT','.')).resolve()
sys.path.insert(0,str(W/'darien')); sys.path.insert(0,str(ROOT/'backend'))
import run_ragas_benchmark as rb
csv_path,out_path,shard,nsh,conc=sys.argv[1],Path(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),int(sys.argv[5]); PERSON=sys.argv[6]
async def main():
    from app.config import get_settings
    from app.context import build_context,shutdown_context
    rows=list(csv.DictReader(open(csv_path,encoding='utf-8',newline='')))
    rows=[r for i,r in enumerate(rows) if i%nsh==shard]
    done=set()
    if out_path.exists():
        done={json.loads(l)['question_id'] for l in out_path.read_text().splitlines() if l.strip()}
    rows=[r for r in rows if r['question_id'] not in done]
    part=json.loads((ROOT/'eval/benchmark_partition/partition.json').read_text())
    acts={x['doc_id'] for x in part['people'][PERSON]['acts']}
    texts,passage=rb.load_export(W/'chunks.jsonl')
    s=get_settings(); ctx=await build_context(s); await ctx.registry.load()
    # one GPU call at a time inside this process: MPS is not safe across threads, and it adds no throughput
    lock=asyncio.Lock(); reg=ctx.registry; orig_r,orig_e=reg.rerank,reg.embed_queries
    async def rr(q,t):
        async with lock: return await orig_r(q,t)
    async def eq(t):
        async with lock: return await orig_e(t)
    reg.rerank,reg.embed_queries=rr,eq
    print(f"shard {shard}: profile={s.model_profile} reranker={reg.reranker_name_active} fusion_top={s.fusion_top} rerank_top={s.rerank_top} llm={s.llm_model}/{s.llm_fast_model} on={ctx.llm.configured} n={len(rows)} conc={conc}",flush=True)
    sem=asyncio.Semaphore(conc); wl=asyncio.Lock(); fout=open(out_path,'a',encoding='utf-8')
    async def one(row):
        async with sem:
            qid=row['question_id']; gold,gold_acts=rb.gold_units(row,acts,passage); t1=time.perf_counter()
            try:
                text,sources,dn,t_ret=await rb.answer(ctx,row['question'])
            except Exception as e:
                print('ERR',qid,repr(e)[:300],flush=True); return
            t_ans=time.perf_counter()-t1
            ids=[x.get('chunk_id') for x in sources if x.get('collection','sg_law')=='sg_law'][:20]
            ranked=[]
            for c in ids:
                u=rb.unit_of(c)
                if u not in ranked: ranked.append(u)
            m=rb.retrieval_metrics(ranked,gold)
            hits={c.split(':',1)[0] for c in ids[:10]}&gold_acts
            m['ActHit@10']=float(bool(hits)) if gold_acts else float(m['Hit@10'])
            rec={k:row[k] for k in('question_id','question','answer','question_type','source_type','gold_doc_ids','gold_citations','evidence_quote')}
            rec.update(gold_units=sorted(gold),retrieved=ids,metrics=m,latency_retrieve_s=round(t_ret,3),latency_answer_s=round(t_ans,3),generated_answer=text,low_confidence=None)
            rec['sources']=[{'n':x.get('n'),'chunk_id':x.get('chunk_id'),'citation':x.get('citation'),'text':texts.get(x.get('chunk_id'),x.get('snippet',''))[:2500]} for x in sources]
            rec['done']={k:v for k,v in dn.items() if k!='message_id'}
            ctxall=rb.squash(' '.join(x['text'] for x in rec['sources']))
            q=row['evidence_quote'].split('|'); rec['context_recall']=sum(rb.squash(y) in ctxall for y in q)/len(q)
            async with wl:
                fout.write(json.dumps(rec,ensure_ascii=False)+'\n'); fout.flush()
            print(f"{qid} hit10={m['Hit@10']:.0f} mrr={m['MRR']:.2f} ret={t_ret:.1f}s ans={t_ans:.1f}s chars={len(text)} n_src={len(sources)}",flush=True)
    try:
        await asyncio.gather(*(one(r) for r in rows))
    finally:
        fout.close(); await shutdown_context(ctx)
asyncio.run(main())
