import csv,json,statistics as st,collections
from pathlib import Path
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
csv.field_size_limit(10**8)
ROOT=Path(__import__('os').environ.get('SINGLAW_ROOT','.')).resolve(); D=ROOT/'data/export/submission/deliverables'; F=D/'figures'; AB=ROOT/'data/export/benchmark/ablation'
INK='#0b0b0b';SEC='#52514e';GRID='#e7e6e2';SUR='#fcfcfb';S=['#2a78d6','#eb6834','#1baf7a','#eda100','#e87ba4']
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.edgecolor':GRID,'axes.labelcolor':SEC,'xtick.color':SEC,'ytick.color':INK,'figure.facecolor':SUR,'axes.facecolor':SUR,'savefig.facecolor':SUR,'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,'axes.titlesize':10.5,'axes.titlecolor':INK,'axes.titleweight':'bold','axes.titlelocation':'left'})
def panels(ax,labels,vals,title,fmt='{:.3f}',xmax=None,color=S[0]):
    y=list(range(len(labels)))[::-1]; ax.barh(y,vals,height=.52,color=color,edgecolor=SUR,linewidth=2,zorder=3); ax.set_yticks(y); ax.set_yticklabels(labels); ax.set_title(title); ax.tick_params(length=0); ax.grid(axis='x',color=GRID,lw=.8,zorder=0)
    m=xmax or max(vals)*1.18; ax.set_xlim(0,m)
    for yy,v in zip(y,vals): ax.text(v+m*.015,yy,fmt.format(v),va='center',ha='left',color=INK,fontsize=9)
A=json.load(open(AB/'ablation_summary.json')); R=A['retrieval']
runs=[('BM25 only','R1_bm25_only'),('Dense only','R2_dense_only'),('Hybrid','A_hybrid'),('Hybrid + rewriting','C_rewrite'),('Hybrid + reranker','B_rerank'),('Hybrid + both','D_rerank_rewrite')]
fig,ax=plt.subplots(1,3,figsize=(11,3.3),sharey=True)
for a,k,t in zip(ax,['MRR','nDCG@10','Hit@10'],['MRR','nDCG@10','Hit@10']): panels(a,[r[0] for r in runs],[R[r[1]][k] for r in runs],t,xmax=1.15)
fig.suptitle('Retrieval by configuration (same 100 questions, paired)',x=.01,ha='left',fontweight='bold',color=INK,fontsize=12); fig.tight_layout(rect=(0,0,1,.93)); fig.savefig(F/'fig_q3_retrieval_ablation.png',dpi=200); plt.close()
J=A['judged']; rj=[('A: Hybrid','A_hybrid'),('B: + reranker','B_rerank'),('C: + rewriting','C_rewrite'),('D: + both','D_rerank_rewrite'),('E: both, no citation rules','E_no_grounding_rules')]
fig,ax=plt.subplots(1,3,figsize=(11,3),sharey=True)
panels(ax[0],[r[0] for r in rj],[J[r[1]]['answer_correctness'] for r in rj],'Answer correctness',xmax=1.18); panels(ax[1],[r[0] for r in rj],[J[r[1]]['faithfulness'] for r in rj],'Faithfulness',xmax=1.18); panels(ax[2],[r[0] for r in rj],[A['latency'][r[1]]['answer_p50'] for r in rj],'Median seconds per answer',fmt='{:.0f} s')
fig.suptitle('Answers by configuration (same 100 questions; blank answers score 0: A 2, B 0, C 0, D 5, E 5)',x=.01,ha='left',fontweight='bold',color=INK,fontsize=12); fig.tight_layout(rect=(0,0,1,.92)); fig.savefig(F/'fig_q5_answer_ablation.png',dpi=200); plt.close()
M=json.load(open(D/'q4_eval/final_metrics.json')); T=[('Provision lookup','provision_lookup'),('Case law','case_law'),('Lay language','lay_language'),('Multi-hop','multi_hop')]
fig,ax=plt.subplots(1,3,figsize=(11,2.6),sharey=True)
for a,k,t in zip(ax,['answer_correctness','Hit@10','MRR'],['Answer correctness','Hit@10','MRR']): panels(a,[x[0] for x in T],[M['by_type'][x[1]][k] for x in T],t,xmax=1.18)
fig.suptitle('Results by question type (all 1,000 questions)',x=.01,ha='left',fontweight='bold',color=INK,fontsize=12); fig.tight_layout(rect=(0,0,1,.9)); fig.savefig(F/'fig_q4_by_question_type.png',dpi=200); plt.close()
Pn=[('badr','badr'),('binyao','binyao'),('darien','darien'),('huang','huang'),('sumo','sumo')]
fig,ax=plt.subplots(1,3,figsize=(11,2.8),sharey=True)
for a,k,t in zip(ax,['faithfulness','answer_relevancy','context_precision'],['Faithfulness','Answer relevancy','Context precision']): panels(a,[x[0] for x in Pn],[M['by_person'][x[1]][k] for x in Pn],t,xmax=1.18)
fig.suptitle('RAG metrics by partition (judges differ: Opus for darien, Haiku for the rest)',x=.01,ha='left',fontweight='bold',color=INK,fontsize=12); fig.tight_layout(rect=(0,0,1,.9)); fig.savefig(F/'fig_q4_rag_by_partition.png',dpi=200); plt.close()
# failure causes, recomputed on final data
rows=list(csv.DictReader(open(D/'q4_eval/final_results_1000.csv',encoding='utf-8-sig')))
docs=lambda r:None
import re,sys
causes=collections.defaultdict(lambda:[0,0]); ids=collections.defaultdict(list)
for r in rows:
    c=float(r['answer_correctness'])
    if c>=1: continue
    ix=0 if c==0 else 1
    if r['answer_blank']=='True': b='Blank answer'
    elif r['refused']=='True': b='Declined or said not found'
    elif float(r['Hit@20'])==0: b='Gold section or passage not in sources'
    elif float(r['context_recall'])<1: b='Some gold evidence missing'
    else: b='All gold evidence retrieved, answer short or wrong'
    causes[b][ix]+=1; ids[b].append(r['question_id'])
order=['Blank answer','Declined or said not found','Gold section or passage not in sources','Some gold evidence missing','All gold evidence retrieved, answer short or wrong']
fig,ax=plt.subplots(figsize=(9,3)); y=list(range(len(order)))[::-1]; z=[causes[o][0] for o in order]; p=[causes[o][1] for o in order]
ax.barh(y,z,height=.52,color=S[1],edgecolor=SUR,linewidth=2,label='Scored 0',zorder=3); ax.barh(y,p,left=z,height=.52,color=S[0],edgecolor=SUR,linewidth=2,label='Scored partly correct',zorder=3)
ax.set_yticks(y); ax.set_yticklabels(order); ax.tick_params(length=0); ax.grid(axis='x',color=GRID,lw=.8,zorder=0); ax.set_title(f'Why answers lost marks ({sum(z)+sum(p)} of 1,000 questions)'); m=max(a+b for a,b in zip(z,p))*1.15; ax.set_xlim(0,m)
for yy,a,b in zip(y,z,p): ax.text(a+b+m*.012,yy,f'{a} + {b}' if a and b else f'{a or b}',va='center',color=INK,fontsize=9)
ax.legend(frameon=False,loc='upper center',bbox_to_anchor=(.35,-.1),ncol=2,labelcolor=SEC); fig.tight_layout(); fig.savefig(F/'fig_q4_failure_causes.png',dpi=200); plt.close()
fails={'order':order,'zero':z,'partial':p,'question_ids':{k:v for k,v in ids.items()},'total_not_fully_correct':sum(z)+sum(p),'zero_total':sum(z),'blank_answers_total':sum(r['answer_blank']=='True' for r in rows)}
(D/'q4_eval/failure_causes.json').write_text(json.dumps(fails,indent=1)); print({k:fails[k] for k in('order','zero','partial','total_not_fully_correct','blank_answers_total')})
# five query stage timings
Q=json.load(open(D/'q2_queries/five_queries.json'))['queries']; stages=[('Query analysis','analysis'),('Rewrite wait','rewrite_hyde_extra_wait'),('Hybrid search','retrieval_hybrid_search'),('Rerank','retrieval_rerank'),('Generation','generation')]
labs=['Provision lookup','Lay language','Case law','Multi-hop','Out of scope (refused)']
fig,ax=plt.subplots(figsize=(9.5,3)); y=list(range(5))[::-1]; left=[0]*5
for (n,k),c in zip(stages,S):
    v=[(q['timings_ms'] or {}).get(k,0)/1000 for q in Q]; ax.barh(y,v,left=left,height=.52,color=c,edgecolor=SUR,linewidth=2,label=n,zorder=3); left=[a+b for a,b in zip(left,v)]
ax.set_yticks(y); ax.set_yticklabels(labs); ax.tick_params(length=0); ax.grid(axis='x',color=GRID,lw=.8,zorder=0); ax.set_xlabel('Seconds'); ax.set_title('Where the time goes: five queries, run one at a time'); ax.set_xlim(0,max(left)*1.12)
for yy,q,l in zip(y,Q,left): ax.text(l+max(left)*.012,yy,f"{q['seconds_total']:.1f} s",va='center',color=INK,fontsize=9)
ax.legend(frameon=False,ncol=5,loc='upper center',bbox_to_anchor=(.45,-.2),labelcolor=SEC,fontsize=9); fig.tight_layout(); fig.savefig(F/'fig_q2_five_query_timings.png',dpi=200); plt.close()
# cost
hi=[{'m3_in':.60,'m3_out':2.40,'flash_in':.15,'flash_out':2.40},{'m3_in':.30,'m3_out':1.20,'flash_in':.15,'flash_out':1.20}]
ans=[q for q in Q if any(u['model']=='MiniMax-M3' for u in q['usage'])]
def tok(q,m,k): return sum(u[k] or 0 for u in q['usage'] if u['model']==m)
avg={k:st.mean(tok(q,m,c) for q in ans) for k,m,c in [('m3_in','MiniMax-M3','prompt'),('m3_out','MiniMax-M3','completion'),('flash_in','MiniMax-M3.1-Flash','prompt'),('flash_out','MiniMax-M3.1-Flash','completion')]}
cost=[sum(avg[k]*p[k]/1e6 for k in avg) for p in hi]
perf={'tokens_per_answered_query_mean_of_4':{k:round(v) for k,v in avg.items()},'usd_per_query_low':round(cost[1],4),'usd_per_query_high':round(cost[0],4),'usd_per_1000_queries':[round(cost[1]*1000,2),round(cost[0]*1000,2)],'price_assumptions':{'low':hi[1],'high':hi[0],'note':'Published prices conflict: MiniMax-M3 is listed at $0.30/$1.20 or $0.60/$2.40 per million tokens. MiniMax-M3.1-Flash input is reported at $0.15; no output price was found, so the M3 output price is used as a stand-in. Check platform.minimax.io before quoting. Judging and annotation costs are not included.','sources':['https://developer.puter.com/tutorials/minimax-api-pricing/','https://venturebeat.com/technology/minimax-m3-debuts-eclipsing-gpt-5-5-and-gemini-3-1-pro-on-key-benchmark-performance-for-just-5-10-of-the-cost','https://www.developersdigest.tech/models/minimax-m3']},
'throughput':{'badr_run':{'questions':200,'minutes':21,'questions_per_second':round(200/(21*60),3),'in_flight':8,'workers':2},'huang_rerun':{'questions':200,'minutes':21,'questions_per_second':round(200/(21*60),3),'in_flight':8,'workers':2},'retrieval_only_100_questions_two_runs_minutes':3},
'latency_seconds':{'badr_p50_p90_max':[41.9,71.4,138.4],'all_1000_p50_p90':[M['overall']['latency_p50'],M['overall']['latency_p90']],'five_queries_total':[q['seconds_total'] for q in Q],'five_queries_first_token':[q['seconds_to_first_token'] for q in Q],'five_queries_search_and_rerank':[q['seconds_search_and_rerank_only'] for q in Q]},
'resources':{'worker_rss_gb_each_approx':3.5,'lowest_free_memory_two_workers_pct':41,'index_size_mb':611,'model_load_seconds':json.load(open(D/'q2_queries/five_queries.json'))['config']['model_load_seconds'],'crash':'Six full-profile workers (24 questions in flight) exhausted memory and caused a kernel watchdog panic on a 64 GB M4 Max with about 50 GB already in use; two workers stayed at 41% free or better.'}}
(D/'q4_eval/performance_and_cost.json').write_text(json.dumps(perf,indent=1)); print(perf['tokens_per_answered_query_mean_of_4'],perf['usd_per_query_low'],perf['usd_per_query_high'],perf['usd_per_1000_queries'])

# pipeline diagram
fig,ax=plt.subplots(figsize=(11,3.6)); ax.axis('off'); ax.set_xlim(0,11); ax.set_ylim(0,3.6)
def box(x,y,w,h,t,c='#eef3fb'):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.02,rounding_size=.08',fc=c,ec=S[0],lw=1)); ax.text(x+w/2,y+h/2,t,ha='center',va='center',fontsize=8.6,color=INK)
def arr(a,b): ax.annotate('',xy=b,xytext=a,arrowprops=dict(arrowstyle='->',color=SEC,lw=1))
ax.text(0,3.42,'Offline',fontweight='bold',fontsize=10,color=INK); ax.text(0,1.72,'Online',fontweight='bold',fontsize=10,color=INK)
X=[(0,'512 Acts + 10,000\njudgment passages'),(2.3,'Clean, chunk\n(sections, passages)'),(4.6,'Add structural\ncontext to chunks'),(6.9,'Embed (Qwen3) +\nBM25 term weights'),(9.2,'Embedded Qdrant\n43,160 chunks')]
for x,t in X: box(x,2.55,1.8,.72,t)
for a,b in zip(X,X[1:]): arr((a[0]+1.85,2.91),(b[0]-.05,2.91))
Y=[(0,'Question'),(1.45,'Query analysis\nscope, citations, dates'),(3.25,'Rewrites + HyDE\n(15 s budget)'),(5.05,'Hybrid search\ndense + BM25, RRF'),(6.85,'Filters, then\nrerank top 50'),(8.65,'Authority + recency\nblend, top 20')]
wd=[1.2,1.55,1.55,1.55,1.55,1.75]
for (x,t),w in zip(Y,wd): box(x,.95,w,.72,t)
for i in range(5): arr((Y[i][0]+wd[i]+.04,1.31),(Y[i+1][0]-.04,1.31))
arr((10.1,2.5),(5.85,1.72))
box(6.1,0,2.15,.68,'MiniMax-M3 answer\nwith [CITE:n] markers','#fdf1ea'); box(8.65,0,1.9,.68,'Grounding check,\ncited answer in UI','#fdf1ea'); arr((9.5,.92),(8.3,.5)); arr((8.28,.34),(8.62,.34))
fig.tight_layout(); fig.savefig(F/'fig_pipeline.png',dpi=200); plt.close()
