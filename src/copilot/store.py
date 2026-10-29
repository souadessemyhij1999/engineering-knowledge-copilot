"""Qdrant vector store: one collection with a named dense vector and a named
sparse BM25 vector per chunk. Access control and revision filtering are
Qdrant payload filters, applied inside every prefetch, so a chunk the user is
not allowed to see never leaves the database."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

DENSE, SPARSE = "dense", "bm25"


@dataclass
class StoreHit:
    id: str
    score: float
    payload: dict


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class VectorStore:
    def __init__(self, url: str = "", path: str = ":memory:", collection: str = "engineering_docs", dim: int = 256):
        if url:
            self.client = QdrantClient(url=url, timeout=30)
        elif path == ":memory:":
            self.client = QdrantClient(location=":memory:")
        else:
            self.client = QdrantClient(path=path)
        self.collection, self.dim, self.remote = collection, dim, bool(url)
        self.ensure_collection()

    def ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            self.collection,
            vectors_config={DENSE: models.VectorParams(size=self.dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        if self.remote:  # embedded mode has no payload indexes
            for field, schema in (("roles", "keyword"), ("doc_no", "keyword"), ("is_current", "bool")):
                self.client.create_payload_index(self.collection, field, field_schema=schema)

    def reset(self) -> None:
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.ensure_collection()

    def upsert(self, payloads: list[dict], dense, sparse: list[tuple[list[int], list[float]]]) -> None:
        points = [
            models.PointStruct(
                id=_point_id(p["chunk_id"]),
                vector={DENSE: d.tolist(), SPARSE: models.SparseVector(indices=s[0], values=s[1])},
                payload=p,
            )
            for p, d, s in zip(payloads, dense, sparse)
        ]
        for i in range(0, len(points), 128):
            self.client.upsert(self.collection, points=points[i:i + 128], wait=True)

    def delete_document(self, doc_no: str, revision: str | None = None) -> None:
        must = [models.FieldCondition(key="doc_no", match=models.MatchValue(value=doc_no))]
        if revision is not None:
            must.append(models.FieldCondition(key="revision", match=models.MatchValue(value=revision)))
        self.client.delete(self.collection, points_selector=models.FilterSelector(filter=models.Filter(must=must)))

    def set_current(self, doc_no: str, current_revision: str) -> None:
        """Mark one revision of a document as current, all others as not."""
        base = models.FieldCondition(key="doc_no", match=models.MatchValue(value=doc_no))
        rev = models.FieldCondition(key="revision", match=models.MatchValue(value=current_revision))
        self.client.set_payload(self.collection, {"is_current": False},
                                points=models.Filter(must=[base], must_not=[rev]))
        self.client.set_payload(self.collection, {"is_current": True},
                                points=models.Filter(must=[base, rev]))

    @staticmethod
    def build_filter(roles: list[str] | None, current_only: bool, doc_nos: list[str] | None = None):
        must = []
        if roles is not None:          # None = superuser, no role filter
            must.append(models.FieldCondition(key="roles", match=models.MatchAny(any=roles or ["__none__"])))
        if current_only:
            must.append(models.FieldCondition(key="is_current", match=models.MatchValue(value=True)))
        if doc_nos:
            must.append(models.FieldCondition(key="doc_no", match=models.MatchAny(any=doc_nos)))
        return models.Filter(must=must) if must else None

    def search(self, dense_q, sparse_q: tuple[list[int], list[float]] | None, *, roles: list[str] | None,
               current_only: bool = True, mode: str = "hybrid", candidates: int = 30, limit: int = 30,
               doc_nos: list[str] | None = None) -> list[StoreHit]:
        flt = self.build_filter(roles, current_only, doc_nos)
        sparse_vec = models.SparseVector(indices=sparse_q[0], values=sparse_q[1]) if sparse_q and sparse_q[0] else None
        if mode == "dense" or (mode == "hybrid" and sparse_vec is None):
            res = self.client.query_points(self.collection, query=dense_q.tolist(), using=DENSE,
                                           query_filter=flt, limit=limit, with_payload=True)
        elif mode == "sparse":
            if sparse_vec is None:
                return []
            res = self.client.query_points(self.collection, query=sparse_vec, using=SPARSE,
                                           query_filter=flt, limit=limit, with_payload=True)
        else:
            res = self.client.query_points(
                self.collection,
                prefetch=[
                    models.Prefetch(query=dense_q.tolist(), using=DENSE, limit=candidates, filter=flt),
                    models.Prefetch(query=sparse_vec, using=SPARSE, limit=candidates, filter=flt),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF), limit=limit, with_payload=True,
            )
        return [StoreHit(id=str(p.id), score=float(p.score), payload=p.payload) for p in res.points]

    def scroll_all(self, roles: list[str] | None = None, current_only: bool = False) -> list[dict]:
        flt = self.build_filter(roles, current_only)
        out, offset = [], None
        while True:
            pts, offset = self.client.scroll(self.collection, scroll_filter=flt, limit=256, offset=offset,
                                             with_payload=True, with_vectors=False)
            out.extend(p.payload for p in pts)
            if offset is None:
                return out

    def count(self) -> int:
        return self.client.count(self.collection).count
