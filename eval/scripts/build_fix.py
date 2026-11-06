"""Second pass for items whose Act evidence did not show the complete cited section(s)."""
import csv,json,random,re,collections
from pathlib import Path
csv.field_size_limit(10**8)
A=Path('.').resolve(); B=A.parents[1]
sq=lambda s:re.sub(r'\s+','',s or '')
text={};pas={}
for l in open(B/'work/chunks.jsonl',encoding='utf-8'):
    c=json.loads(l); text[c['chunk_id']]=c.get('text') or ''
    if c.get('doc_type')=='judgment' and ':part' in c['chunk_id']:
        gd=(c.get('source_url') or '').rstrip('/').rsplit('/',1)[-1]; pas[f"{gd}-{int(c['chunk_id'].rsplit(':part',1)[1]):04d}"]=c['chunk_id']
by={}
for cid in text: by.setdefault(cid.split(':',1)[0],[]).append(cid)
def unit(cid):
    m=re.match(r'^(.*?:s[0-9A-Za-z]+?)(?:\.\d+)?$',cid); return m.group(1) if m and ':part' not in cid else cid
def order(cid):
    m=re.search(r'\.(\d+)$',cid); return int(m.group(1)) if m else 0
def sections(cite):
    m=re.search(r',\s*(?:ss?|sections?)\.?\s*(.+)$',cite,re.I); loc=re.sub(r'\([^)]*\)','',m.group(1) if m else cite.rsplit(',',1)[-1]); out=[]
    for a,b in re.findall(r'(\d+[A-Z]*)(?:\s*[-–—]\s*(\d+[A-Z]*))?',loc):
        if b and a.isdigit() and b.isdigit(): out+=[str(n) for n in range(int(a),int(b)+1)]
        else: out+=[a]+([b] if b else [])
    return out
def first_shown(d,q):
    for c in by.get(d,[]):
        if sq(q) and sq(q) in sq(text[c]):
            t=text[c]
            if len(t)<=3000: return c,t
            pat=r'\s*'.join(map(re.escape,re.sub(r'\s+','',q))); m=re.search(pat,t)
            return c,(t[max(0,m.start()-1200):max(0,m.start()-1200)+3000] if m else t[:3000])
    return None,''
S=B/'work/combined/src'; rows=[]
for p in ['badr','binyao','darien','huang','sumo']:
    rows+=list(csv.DictReader(open(B/'badr.csv' if p=='badr' else S/p/f'{p}.csv',encoding='utf-8-sig',newline='')))
items=[];why=collections.Counter();missing=[]
for r in rows:
    ev=[];fix=set()
    for d,c,q in zip(r['gold_doc_ids'].split('|'),r['gold_citations'].split('|'),r['evidence_quote'].split('|')):
        if d in pas: ev.append((c,q,text[pas[d]][:6000])); continue
        secs=sections(c); full=[]
        for n in secs:
            parts=sorted([x for x in by.get(d,[]) if unit(x)==f'{d}:s{n}'],key=order)
            if not parts: missing.append((r['question_id'],d,n))
            full.append('\n'.join(text[x] for x in parts))
        whole='\n\n'.join(full)
        cid,shown=first_shown(d,q)
        if cid is None or unit(cid) not in {f'{d}:s{n}' for n in secs}: fix.add('wrong section shown')
        if len(secs)>1: fix.add('only one of several cited sections shown')
        if sq(shown)!=sq(whole) and sq(whole) not in sq(shown): fix.add('cited section cut short or split')
        ev.append((c,q,whole[:9000]))
    if fix:
        for w in fix: why[w]+=1
        items.append({'id':r['question_id'],'q':r['question'],'a':r['answer'],'ev':ev})
print('items to redo',len(items),dict(why),'cited sections missing from index',len(missing),missing[:6])
F=A/'fix'; F.mkdir(exist_ok=True)
man={}; SIZE=40
for ann,seed in [('A',11),('B',22),('C',33)]:
    d=F/ann; (d/'out').mkdir(parents=True,exist_ok=True); x=items[:]; random.Random(seed).shuffle(x)
    bs=[x[i:i+SIZE] for i in range(0,len(x),SIZE)]
    for n,b in enumerate(bs):
        (d/f'batch_{n:02d}.txt').write_text('\n\n'.join('### ITEM '+i['id']+'\nQUESTION: '+i['q']+'\nREFERENCE ANSWER: '+i['a']+'\n'+'\n'.join(f"EVIDENCE [{c}]\nQUOTE: {q}\nSOURCE TEXT: {t}" for c,q,t in i['ev']) for i in b),encoding='utf-8')
    man[ann]={f'{n:02d}':[i['id'] for i in b] for n,b in enumerate(bs)}
(F/'manifest.json').write_text(json.dumps(man)); print({k:len(v) for k,v in man.items()},'largest',max(p.stat().st_size for p in (F/'A').glob('batch_*.txt'))//1024,'KB')
print('by person',collections.Counter(i['id'].split('-')[0] for i in items))
