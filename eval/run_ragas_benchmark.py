"""Run a labelled benchmark (data/export/benchmark/<name>.csv) through SingLaw.

    cd backend && uv run python ../eval/run_ragas_benchmark.py darien

For every question this calls the same retrieval and answer pipeline that
/api/search and /api/chat use, in process, and records:
  - the top-K retrieved chunk ids and the latency of retrieval and answering
  - the generated answer and the sources it was given
  - retrieval metrics against the gold documents: P@K, R@K, Hit@K, MRR, nDCG@10
  - context recall: the share of gold evidence quotes found in the sources

Gold units: an Act question's gold is the cited section(s) (a split section's
chunks "...:s10", "...:s10.1" all count as s 10); a judgment question's gold
is the exact passage chunk. A lenient "act-level" hit is also reported.

Writes eval/results/<name>_results.jsonl (one line per question, resumable)
and eval/results/<name>_retrieval.json. Score the answers afterwards with
eval/judge_claude.py.

Needs the published index (`make index`) and data/export/chunks.jsonl.
Stop `make dev` first: embedded Qdrant allows one process at a time.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

KS = (1, 3, 5, 10, 20)


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def load_export(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """chunk_id -> text, and benchmark passage id (2003_SGHC_134-0001) -> chunk_id."""
    texts, passage = {}, {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            texts[r["chunk_id"]] = r.get("text", "")
            if r.get("doc_type") == "judgment" and ":part" in r["chunk_id"]:
                gd = r.get("source_url", "").rstrip("/").rsplit("/", 1)[-1]
                part = int(r["chunk_id"].rsplit(":part", 1)[1])
                passage[f"{gd}-{part:04d}"] = r["chunk_id"]
    return texts, passage


def unit_of(chunk_id: str) -> str:
    """Retrieval unit: an Act section (sub-chunks merged) or a judgment passage."""
    m = re.match(r"^(.*?:s[0-9A-Za-z]+?)(?:\.\d+)?$", chunk_id)
    return m.group(1) if m and ":part" not in chunk_id else chunk_id


def gold_units(row: dict, acts: set[str], passage: dict[str, str]) -> tuple[set[str], set[str]]:
    """(gold units, gold Acts) for a benchmark row."""
    units, gold_acts = set(), set()
    for doc, cite in zip(row["gold_doc_ids"].split("|"), row["gold_citations"].split("|")):
        if doc in acts:
            gold_acts.add(doc)
            loc = cite.rsplit(", s", 1)[-1].lstrip("s ").strip()
            for num in re.findall(r"[0-9]+[A-Z]*", loc):
                units.add(f"{doc}:s{num}")
        elif doc in passage:
            units.add(passage[doc])
        else:
            units.add(f"MISSING:{doc}")
    return units, gold_acts


def retrieval_metrics(ranked_units: list[str], gold: set[str]) -> dict:
    out: dict = {}
    for k in KS:
        top = ranked_units[:k]
        hits = len(gold & set(top))
        out[f"P@{k}"] = hits / k
        out[f"R@{k}"] = hits / len(gold) if gold else 0.0
        out[f"Hit@{k}"] = float(hits > 0)
    rr = 0.0
    for i, u in enumerate(ranked_units, start=1):
        if u in gold:
            rr = 1.0 / i
            break
    out["MRR"] = rr
    dcg = sum(1 / math.log2(i + 1) for i, u in enumerate(ranked_units[:10], start=1) if u in gold)
    idcg = sum(1 / math.log2(i + 1) for i in range(1, min(len(gold), 10) + 1))
    out["nDCG@10"] = dcg / idcg if idcg else 0.0
    return out


def summarise(results: list[dict]) -> dict:
    keys = [k for k in results[0]["metrics"]] if results else []

    def avg(rs: list[dict]) -> dict:
        s = {k: round(sum(r["metrics"][k] for r in rs) / len(rs), 4) for k in keys}
        lat = [r["latency_retrieve_s"] for r in rs]
        s["n"] = len(rs)
        s["latency_retrieve_p50_s"] = round(sorted(lat)[len(lat) // 2], 3)
        ans = [r["latency_answer_s"] for r in rs if r.get("latency_answer_s") is not None]
        if ans:
            s["latency_answer_p50_s"] = round(sorted(ans)[len(ans) // 2], 3)
        cr = [r["context_recall"] for r in rs if r.get("context_recall") is not None]
        if cr:
            s["context_recall"] = round(sum(cr) / len(cr), 4)
        return s

    by: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by[f"type={r['question_type']}"].append(r)
        by[f"source={r['source_type']}"].append(r)
    return {"overall": avg(results), **{k: avg(v) for k, v in sorted(by.items())}}


async def answer(ctx, question: str) -> tuple[str, list[dict], dict, float]:
    """Run the /api/chat pipeline; returns text, sources, done event, seconds to sources."""
    from app.answer import chat_stream
    text, sources, done, t_src = "", [], {}, 0.0
    t0 = time.perf_counter()
    async for frame in chat_stream(ctx, question, None, None):
        event, data = "", None
        for line in frame.strip().split("\n"):
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if data is None:
            continue
        if event == "token" or (not event and "text" in data):
            text += data.get("text", "")
        elif event == "sources":
            sources = data.get("sources", [])
            t_src = time.perf_counter() - t0
        elif event == "done":
            done = data
    return text, sources, done, t_src


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--csv", help="default: data/export/benchmark/<name>.csv")
    ap.add_argument("--chunks", default=str(ROOT / "data" / "export" / "chunks.jsonl"))
    ap.add_argument("--top-k", type=int, default=20)
    ap.add_argument("--limit", type=int, help="only the first N questions (smoke test)")
    ap.add_argument("--no-answer", action="store_true", help="retrieval metrics only")
    ap.add_argument("--fresh", action="store_true", help="discard earlier results and rerun all")
    ap.add_argument("--tag", help="name this run, e.g. minilm: writes <name>_<tag>_results.jsonl")
    ap.add_argument("--only", help="comma-separated question ids to (re)run, e.g. darien-023,darien-058. "
                    "Without --tag their records in the main results are replaced; with --tag they "
                    "go to the tagged file only")
    ap.add_argument("--no-llm-cache", action="store_true",
                    help="clear the cached LLM analysis/rewrites/HyDE for the questions being run, "
                         "so they are regenerated instead of reused")
    a = ap.parse_args()

    from app.config import get_settings
    from app.context import build_context, shutdown_context
    from app.retrieval import analyze_query, retrieve

    csv_path = Path(a.csv or ROOT / "data" / "export" / "benchmark" / f"{a.name}.csv")
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8", newline="")))[: a.limit]
    only = {q.strip() for q in a.only.split(",") if q.strip()} if a.only else None
    if only:
        unknown = only - {r["question_id"] for r in rows}
        if unknown:
            sys.exit(f"unknown question ids: {sorted(unknown)}")
    merge = bool(only) and not a.tag   # rewrite the main file with the rerun records swapped in
    if merge and a.fresh:
        sys.exit("--only without --tag replaces records in the main results; do not combine it with --fresh")
    part = json.loads((ROOT / "eval" / "benchmark_partition" / "partition.json").read_text())
    acts = {x["doc_id"] for x in part["people"][a.name]["acts"]}
    texts, passage = load_export(Path(a.chunks))

    out_dir = ROOT / "eval" / "results"
    out_dir.mkdir(exist_ok=True)
    stem = f"{a.name}_{a.tag}" if a.tag else a.name
    out_path = out_dir / f"{stem}_results.jsonl"
    done_ids: dict[str, dict] = {}
    if out_path.exists() and not a.fresh:
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                done_ids[r["question_id"]] = r

    pending = set(only) if only else set()   # selected questions are always rerun;
    # their old records stay in place until the new ones replace them
    to_run = [r for r in rows if (not only or r["question_id"] in only)]

    settings = get_settings()
    ctx = await build_context(settings)
    if a.no_llm_cache:
        import hashlib
        keys = []
        for r in to_run:
            norm = " ".join(r["question"].lower().split())
            for kind in ("analysis", "rewrites", "hyde"):
                keys.append(("llmcache:" + hashlib.sha256(
                    f"{kind}|{settings.llm_fast_model}|{norm}".encode()).hexdigest(),))
        async with ctx.db._write() as c:
            await c.executemany("DELETE FROM kv WHERE key=?", keys)
        print(f"cleared cached LLM helper results for {len(to_run)} question(s)")
    await ctx.registry.load()
    run_cfg = {"profile": settings.model_profile, "top_k": a.top_k,
               "llm_configured": ctx.llm.configured,
               "reranker": ctx.registry.reranker_name_active,
               "fusion_top": settings.fusion_top, "rerank_top": settings.rerank_top}
    print(f"profile={settings.model_profile} llm={'on' if ctx.llm.configured else 'OFF (extractive)'} "
          f"reranker={run_cfg['reranker']} fusion_top={settings.fusion_top} "
          f"questions={len(to_run)} already done={len(done_ids) if not only else 0}"
          + (" (replacing in main results)" if merge else ""))
    try:
        with open(out_path, "w" if (a.fresh and not merge) else "a", encoding="utf-8") as fout:
            for i, row in enumerate(to_run, start=1):
                qid = row["question_id"]
                if qid in done_ids and qid not in pending:
                    continue
                gold, gold_acts = gold_units(row, acts, passage)
                if a.no_answer:
                    t0 = time.perf_counter()
                    analysis = await analyze_query(ctx, row["question"])
                    res = await retrieve(ctx, row["question"], top_k=a.top_k, analysis=analysis)
                    t_ret = time.perf_counter() - t0
                    chunk_ids = [c.payload.chunk_id for c in res.chunks[: a.top_k]]
                    low_conf = res.low_confidence
                else:
                    # the chat pipeline retrieves once; its sources are the ranked top 20
                    t1 = time.perf_counter()
                    text, sources, done, t_ret = await answer(ctx, row["question"])
                    t_ans = time.perf_counter() - t1
                    chunk_ids = [s.get("chunk_id") for s in sources
                                 if s.get("collection", "sg_law") == "sg_law"][: a.top_k]
                    low_conf = None
                ranked: list[str] = []
                for c in chunk_ids:
                    u = unit_of(c)
                    if u not in ranked:
                        ranked.append(u)
                m = retrieval_metrics(ranked, gold)
                act_hits = {c.split(":", 1)[0] for c in chunk_ids[:10]} & gold_acts
                m["ActHit@10"] = float(bool(act_hits)) if gold_acts else float(m["Hit@10"])

                rec = {k: row[k] for k in ("question_id", "question", "answer", "question_type",
                                           "source_type", "gold_doc_ids", "gold_citations",
                                           "evidence_quote")}
                rec.update(gold_units=sorted(gold), retrieved=chunk_ids, metrics=m,
                           latency_retrieve_s=round(t_ret, 3),
                           low_confidence=low_conf)
                if not a.no_answer:
                    rec["latency_answer_s"] = round(t_ans, 3)
                    rec["generated_answer"] = text
                    rec["sources"] = [{"n": s.get("n"), "chunk_id": s.get("chunk_id"),
                                       "citation": s.get("citation"),
                                       "text": texts.get(s.get("chunk_id"), s.get("snippet", ""))[:2500]}
                                      for s in sources]
                    rec["done"] = {k: v for k, v in done.items() if k != "message_id"}
                    ctx_all = squash(" ".join(s["text"] for s in rec["sources"]))
                    quotes = row["evidence_quote"].split("|")
                    rec["context_recall"] = sum(squash(q) in ctx_all for q in quotes) / len(quotes)
                done_ids[qid] = rec
                pending.discard(qid)
                if merge:
                    # rewrite the whole file in benchmark order with this record swapped in
                    tmp = out_path.with_suffix(".tmp")
                    with open(tmp, "w", encoding="utf-8") as ft:
                        for r0 in rows:
                            if r0["question_id"] in done_ids:
                                ft.write(json.dumps(done_ids[r0["question_id"]], ensure_ascii=False) + "\n")
                    tmp.replace(out_path)
                else:
                    fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fout.flush()
                print(f"  {qid} [{row['question_type']:<16}] Hit@10={m['Hit@10']:.0f} "
                      f"MRR={m['MRR']:.2f} ret={t_ret:.1f}s"
                      + (f" ans={rec['latency_answer_s']:.1f}s cr={rec['context_recall']:.2f}"
                         if not a.no_answer else ""))
    finally:
        await shutdown_context(ctx)

    results = [done_ids[r["question_id"]] for r in rows if r["question_id"] in done_ids]
    summary = summarise(results)
    summary["config"] = run_cfg
    (out_dir / f"{stem}_retrieval.json").write_text(json.dumps(summary, indent=2))
    print("\n=========== retrieval summary ===========")
    cols = ["n", "P@5", "R@5", "R@10", "R@20", "Hit@10", "MRR", "nDCG@10", "ActHit@10",
            "context_recall", "latency_retrieve_p50_s"]
    print(f"{'':<26}" + "".join(f"{c[:13]:>14}" for c in cols))
    for k, s in summary.items():
        if k == "config":
            continue
        print(f"{k:<26}" + "".join(f"{s.get(c, float('nan')):>14.3f}" if c != "n"
                                   else f"{s['n']:>14d}" for c in cols))
    print(f"\nwrote {out_path} and {out_dir / (stem + '_retrieval.json')}")


if __name__ == "__main__":
    asyncio.run(main())
