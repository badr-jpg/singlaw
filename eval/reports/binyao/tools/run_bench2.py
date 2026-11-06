"""Run SingLaw on a benchmark CSV and record ranked sources + answers for judging.

usage (from backend/, server stopped):
  uv run python -X utf8 <this> <repo_root> binyao <tag> <concurrency> [limit]
Writes data/export/benchmark/<name>_run.jsonl (resumable: done ids are skipped).

Gold matching against the published index (badlaldh/singlaw-vdb):
  Act      gold doc  'road-traffic-act-1961' + citation 's 65B'
           -> doc match: chunk doc_id == act slug; exact match: chunk_id 'road-traffic-act-1961:s65B[.k]'
  Judgment gold doc  '2014_SGHC_271-0012' (HF passage id, part 12)
           -> case match: chunk doc_id == case slug; exact match: chunk_id '<case slug>:part12'
"""
from __future__ import annotations
import asyncio, csv, json, re, sqlite3, sys, time
from pathlib import Path

repo = Path(sys.argv[1]).resolve(); name = sys.argv[2]
tag = sys.argv[3]                      # output suffix, e.g. "minimax"
conc = int(sys.argv[4])                # questions in flight at once
limit = int(sys.argv[5]) if len(sys.argv) > 5 else None
sys.path.insert(0, str(repo / "backend"))

from app.answer import chat_stream  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.context import build_context, shutdown_context  # noqa: E402
from app.vectorstore import SG_LAW  # noqa: E402

bench = repo / "data" / "export" / "benchmark"
rows = list(csv.DictReader(open(bench / f"{name}.csv", encoding="utf-8")))
out_path = bench / f"{name}_run_{tag}.jsonl"
done = set()
if out_path.exists():
    done = {json.loads(l)["question_id"] for l in out_path.read_text(encoding="utf-8").splitlines() if l.strip()}

db = sqlite3.connect(repo / "data" / "db" / "app.sqlite3")
slug_by_cite = dict(db.execute("select citation, doc_id from judgments"))


def gold_targets(r: dict) -> list[dict]:
    out = []
    for g, c in zip(r["gold_doc_ids"].split("|"), r["gold_citations"].split("|")):
        m = re.match(r"(\d{4})_(SG[A-Z]+)_(\d+)-(\d+)$", g)
        if m:  # judgment passage
            y, court, num, part = m.groups()
            court = court.replace("SGHCA", "SGHC(A)")
            slug = slug_by_cite.get(f"[{y}] {court} {num}")
            out.append({"gold": g, "doc": slug, "exact": [f"{slug}:part{int(part)}"], "kind": "judgment"})
        else:  # Act; sections from 's 65B', 'ss 57-58', 'ss 10, 16'
            secs = re.sub(r"^.*?,\s*ss?\s+", "", c)
            nums = []
            for piece in re.split(r",\s*", secs):
                a, _, b = piece.partition("-")
                if b and a.isdigit() and b.isdigit():
                    nums += [str(n) for n in range(int(a), int(b) + 1)]
                else:
                    nums.append(a.strip())
            out.append({"gold": g, "doc": g, "exact": [f"{g}:s{n}" for n in nums], "kind": "act"})
    return out


def first_rank(pred, items) -> int | None:
    for i, x in enumerate(items, 1):
        if pred(x):
            return i
    return None


async def one(ctx, r: dict) -> dict:
    q = r["question"]; targets = gold_targets(r)
    t0 = time.time()
    text, sources, meta, err, ev = "", [], {}, None, None
    async for frame in chat_stream(ctx, q, None, None):
        for line in frame.strip().split("\n"):
            if line.startswith("event: "):
                ev = line[7:].strip()
            elif line.startswith("data: "):
                d = json.loads(line[6:])
                if ev == "error":
                    err = d
                elif "text" in d and ev != "meta":
                    text += d["text"]
                elif "sources" in d:
                    sources = d["sources"]
                if ev in ("meta", "done") and isinstance(d, dict):
                    for k in ("intent", "low_confidence", "low_confidence_reasons", "validation", "timings_ms"):
                        if k in d:
                            meta[k] = d[k]
    cids = [s.get("chunk_id", "") for s in sources]
    docs = [c.split(":", 1)[0] for c in cids]
    rank_exact = [first_rank(lambda c, t=t: any(c == e or c.startswith(e + ".") for e in t["exact"]), cids) for t in targets]
    rank_doc = [first_rank(lambda d, t=t: d == t["doc"], docs) for t in targets]
    return {
        "question_id": r["question_id"], "question_type": r["question_type"], "source_type": r["source_type"],
        "gold": targets, "rank_exact": rank_exact, "rank_doc": rank_doc,
        "sources": [{"n": s.get("n"), "chunk_id": s.get("chunk_id"), "citation": s.get("citation")} for s in sources],
        "answer": text, "meta": meta, "error": err, "t_total": round(time.time() - t0, 1),
    }


async def main():
    s = get_settings()
    ctx = await build_context(s)
    try:
        n = await ctx.store.count(SG_LAW)
        print(f"profile={s.model_profile} reranker={s.reranker_model_resolved} llm={ctx.llm.configured} "
              f"model={s.llm_model}/{s.llm_fast_model} conc={conc} chunks={n}", flush=True)
        todo = [r for r in rows if r["question_id"] not in done][:limit]
        sem = asyncio.Semaphore(conc)
        lock = asyncio.Lock()
        fh = open(out_path, "a", encoding="utf-8")
        count = 0

        async def worker(r):
            nonlocal count
            async with sem:
                o = None
                for attempt in range(3):  # retry on LLM errors (rate limits etc.)
                    try:
                        o = await one(ctx, r)
                        if not o.get("error"):
                            break
                    except Exception as e:
                        o = {"question_id": r["question_id"], "error": repr(e)}
                    await asyncio.sleep(10 * (attempt + 1))
            async with lock:
                count += 1
                fh.write(json.dumps(o, ensure_ascii=False) + "\n"); fh.flush()
                tm = (o.get("meta") or {}).get("timings_ms") or {}
                print(f"{count}/{len(todo)} {r['question_id']} exact={o.get('rank_exact')} doc={o.get('rank_doc')} "
                      f"n_src={len(o.get('sources', []))} t={o.get('t_total')}s "
                      f"ana={tm.get('analysis')} gen={tm.get('generation')} err={bool(o.get('error'))}", flush=True)

        await asyncio.gather(*(worker(r) for r in todo))
        fh.close()
    finally:
        await shutdown_context(ctx)

asyncio.run(main())
