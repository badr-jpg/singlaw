"""Q2: five queries, one at a time, through the same pipeline as /api/chat. Records sources, answer, stage timings and token usage."""
import asyncio,json,sys,time
from pathlib import Path
ROOT=Path(__import__('os').environ.get('SINGLAW_ROOT','.')).resolve(); sys.path.insert(0,str(ROOT/'backend')); D=ROOT/'data/export/submission/deliverables/q2_queries'
QUERIES=[('provision_lookup','What duty does the Companies Act 1967 place on a director to act honestly?'),
('lay_language','Can my bank tell someone else about my account details?'),
('case_law','What must a claimant show to establish a duty of care in negligence under Singapore case law?'),
('multi_hop','Under the Moneylenders Act 2008, when can the Registrar forfeit a licensee\'s security deposit, and how can the licensee challenge it?'),
('out_of_scope','What is the minimum wage in Malaysia?')]
async def main():
    from app.answer import chat_stream
    from app.config import get_settings
    from app.context import build_context,shutdown_context
    from app.retrieval import analyze_query,retrieve
    s=get_settings(); t0=time.perf_counter(); ctx=await build_context(s); await ctx.registry.load(); load=time.perf_counter()-t0
    usage=[]; client=ctx.llm._client; orig=client.chat.completions.create
    async def create(**k):
        st=bool(k.get('stream'))
        if st: k['stream_options']={'include_usage':True}
        r=await orig(**k)
        if not st:
            u=getattr(r,'usage',None); usage.append({'model':k.get('model'),'prompt':getattr(u,'prompt_tokens',None),'completion':getattr(u,'completion_tokens',None)}); return r
        async def gen():
            async for c in r:
                u=getattr(c,'usage',None)
                if u: usage.append({'model':k.get('model'),'prompt':u.prompt_tokens,'completion':u.completion_tokens})
                yield c
        return gen()
    client.chat.completions.create=create
    out=[]
    for typ,q in QUERIES:
        usage.clear(); t1=time.perf_counter(); text='';srcs=[];done={};meta={};ev=None;first=None
        async for fr in chat_stream(ctx,q,None,None):
            d=None
            for line in fr.strip().split('\n'):
                if line.startswith('event: '): ev=line[7:]
                elif line.startswith('data: '): d=json.loads(line[6:])
            if d is None: continue
            if ev=='token':
                if first is None: first=time.perf_counter()-t1
                text+=d.get('text','')
            elif ev=='sources': srcs=d.get('sources',[]); t_src=time.perf_counter()-t1
            elif ev=='meta': meta=d
            elif ev=='done': done=d
        total=time.perf_counter()-t1
        # retrieval only, helper results now cached, so this shows search + rerank alone
        t2=time.perf_counter(); a=await analyze_query(ctx,q); res=await retrieve(ctx,q,analysis=a,rewrites=[],hyde=None); ret=time.perf_counter()-t2
        await asyncio.sleep(0)
        out.append({'type':typ,'query':q,'intent':meta.get('intent'),'low_confidence':meta.get('low_confidence'),'seconds_to_sources':round(t_src,2) if srcs else None,'seconds_to_first_token':round(first,2) if first else None,'seconds_total':round(total,2),'seconds_search_and_rerank_only':round(ret,2),'timings_ms':done.get('timings_ms'),'usage':list(usage),'answer':text,'n_sources':len(srcs),'top_sources':[{'n':x['n'],'citation':x['citation'],'chunk_id':x['chunk_id']} for x in srcs[:5]]})
        print(typ,'total',round(total,1),'first',first and round(first,1),'search',round(ret,1),'chars',len(text),'usage',usage,'|',[x['citation'][:40] for x in srcs[:2]],flush=True)
    res={'config':{'profile':s.model_profile,'reranker':ctx.registry.reranker_name_active,'fusion_top':s.fusion_top,'rerank_top':s.rerank_top,'final_top':s.final_top,'llm':s.llm_model,'fast_llm':s.llm_fast_model,'prestage_budget_s':s.llm_prestage_budget_seconds,'machine':'Apple M4 Max, 64 GB, MPS','model_load_seconds':round(load,1),'order':'one at a time'},'queries':out}
    (D/'five_queries.json').write_text(json.dumps(res,indent=1,ensure_ascii=False)); await shutdown_context(ctx)
asyncio.run(main())
