"""向量存储抽象层（Milvus 后端）。

职责边界：
  - 只负责 "embedding -> chunk_id" 的相似度检索与持久化；
  - chunk 正文、元数据与权限过滤仍由 MySQL（AgentKnowledgeChunk）承担，
    因此向量库只存 id 与向量，不存正文，避免双写不一致。

配置（.env）：
  AGENT_VECTOR_STORE      auto（默认，检测到 milvus 即启用）| milvus | none
  AGENT_MILVUS_URI        Milvus 服务地址，如 http://127.0.0.1:19530（必填）
  AGENT_MILVUS_TOKEN      Milvus 认证 token（可选；开启认证或 Zilliz Cloud 时填写）
  AGENT_MILVUS_COLLECTION 向量集合名，默认 oa_knowledge_chunks

一致性策略：
  - 入库/删除 chunk 时增量同步向量库（upsert / delete）；
  - 数据由 Milvus 服务端持久化（etcd + MinIO），进程重启后自动可用；
  - 检索时以 MySQL 为主数据源做 id 与权限过滤，向量库只负责候选排序，
    索引与 MySQL 短暂不一致时最多损失召回，不会返回越权内容。
"""
from __future__ import annotations

import logging
import threading

from .env import env_strip
from .exceptions import AgentServiceError

logger = logging.getLogger(__name__)

try:
    import numpy as np
    from pymilvus import DataType, MilvusClient

    _MILVUS_AVAILABLE = True
except Exception:  # pragma: no cover
    _MILVUS_AVAILABLE = False
    np = None
    DataType = None
    MilvusClient = None

_DEFAULT_COLLECTION = "oa_knowledge_chunks"


class MilvusVectorStore:
    """基于 Milvus 的持久化向量存储（FLAT 索引 + COSINE 度量）。

    - 度量采用 COSINE，返回的 distance 即余弦相似度，与旧 FAISS
      "L2 归一化后内积" 的分数语义一致；
    - chunk 的 Django 主键作为 Milvus 的 id（INT64），便于与 MySQL 对齐；
    - 集合不存在时自动创建；embedding 维度变化时自动重建（旧向量清空）。
    """

    def __init__(self, uri: str, token: str | None = None, collection_name: str = _DEFAULT_COLLECTION):
        self._uri = uri
        self._token = token
        self._collection_name = collection_name
        self._client: MilvusClient | None = None
        self._dimension: int | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # 连接与集合生命周期
    # ------------------------------------------------------------------

    def _connect(self) -> MilvusClient:
        if self._client is None:
            kwargs = {"uri": self._uri}
            if self._token:
                kwargs["token"] = self._token
            self._client = MilvusClient(**kwargs)
        return self._client

    def _collection_dimension(self) -> int | None:
        client = self._connect()
        if not client.has_collection(self._collection_name):
            return None
        info = client.describe_collection(self._collection_name)
        for field in info.get("fields", []):
            if field.get("name") == "vector":
                return int(field.get("params", {}).get("dim"))
        return None

    def _ensure_collection(self, dimension: int) -> None:
        client = self._connect()
        current = self._collection_dimension()
        if current is not None and current != dimension:
            # embedding 模型切换导致维度变化：旧集合整体失效，重建
            logger.warning("向量维度由 %s 变为 %s，重建 Milvus 集合", current, dimension)
            client.drop_collection(self._collection_name)
            current = None
        if current is not None:
            return
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
        schema.add_field(field_name="vector", datatype=DataType.FLOAT_VECTOR, dim=dimension)
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="vector", index_type="FLAT", metric_type="COSINE")
        # Strong 一致性：写入后立即可检索（默认 Bounded 需 flush 才可见）
        client.create_collection(
            collection_name=self._collection_name,
            schema=schema,
            index_params=index_params,
            consistency_level="Strong",
        )
        self._dimension = dimension
        logger.info("创建 Milvus 集合 %s（维度 %s）", self._collection_name, dimension)

    def _flush(self) -> None:
        """flush 落盘，确保写入/删除结果对后续检索立即可见。"""
        try:
            self._connect().flush(self._collection_name)
        except Exception as exc:  # pragma: no cover
            logger.warning("Milvus flush 失败（%s），检索结果可能短暂滞后", exc)

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------

    def upsert(self, ids: list[int], embeddings: list[list[float]]) -> None:
        """写入/追加向量。embedding 模型维度变化时自动重建集合。"""
        if not ids or not embeddings:
            return
        vectors = np.asarray(embeddings, dtype="float32")
        dimension = int(vectors.shape[1])
        with self._lock:
            self._ensure_collection(dimension)
            data = [
                {"id": int(chunk_id), "vector": vector.tolist()}
                for chunk_id, vector in zip(ids, vectors)
            ]
            self._connect().upsert(self._collection_name, data=data)
            self._flush()

    def delete(self, ids: list[int]) -> None:
        """按 chunk id 删除向量。"""
        if not ids:
            return
        with self._lock:
            client = self._connect()
            if not client.has_collection(self._collection_name):
                return
            try:
                client.delete(self._collection_name, ids=list(ids))
                self._flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("Milvus 向量删除失败（%s），后续检索可能包含失效 id", exc)
                raise AgentServiceError(str(exc)) from exc

    def clear(self) -> None:
        """清空向量库（重建空集合）。"""
        with self._lock:
            client = self._connect()
            if client.has_collection(self._collection_name):
                client.drop_collection(self._collection_name)
            self._dimension = None

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def search(self, query_embedding: list[float], top_k: int) -> list[tuple[int, float]]:
        """返回 [(chunk_id, score)]，score 为余弦相似度。"""
        if not query_embedding:
            return []
        client = self._connect()
        if not client.has_collection(self._collection_name):
            return []
        query = np.asarray(query_embedding, dtype="float32").reshape(1, -1)
        try:
            results = client.search(
                collection_name=self._collection_name,
                data=[query[0].tolist()],
                limit=max(1, int(top_k)),
                output_fields=[],
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("Milvus 向量检索失败：%s", exc)
            return []
        hits: list[tuple[int, float]] = []
        for row in results[0] if results else []:
            hits.append((int(row["id"]), float(row["distance"])))
        return hits

    def count(self) -> int:
        """返回集合中的行数统计。

        注意：Milvus 的 row_count 为导入行数统计，delete 后可能短暂滞后
        （search 已排除删除项，count 仅作展示/调试用）。
        """
        client = self._connect()
        if not client.has_collection(self._collection_name):
            return 0
        stats = client.get_collection_stats(self._collection_name)
        return int(stats.get("row_count", 0))


_store = None
_store_lock = threading.Lock()


def get_vector_store():
    """返回全局向量库实例；未启用或不可用时返回 None（调用方回退暴力扫描）。"""
    global _store
    if not _MILVUS_AVAILABLE:
        return None
    mode = env_strip("AGENT_VECTOR_STORE", "auto").lower()
    if mode == "none":
        return None
    with _store_lock:
        if _store is None:
            try:
                uri = env_strip("AGENT_MILVUS_URI", "").strip()
                if not uri:
                    if mode == "milvus":
                        raise AgentServiceError("AGENT_MILVUS_URI 未配置，无法启用 Milvus 向量检索")
                    logger.warning("未配置 AGENT_MILVUS_URI，向量检索回退 MySQL 余弦扫描")
                    return None
                token = env_strip("AGENT_MILVUS_TOKEN", "").strip() or None
                collection = (
                    env_strip("AGENT_MILVUS_COLLECTION", _DEFAULT_COLLECTION).strip() or _DEFAULT_COLLECTION
                )
                store = MilvusVectorStore(uri=uri, token=token, collection_name=collection)
                # 探活：强制建立连接并确认服务可用，失败即回退
                store._connect().get_server_version()
                _store = store
                logger.info("Milvus 向量库已连接：%s（集合 %s）", uri, collection)
            except Exception as exc:  # pragma: no cover
                logger.warning("向量库初始化失败，回退暴力扫描：%s", exc)
                _store = None
    return _store


def reset_vector_store() -> None:
    """重置单例（测试用）。"""
    global _store
    with _store_lock:
        _store = None
