"""Ablation worker. Features are switched here for the test only; the app's code is unchanged.
usage: run_ablation.py <shard> <nshards> <concurrency>   env: DATA_DIR, FUSION_TOP, LLM_PRESTAGE_BUDGET_SECONDS"""
import asyncio,csv,json,sys,time
from pathlib import Path
AB=Path(__file__).resolve().parent; B=AB.parent; W=B/'work'; ROOT=B.parents[2]
sys.path.insert(0,str(W/'darien')); sys.path.insert(0,str(ROOT/'backend'))
import run_ragas_benchmark as rb
shard,nsh,conc=int(sys.argv[1]),int(sys.argv[2]),int(sys.argv[3])
CONFIGS=[('R1_bm25_only',dict(search='sparse',rerank=False,rewrite=False,grounding=True,answer=False)),
 ('R2_dense_only',dict(search='dense',rerank=False,rewrite=False,grounding=True,answer=False)),
 ('A_hybrid',dict(search='hybrid',rerank=False,rewrite=False,grounding=True,answer=True)),
 ('B_rerank',dict(search='hybrid',rerank=True,rewrite=False,grounding=True,answer=True)),
 ('C_rewrite',dict(search='hybrid',rerank=False,rewrite=True,grounding=True,answer=True)),
 ('D_rerank_rewrite',dict(search='hybrid',rerank=True,rewrite=True,grounding=True,answer=True)),
 ('E_no_grounding_rules',dict(search='hybrid',rerank=True,rewrite=True,grounding=False,answer=True))]
CFG={}
async def main():
    import app.answer as ans
    from app.config import get_settings
    from app.context import build_context,shutdown_context
    from app.retrieval import analyze_query,retrieve
    rows=[r for i,r in enumerate(csv.DictReader(open(AB/'sample.csv',encoding='utf-8',newline=''))) if i%nsh==shard]
    texts,_=rb.load_export(W/'chunks.jsonl')
    s=get_settings(); ctx=await build_context(s); await ctx.registry.load(); reg=ctx.registry; store=ctx.store
    lock=asyncio.Lock(); orig_r,orig_e=reg.rerank,reg.embed_queries
    async def rr(q,t):
        if not CFG['rerank']: return [1.0-i/max(1,len(t)) for i in range(len(t))]  # keep fusion order; the final blend then sees that order
        async with lock: return await orig_r(q,t)
    async def eq(t):
        async with lock: return await orig_e(t)
    reg.rerank,reg.embed_queries=rr,eq
    od,osp=store.search_dense,store.search_sparse
    async def sd(*a,**k): return [] if CFG['search']=='sparse' else await od(*a,**k)
    async def ssp(*a,**k): return [] if CFG['search']=='dense' else await osp(*a,**k)
    store.search_dense,store.search_sparse=sd,ssp
    orig_rw=ans.rewrite_and_hyde
    async def rw(c,q): return await orig_rw(c,q) if CFG['rewrite'] else ([],None)
    ans.rewrite_and_hyde=rw
    full_prompt=ans._SYSTEM_PROMPT
    L=full_prompt.split('\n')
    plain='\n'.join(x.replace('STRICT GROUNDING RULES — these override everything else:','GUIDELINES:') for x in L if not (x.startswith('1. Use ONLY') or x.startswith('2. Every factual')))
    assert plain!=full_prompt and '{as_at}' in plain and 'CITE' not in plain
    print(f"shard {shard}: profile={s.model_profile} reranker={reg.reranker_name_active} fusion_top={s.fusion_top} budget={s.llm_prestage_budget_seconds} llm={s.llm_model}/{s.llm_fast_model} on={ctx.llm.configured} n={len(rows)} conc={conc}",flush=True)
    try:
        for name,cfg in CONFIGS:
            CFG.clear(); CFG.update(cfg); ans._SYSTEM_PROMPT=full_prompt if cfg['grounding'] else plain
            out=AB/f'{name}_shard{shard}.jsonl'; done=set()
            if out.exists(): done={json.loads(l)['question_id'] for l in out.read_text().splitlines() if l.strip()}
            todo=[r for r in rows if r['question_id'] not in done]
            t0=time.time(); sem=asyncio.Semaphore(conc); wl=asyncio.Lock(); f=open(out,'a',encoding='utf-8'); print(f'== {name} start n={len(todo)}',flush=True)
            async def one(row):
                async with sem:
                    q=row['question']; rec={'question_id':row['question_id'],'run':name}; t1=time.perf_counter()
                    try:
                        if cfg['answer']:
                            text,srcs,dn,t_ret=await rb.answer(ctx,q)
                            ids=[x.get('chunk_id') for x in srcs if x.get('collection','sg_law')=='sg_law'][:20]
                            rec.update(generated_answer=text,latency_answer_s=round(time.perf_counter()-t1,2),latency_retrieve_s=round(t_ret,2),done={k:v for k,v in dn.items() if k!='message_id'},
                                sources=[{'n':x.get('n'),'chunk_id':x.get('chunk_id'),'citation':x.get('citation'),'text':texts.get(x.get('chunk_id'),x.get('snippet',''))[:2500]} for x in srcs],
                                validation=ans.validate_grounding(text,len(srcs)))
                        else:
                            a=await analyze_query(ctx,q); res=await retrieve(ctx,q,analysis=a,rewrites=[],hyde=None)
                            ids=[c.payload.chunk_id for c in res.chunks][:20]; rec.update(latency_retrieve_s=round(time.perf_counter()-t1,2))
                    except Exception as e:
                        print('ERR',name,row['question_id'],repr(e)[:250],flush=True); return
                    rec['retrieved']=ids
                    async with wl: f.write(json.dumps(rec,ensure_ascii=False)+'\n'); f.flush()
                    print(f"{name} {row['question_id']} n={len(ids)} t={time.perf_counter()-t1:.1f}s"+(f" chars={len(rec['generated_answer'].strip())}" if cfg['answer'] else ''),flush=True)
            await asyncio.gather(*(one(r) for r in todo)); f.close()
            print(f'== {name} done in {time.time()-t0:.0f}s',flush=True)
    finally:
        await shutdown_context(ctx)
asyncio.run(main())
