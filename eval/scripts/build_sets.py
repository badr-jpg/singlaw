"""Build blind annotation batches: 3 annotators, each with own shuffle and batches. No system answers, no judge scores."""
import csv,json,random,re,sys
from pathlib import Path
csv.field_size_limit(10**8)
A=Path(__file__).resolve().parent; B=A.parents[1]; ROOT=B.parents[2]
sys.path.insert(0,str(ROOT/'eval/reports/combined'))
text={};pas={}
for l in open(B/'work/chunks.jsonl',encoding='utf-8'):
    c=json.loads(l); text[c['chunk_id']]=c.get('text') or ''
    if c.get('doc_type')=='judgment' and ':part' in c['chunk_id']:
        gd=(c.get('source_url') or '').rstrip('/').rsplit('/',1)[-1]; pas[f"{gd}-{int(c['chunk_id'].rsplit(':part',1)[1]):04d}"]=c['chunk_id']
by=dict()
for cid in text: by.setdefault(cid.split(':',1)[0],[]).append(cid)
sq=lambda s:re.sub(r'\s+','',s or '')
S=B/'work/combined/src'
def rows(p): return list(csv.DictReader(open(B/'badr.csv' if p=='badr' else S/p/f'{p}.csv',encoding='utf-8-sig',newline='')))
def locate(doc,q):
    """Source text around the evidence quote, from the index chunk that holds it."""
    cands=[pas[doc]] if doc in pas else by.get(doc,[])
    qs=sq(q)
    for c in cands:
        if qs and qs in sq(text[c]):
            t=text[c]
            if len(t)<=3000: return t,True
            # centre on the quote using a whitespace-tolerant search
            pat=r'\s*'.join(map(re.escape,re.sub(r'\s+','',q)))
            m=re.search(pat,t)
            if m:
                a=max(0,m.start()-1200); return t[a:a+3000],True
            return t[:3000],True
    # quote crosses a chunk boundary or sits past the index chunk: the pinned-source validator already confirmed it
    return (text[cands[0]][:1500] if len(cands)==1 else ''),False
items=[];nf=0
for p in ['badr','binyao','darien','huang','sumo']:
    for r in rows(p):
        ev=[]
        for d,c,q in zip(r['gold_doc_ids'].split('|'),r['gold_citations'].split('|'),r['evidence_quote'].split('|')):
            t,found=locate(d,q); nf+=not found
            ev.append({'citation':c,'quote':q,'source_text':t})
        items.append({'id':r['question_id'],'question':r['question'],'reference_answer':r['answer'],'evidence':ev})
print('items',len(items),'quotes without surrounding text',nf,'chars',sum(len(json.dumps(i,ensure_ascii=False)) for i in items))
SIZE=80
man={}
for ann,seed in [('A',101),('B',202),('C',303)]:
    d=A/ann; d.mkdir(exist_ok=True); (d/'out').mkdir(exist_ok=True)
    x=items[:]; random.Random(seed).shuffle(x)
    bs=[x[i:i+SIZE] for i in range(0,len(x),SIZE)]
    for n,b in enumerate(bs):
        (d/f'batch_{n:02d}.txt').write_text('\n\n'.join('### ITEM '+i['id']+'\nQUESTION: '+i['question']+'\nREFERENCE ANSWER: '+i['reference_answer']+'\n'+'\n'.join(f"EVIDENCE [{e['citation']}]\nQUOTE: {e['quote']}\nSOURCE TEXT: {e['source_text'] or '(only the quote is available)'}" for e in i['evidence']) for i in b),encoding='utf-8')
    man[ann]={f'{n:02d}':[i['id'] for i in b] for n,b in enumerate(bs)}
(A/'manifest.json').write_text(json.dumps(man))
print({k:len(v) for k,v in man.items()},max((A/'A').glob('batch_*.txt'),key=lambda p:p.stat().st_size).stat().st_size)
