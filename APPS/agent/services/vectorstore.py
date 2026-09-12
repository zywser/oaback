"""向量存储抽象层（FAISS 后端）。

职责边界：
  - 只负责 "embedding -> chunk_id" 的相似度检索与持久化；
  - chunk 正文、元数据与权限过滤仍由 MySQL（AgentKnowledgeChunk）承担，
    因此向量库只存 id 与向量，不存正文，避免双写不一致。

配置（.env）：
  AGENT_VECTOR_STORE  auto（默认，检测到 faiss 即启用）| faiss | none
  AGENT_VECTOR_DIR    索引持久化目录，默认 <项目根>/var/vector_store

一致性策略：
  - 入库/删除 chunk 时增量同步向量库（add_with_ids / remove_ids）；
  - 索引实时落盘，进程重启后自动加载；
  - 检索时以 MySQL 为主数据源做 id 与权限过滤，向量库只负责候选排序，
    索引与 MySQL 短暂不一致时最多损失召回，不会返回越权内容。
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path

from .env import env_strip
from .exceptions import AgentServiceError

logger = logging.getLogger(__name__)

try:
    import faiss
    import numpy as np

    _FAISS_AVAILABLE = True
except Exception:  # pragma: no cover
    _FAISS_AVAILABLE = False
    faiss = None
    np = None


def _project_root() -> Path:
    # APPS/agent/services/vectorstore.py -> 项目根
    return Path(__file__).resolve().parents[3]


class FaissVectorStore:
    """基于 faiss IndexIDMap2(IndexFlatIP) 的持久化向量索引。

    - 入库前对向量做 L2 归一化，查询时同样归一化，内积即余弦相似度；
    - chunk 的 Django 主键作为 faiss 的 id，便于与 MySQL 对齐；
    - IndexIDMap2 支持 remove_ids，可按 source 批量删除。
    """

    def __init__(self, index_path: str | Path):
        self.index_path = Path(index_path)
        self._index = None
        self._dimension: int | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 索引生命周期
    # ------------------------------------------------------------------

    def _load(self):
        if self.index_path.exists():
            index = faiss.read_index(str(self.index_path))
            self._dimension = index.d
            return index
        return None

    def _create(self, dimension: int):
        return faiss.IndexIDMap2(faiss.IndexFlatIP(dimension))

    def _save(self):
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(self.index_path))

    @property
    def index(self):
        if self._index is None:
            self._index = self._load()
        return self._index

    def count(self) -> int:
        if self.index is None:
            return 0
        return int(self.index.ntotal)

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------

    def upsert(self, ids: list[int], embeddings: list[list[float]]) -> None:
        """写入/追加向量。embedding 模型维度变化时自动重建索引。"""
        if not ids or not embeddings:
            return
        vectors = np.asarray(embeddings, dtype="float32")
        dimension = int(vectors.shape[1])
        with self._lock:
            if self.index is None:
                self._index = self._create(dimension)
                self._dimension = dimension
            elif self._dimension != dimension:
                # embedding 模型切换导致维度变化：旧索引整体失效，重建
                logger.warning("向量维度由 %s 变为 %s，重建向量索引", self._dimension, dimension)
                self._index = self._create(dimension)
                self._dimension = dimension
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / np.maximum(norms, 1e-9)
            id_array = np.asarray(ids, dtype="int64")
            self._index.add_with_ids(vectors, id_array)
            self._save()

    def delete(self, ids: list[int]) -> None:
        """按 chunk id 删除向量。"""
        if not ids or self.index is None:
            return
        with self._lock:
            try:
                self._index.remove_ids(np.asarray(ids, dtype="int64"))
                self._save()
            except Exception as exc:  # pragma: no cover
                logger.warning("向量索引删除失败（%s），后续检索可能包含失效 id", exc)
                raise AgentServiceError(str(exc)) from exc

    def clear(self) -> None:
        with self._lock:
            if self.index is not None:
                self._index.reset()
                self._save()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def search(self, query_embedding: list[float], top_k: int) -> list[tuple[int, float]]:
        """返回 [(chunk_id, score)]，score 为归一化内积（即余弦相似度）。"""
        if self.index is None or not query_embedding:
            return []
        query = np.asarray(query_embedding, dtype="float32").reshape(1, -1)
        if self._dimension is None or query.shape[1] != self._dimension:
            return []
        norm = np.linalg.norm(query)
        if norm > 0:
            query = query / norm
        scores, ids = self._index.search(query, max(1, int(top_k)))
        hits: list[tuple[int, float]] = []
        for chunk_id, score in zip(ids[0], scores[0]):
            if chunk_id == -1:
                continue
            hits.append((int(chunk_id), float(score)))
        return hits


_store = None
_store_lock = threading.Lock()


def get_vector_store():
    """返回全局向量库实例；未启用或不可用时返回 None（调用方回退暴力扫描）。"""
    global _store
    if not _FAISS_AVAILABLE:
        return None
    mode = env_strip("AGENT_VECTOR_STORE", "auto").lower()
    if mode == "none":
        return None
    with _store_lock:
        if _store is None:
            try:
                custom_dir = env_strip("AGENT_VECTOR_DIR", "").strip()
                base_dir = Path(custom_dir) if custom_dir else _project_root() / "var" / "vector_store"
                base_dir.mkdir(parents=True, exist_ok=True)
                _store = FaissVectorStore(base_dir / "faiss.index")
            except Exception as exc:  # pragma: no cover
                logger.warning("向量库初始化失败，回退暴力扫描：%s", exc)
                _store = None
    return _store


def reset_vector_store() -> None:
    """重置单例（测试用）。"""
    global _store
    with _store_lock:
        _store = None
