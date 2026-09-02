"""Embedded Qdrant wrapper: two collections, named dense + sparse vectors.

Runs via `AsyncQdrantClient(path=...)` — no server, persists to the project
filesystem. Payload index creation is deliberately skipped: embedded/local
mode filters without indexes (consistent with the prior service).
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import numpy as np
from qdrant_client import AsyncQdrantClient, models

from app.ml import SparseVector
from app.schemas import ChunkPayload

_NS = uuid.UUID("6ba7b812-9dad-11d1-80b4-00c04fd430c8")  # uuid5 namespace

SG_LAW = "sg_law"
USER_DOCS = "user_docs"


def point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_NS, chunk_id))


class VectorStore:
    def __init__(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        self.client = AsyncQdrantClient(path=str(path))

    async def close(self) -> None:
        await self.client.close()

    async def ensure_collections(self, dim: int) -> None:
        for name in (SG_LAW, USER_DOCS):
            if await self.client.collection_exists(name):
                info = await self.client.get_collection(name)
                existing = info.config.params.vectors["dense"].size
                if existing != dim:
                    raise RuntimeError(
                        f"collection '{name}' holds {existing}-dim vectors but the "
                        f"configured embedder produces {dim}-dim. The embedding "
                        "model changed — reindex with `make clean && make seed`.")
                continue
            await self.client.create_collection(
                    collection_name=name,
                    vectors_config={
                        "dense": models.VectorParams(
                            size=dim, distance=models.Distance.COSINE)
                    },
                    sparse_vectors_config={
                        "sparse": models.SparseVectorParams(
                            modifier=models.Modifier.IDF)
                    },
                )

    async def upsert_chunks(
        self,
        collection: str,
        chunks: list[ChunkPayload],
        dense: np.ndarray,
        sparse: list[SparseVector],
    ) -> None:
        points = [
            models.PointStruct(
                id=point_id(c.chunk_id),
                vector={
                    "dense": dense[i].tolist(),
                    "sparse": models.SparseVector(
                        indices=sparse[i][0], values=sparse[i][1]),
                },
                payload=c.qdrant_payload(),
            )
            for i, c in enumerate(chunks)
        ]
        await self.client.upsert(collection_name=collection, points=points)

    async def search_dense(
        self, collection: str, vector: np.ndarray, limit: int,
        flt: models.Filter | None = None,
    ) -> list[models.ScoredPoint]:
        res = await self.client.query_points(
            collection_name=collection, query=vector.tolist(), using="dense",
            limit=limit, query_filter=flt, with_payload=True)
        return res.points

    async def search_sparse(
        self, collection: str, sparse: SparseVector, limit: int,
        flt: models.Filter | None = None,
    ) -> list[models.ScoredPoint]:
        if not sparse[0]:
            return []
        res = await self.client.query_points(
            collection_name=collection,
            query=models.SparseVector(indices=sparse[0], values=sparse[1]),
            using="sparse", limit=limit, query_filter=flt, with_payload=True)
        return res.points

    async def get_chunk(self, chunk_id: str) -> dict[str, Any] | None:
        for coll in (SG_LAW, USER_DOCS):
            recs = await self.client.retrieve(
                collection_name=coll, ids=[point_id(chunk_id)], with_payload=True)
            if recs:
                return recs[0].payload
        return None

    async def scroll_payloads(
        self, collection: str, flt: models.Filter | None, limit: int = 500,
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        offset = None
        while True:
            recs, offset = await self.client.scroll(
                collection_name=collection, scroll_filter=flt,
                limit=min(limit - len(out), 100), offset=offset,
                with_payload=True)
            out.extend(r.payload for r in recs)
            if offset is None or len(out) >= limit:
                return out

    async def by_doc_id(self, collection: str, doc_id: str) -> list[dict[str, Any]]:
        return await self.scroll_payloads(
            collection, self.match("doc_id", doc_id), limit=2000)

    async def by_citation_exact(self, citation: str) -> list[dict[str, Any]]:
        return await self.scroll_payloads(
            SG_LAW, self.match("citation", citation), limit=50)

    async def set_payload_by_doc(
        self, collection: str, doc_id: str, payload: dict[str, Any],
    ) -> None:
        await self.client.set_payload(
            collection_name=collection, payload=payload,
            points=models.FilterSelector(filter=self.match("doc_id", doc_id)))

    async def delete_doc(self, collection: str, doc_id: str) -> None:
        await self.client.delete(
            collection_name=collection,
            points_selector=models.FilterSelector(
                filter=self.match("doc_id", doc_id)))

    async def count(self, collection: str, flt: models.Filter | None = None) -> int:
        return (await self.client.count(
            collection_name=collection, count_filter=flt, exact=True)).count

    @staticmethod
    def match(key: str, value: Any) -> models.Filter:
        return models.Filter(must=[models.FieldCondition(
            key=key, match=models.MatchValue(value=value))])

    @staticmethod
    def match_any(key: str, values: list[Any]) -> models.Filter:
        return models.Filter(must=[models.FieldCondition(
            key=key, match=models.MatchAny(any=values))])
