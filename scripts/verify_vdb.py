"""Check the built index before it is published.

    cd backend
    RERANKER_MODEL=Qwen/Qwen3-Reranker-0.6B python ../scripts/verify_vdb.py

Structural checks (counts, vector shape and norm, ids, self-retrieval) must all
pass, or the script exits 1. Relevance probes run the real retrieval pipeline and
are reported only: they show whether answers look right, they do not prove it.
Writes data/export/vdb/verification.json. Stop the server first: embedded Qdrant
allows one process at a time.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.context import build_context, shutdown_context  # noqa: E402
from app.retrieval import retrieve  # noqa: E402
from app.vectorstore import SG_LAW, USER_DOCS, point_id  # noqa: E402

EXPECTED = {"act_docs": 512, "act_chunks": 33_160, "judgment_docs": 214, "judgment_chunks": 10_000}
DIM = 1024
SELF_SAMPLE = 300
# Qwen3-Embedding runs in bfloat16, so it normalises at that precision and vectors are
# only unit length to within its epsilon. Measured: max deviation 0.003855, and
# renormalising in float32 left the top 10 unchanged on the queries tried.
NORM_TOLERANCE = 2 ** -8

# (question, expected, expected doc_type or None). `expected` is text that must appear
# in a top-10 citation, or "=<citation>" for that exact citation at rank 1, or None.
PROBES = [
    ("s 10 of the Employment Act 1968", "=Employment Act 1968, s 10", "act"),
    ("What does s 10 of the Employment Act 1968 say about notice?", "=Employment Act 1968, s 10", "act"),
    ("s 406 of the Penal Code 1871", "=Penal Code 1871, s 406", "act"),
    ("s 14 of the Constitution of the Republic of Singapore", "=Constitution of the Republic of Singapore, s 14", "act"),
    ("What notice must an employer give to terminate a contract of service?", "Employment Act", "act"),
    ("What is the punishment for criminal breach of trust?", "Penal Code", "act"),
    ("How must an organisation obtain consent before collecting personal data?", "Personal Data Protection Act", "act"),
    ("Must a company director act honestly in the discharge of their duties?", "Companies Act", "act"),
    ("What is the penalty for driving under the influence of alcohol?", "Road Traffic Act", "act"),
    ("Which provision protects freedom of speech and expression?", "Constitution", "act"),
    ("What is the two-stage test for a duty of care in negligence in Singapore?", None, "judgment"),
    ("What standard of care applies to a doctor giving medical advice to a patient?", None, "judgment"),
    ("Was the auditor liable in negligence to Hin Leong Trading, and how was damages limited?", "[2026] SGCA 33", "judgment"),
    ("Is an occupier liable when a visitor is injured on the premises?", None, "judgment"),
    ("[2026] SGCA 33", "[2026] SGCA 33", "judgment"),
    # Known miss without an LLM: the heuristic parser only recognises "s N of the <Act>",
    # so this form gets no exact lookup. The section is in the index (see the probes above).
    ("Employment Act 1968, s 10", "=Employment Act 1968, s 10", "act"),
]


async def scan(ctx) -> list:
    points, offset = [], None
    while True:
        batch, offset = await ctx.store.client.scroll(
            SG_LAW, limit=1000, offset=offset, with_payload=True, with_vectors=True)
        points += batch
        if offset is None:
            return points


async def main() -> int:
    settings = get_settings()
    ctx = await build_context(settings)
    failures: list[str] = []

    def check(name: str, ok: bool, detail: object = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name} {detail}")
        if not ok:
            failures.append(f"{name} {detail}")

    try:
        points = await scan(ctx)
        chunks = Counter(p.payload["doc_type"] for p in points)
        docs: dict[str, set] = {}
        for p in points:
            docs.setdefault(p.payload["doc_type"], set()).add(p.payload["doc_id"])
        check("act chunks", chunks["act"] == EXPECTED["act_chunks"], chunks["act"])
        check("judgment chunks", chunks["judgment"] == EXPECTED["judgment_chunks"], chunks["judgment"])
        check("no other doc types", set(chunks) == {"act", "judgment"}, dict(chunks))
        check("act documents", len(docs["act"]) == EXPECTED["act_docs"], len(docs["act"]))
        check("judgment documents", len(docs["judgment"]) == EXPECTED["judgment_docs"], len(docs["judgment"]))
        check("user_docs is empty", await ctx.store.count(USER_DOCS) == 0)

        ids = [p.payload["chunk_id"] for p in points]
        check("chunk ids unique", len(set(ids)) == len(ids), f"{len(set(ids))}/{len(ids)}")
        check("point id derives from chunk id", all(str(p.id) == point_id(p.payload["chunk_id"]) for p in points))
        bad_dim = sum(len(p.vector["dense"]) != DIM for p in points)
        norms = [math.sqrt(sum(x * x for x in p.vector["dense"])) for p in points]
        bad_norm = sum(not math.isclose(n, 1.0, abs_tol=NORM_TOLERANCE) for n in norms)  # NaN fails too
        check(f"dense vectors are {DIM}-dim", bad_dim == 0, f"{bad_dim} wrong")
        check("dense vectors are finite and unit norm within bfloat16 precision", bad_norm == 0,
              f"{bad_norm} wrong; norms {min(norms):.6f}..{max(norms):.6f}, tolerance {NORM_TOLERANCE}")
        empty_sparse = sum(not p.vector.get("sparse") or not p.vector["sparse"].indices for p in points)
        check("sparse vectors present", empty_sparse == 0, f"{empty_sparse} empty")
        check("required labels present",
              all(p.payload["citation"] and p.payload["title"] and p.payload["text"]
                  and p.payload["source_url"] and p.payload["hierarchy_path"] for p in points))

        rows = await ctx.db.all_judgments()
        check("judgments registered", len(rows) == EXPECTED["judgment_docs"], len(rows))
        treatments = Counter(r["treatment"] for r in rows)
        cur = await ctx.db.conn.execute("SELECT doc_type, COUNT(*), SUM(chunk_count) FROM corpus_docs GROUP BY doc_type")
        registry = {r[0]: (r[1], r[2]) for r in await cur.fetchall()}
        check("corpus registry matches index", registry == {
            "act": (EXPECTED["act_docs"], EXPECTED["act_chunks"]),
            "judgment": (EXPECTED["judgment_docs"], EXPECTED["judgment_chunks"])}, registry)
        cur = await ctx.db.conn.execute("SELECT kind, COUNT(*) FROM citation_edges GROUP BY kind")
        edges = {r[0]: r[1] for r in await cur.fetchall()}

        # Re-embed stored text: its nearest neighbour must be itself, so vectors
        # really do belong to the payloads stored beside them.
        random.seed(0)
        sample = random.sample(points, SELF_SAMPLE)
        texts = [f"{p.payload['context']}\n\n{p.payload['text']}".strip() for p in sample]
        vecs = await ctx.registry.embed_docs(texts)
        misses = []
        for p, v in zip(sample, vecs):
            hit = (await ctx.store.search_dense(SG_LAW, v, 1))[0]
            if hit.payload["chunk_id"] != p.payload["chunk_id"] and hit.payload["text"] != p.payload["text"]:
                misses.append(p.payload["chunk_id"])
        check(f"self-retrieval on {SELF_SAMPLE} samples", not misses, misses[:5])

        probes = []
        for q, want, want_type in PROBES:
            res = await retrieve(ctx, q)
            top = [c.payload for c in res.chunks[:10]]
            citations = [p.citation for p in top]
            if want and want.startswith("="):
                found = bool(citations) and citations[0] == want[1:]
            else:
                found = not want or any(want in c for c in citations)
            ok = found and (not want_type or any(p.doc_type == want_type for p in top))
            probes.append({"question": q, "expected": want or want_type, "ok": ok,
                           "low_confidence": res.low_confidence, "top": citations[:5]})
            print(f"{'ok  ' if ok else 'MISS'}  {q}\n        → {citations[:3]}")

        report = {
            "structural_failures": failures,
            "chunks": dict(chunks),
            "documents": {k: len(v) for k, v in docs.items()},
            "judgment_treatment": dict(treatments),
            "citation_edges": edges,
            "dense_norm_range": [min(norms), max(norms)],
            "self_retrieval": {"sample": SELF_SAMPLE, "misses": len(misses)},
            "probes_ok": sum(p["ok"] for p in probes),
            "probes_total": len(probes),
            "probes": probes,
            "embedder_device": str(ctx.registry.embedder.model.device),
            "reranker": ctx.registry.reranker_name_active,
        }
        out = settings.data_dir / "export" / "vdb"
        out.mkdir(parents=True, exist_ok=True)
        (out / "verification.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n{len(failures)} structural failures; probes {report['probes_ok']}/{report['probes_total']}")
    finally:
        await shutdown_context(ctx)
    return 1 if failures else 0


if __name__ == "__main__":
    code = asyncio.run(main())
    sys.stdout.flush()
    os._exit(code)  # torch/tokenizer threads can outlive the loop (see app.crawler)
