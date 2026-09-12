"""知识库 RAG：入库、分块索引、检索、问答与反馈。"""
from __future__ import annotations

import hashlib
import logging
import math
from typing import Iterable, Sequence

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from APPS.inform.models import Inform
from APPS.oaauth.models import OADepartment

from ._compat import _LANGCHAIN_AVAILABLE
from .config import get_chat_config, get_embedding_config, get_llm_config
from .env import env_int
from .exceptions import AgentServiceError
from .llm import _legacy_stream_chat_completion, chat_completion, embed_texts
from ..models import (
    AgentConversation,
    AgentConversationRole,
    AgentFeedback,
    AgentKnowledgeChunk,
    AgentKnowledgeSource,
    AgentMessage,
    AgentSourceStatus,
    AgentSourceType,
)
from .permissions import accessible_sources_queryset, is_boarder
from .security import guard_enabled, scan_injection
from .prompts import (
    _langchain_stream_answer,
    build_context_prompt,
    conversation_history_scope,
    document_to_reference,
    invoke_answer,
)
from .text import estimate_tokens, extract_text_from_file, normalize_text, split_text
from .tools import try_tool_call
from .vectorstore import get_vector_store
from .web import search_web, should_use_web_search

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 检索结果与相似度
# ---------------------------------------------------------------------------


def chunk_to_reference(chunk: AgentKnowledgeChunk, score: float) -> dict:

    """
    将知识块转换为引用字典的函数

    参数:
        chunk: AgentKnowledgeChunk对象，包含知识块的详细信息
        score: float类型，表示知识块的匹配分数

    返回:
        dict: 包含知识块及其来源信息的字典，格式化后用于引用展示
    """
    source = chunk.source  # 获取知识块的来源信息
    return {
        "source_id": source.id,  # 来源ID
        "source_type": source.source_type,  # 来源类型
        "title": source.title,  # 来源标题
        "chunk_id": chunk.id,  # 知识块ID
        "chunk_index": chunk.chunk_index,  # 知识块索引
        "score": round(score, 6),  # 匹配分数，保留6位小数
        "excerpt": chunk.content[:1500],  # 知识块内容摘要（截取前1500字符，覆盖完整短块）
        "is_public": source.is_public,  # 是否公开
        "departments": [department.name for department in source.departments.all()],  # 所属部门列表
        "file_url": source.file.url if source.file else "",  # 文件URL，如果有文件
        "author": source.author.realname if source.author_id else "",  # 作者姓名，如果有作者ID
        "created_at": source.created_at.isoformat() if source.created_at else "",  # 创建时间，转换为ISO格式字符串
    }


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = sum(float(left[index]) * float(right[index]) for index in range(size))
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left[:size]))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right[:size]))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


# ---------------------------------------------------------------------------
# 知识库入库与索引
# ---------------------------------------------------------------------------


def ingest_source_text(
    *,
    title: str,
    content: str,
    source_type: str = AgentSourceType.MANUAL,
    author=None,
    departments: Iterable[OADepartment] | None = None,
    is_public: bool = True,
    external_app: str = "",
    external_object_id: str = "",
    file=None,
    metadata: dict | None = None,
) -> AgentKnowledgeSource:
    metadata = dict(metadata or {})
    normalized_content = normalize_text(content)
    summary = metadata.pop("summary", "") or normalized_content[:500]

    with transaction.atomic():
        defaults = {
            "title": title,
            "source_type": source_type,
            "content": normalized_content,
            "summary": summary,
            "author": author,
            "is_public": is_public,
            "metadata": metadata,
            "status": AgentSourceStatus.PENDING,
            "chunk_count": 0,
            "indexed_at": None,
        }
        if external_app and external_object_id not in (None, ""):
            source, _ = AgentKnowledgeSource.objects.update_or_create(
                external_app=external_app or None,
                external_object_id=str(external_object_id) if external_object_id is not None else None,
                defaults=defaults,
            )
        else:
            source = AgentKnowledgeSource.objects.create(
                external_app=None,
                external_object_id=None,
                **defaults,
            )
        if file is not None:
            if source.file:
                source.file.delete(save=False)
            source.file = file
        source.save()
        if departments is not None:
            source.departments.set(list(departments))
        rebuild_source_index(source)
        return source


def rebuild_source_index(source: AgentKnowledgeSource) -> AgentKnowledgeSource:
    text = normalize_text(source.content or "")
    if not text and source.file:
        text = extract_text_from_file(source.file.path)
        source.content = text

    chunks = split_text(text)
    old_chunk_ids = list(AgentKnowledgeChunk.objects.filter(source=source).values_list("id", flat=True))
    if old_chunk_ids:
        _vector_delete(old_chunk_ids)
    AgentKnowledgeChunk.objects.filter(source=source).delete()

    if not chunks:
        source.chunk_count = 0
        source.status = AgentSourceStatus.FAILED
        source.indexed_at = timezone.now()
        source.save(update_fields=["content", "chunk_count", "status", "indexed_at", "updated_at"])
        return source

    try:
        embeddings = embed_texts(chunks, kind="document")
        chunk_rows = []
        for index, chunk_text in enumerate(chunks):
            embedding = embeddings[index] if index < len(embeddings) else []
            chunk_rows.append(
                AgentKnowledgeChunk(
                    source=source,
                    chunk_index=index,
                    content=chunk_text,
                    token_count=estimate_tokens(chunk_text),
                    embedding=embedding,
                    embedding_model=get_embedding_config().model,
                    content_hash=hashlib.sha256(chunk_text.encode("utf-8")).hexdigest(),
                )
            )
        AgentKnowledgeChunk.objects.bulk_create(chunk_rows)
        # 向量库写入以数据库回读为准（部分 MySQL 驱动 bulk_create 不回填自增 id）
        db_chunks = list(AgentKnowledgeChunk.objects.filter(source=source).order_by("chunk_index"))
        _vector_upsert([(db_chunk.id, db_chunk.embedding) for db_chunk in db_chunks])
        source.chunk_count = len(chunk_rows)
        source.status = AgentSourceStatus.INDEXED
        source.indexed_at = timezone.now()
        source.metadata = {**(source.metadata or {}), "index_status": "indexed"}
        source.save(update_fields=["content", "chunk_count", "status", "indexed_at", "metadata", "updated_at"])
        return source
    except AgentServiceError as exc:
        source.chunk_count = 0
        source.status = AgentSourceStatus.FAILED
        source.indexed_at = timezone.now()
        source.metadata = {**(source.metadata or {}), "index_status": "failed", "index_error": str(exc)}
        source.save(update_fields=["content", "chunk_count", "status", "indexed_at", "metadata", "updated_at"])
        return source


def sync_inform_sources() -> list[AgentKnowledgeSource]:
    sources: list[AgentKnowledgeSource] = []
    informs = Inform.objects.select_related("author").prefetch_related("departments").all()
    for inform in informs:
        departments = list(inform.departments.all()) if not inform.public else []
        source = ingest_source_text(
            title=inform.title,
            content=f"{inform.title}\n\n{inform.content}",
            source_type=AgentSourceType.INFORM,
            author=inform.author,
            departments=departments,
            is_public=inform.public,
            external_app="inform",
            external_object_id=str(inform.pk),
            metadata={
                "inform_id": inform.pk,
                "read_count": inform.reads.count(),
            },
        )
        sources.append(source)
    return sources


# ---------------------------------------------------------------------------
# 向量库同步与检索（FAISS，可选；未启用/失败时回退暴力扫描）
# ---------------------------------------------------------------------------


def _vector_store():
    try:
        return get_vector_store()
    except Exception:  # noqa: BLE001
        return None


def _vector_upsert(rows) -> None:
    """将 (chunk_id, embedding) 元组列表写入向量库；失败仅记录，不影响 MySQL。"""
    store = _vector_store()
    if store is None:
        return
    ids = [row[0] for row in rows if row[1]]
    embeddings = [row[1] for row in rows if row[1]]
    if not ids:
        return
    try:
        store.upsert(ids, embeddings)
    except AgentServiceError as exc:
        logger.warning("向量库写入失败：%s", exc)


def _vector_delete(chunk_ids) -> None:
    store = _vector_store()
    if store is None or not chunk_ids:
        return
    try:
        store.delete(list(chunk_ids))
    except AgentServiceError as exc:
        logger.warning("向量库删除失败：%s", exc)


def purge_source_vectors(source) -> None:
    """删除某个知识源的全部向量（供知识源删除时同步调用）。"""
    chunk_ids = list(AgentKnowledgeChunk.objects.filter(source=source).values_list("id", flat=True))
    if chunk_ids:
        _vector_delete(chunk_ids)


def _vector_search_chunks(user, question: str, top_k: int, source_ids=None):
    """向量库检索（带权限过滤）。返回 [(chunk, score)]；未启用/失败返回 None。"""
    if not _LANGCHAIN_AVAILABLE:
        return None
    store = _vector_store()
    if store is None:
        return None
    query_embedding = embed_texts([question], kind="query")[0]
    candidates = store.search(query_embedding, top_k * 3)
    if not candidates:
        return []
    chunk_ids = [chunk_id for chunk_id, _ in candidates]
    queryset = AgentKnowledgeChunk.objects.filter(
        id__in=chunk_ids,
        source__in=accessible_sources_queryset(user),
    )
    if source_ids:
        queryset = queryset.filter(source_id__in=list(source_ids))
    chunk_map = {
        chunk.id: chunk
        for chunk in queryset.select_related("source", "source__author").prefetch_related("source__departments")
    }
    scored = [
        (chunk_map[chunk_id], score)
        for chunk_id, score in candidates
        if chunk_id in chunk_map
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_k]


def _chunk_to_document(chunk: AgentKnowledgeChunk, score: float):
    """chunk -> langchain Document（metadata 与 KnowledgeRetriever 对齐）。"""
    from langchain_core.documents import Document

    source = chunk.source
    return Document(
        page_content=chunk.content,
        metadata={
            "source_id": source.id,
            "source_type": source.source_type,
            "title": source.title,
            "chunk_id": chunk.id,
            "chunk_index": chunk.chunk_index,
            "score": round(score, 6),
            "excerpt": chunk.content[:1500],
            "is_public": source.is_public,
            "departments": [department.name for department in source.departments.all()],
            "file_url": source.file.url if source.file else "",
            "author": source.author.realname if source.author_id else "",
            "created_at": source.created_at.isoformat() if source.created_at else "",
            "url": "",
            "source_origin": "knowledge",
        },
    )


# ---------------------------------------------------------------------------
# legacy 引擎实现（原 services.py）
# ---------------------------------------------------------------------------


def _legacy_retrieve_top_chunks(
    user,
    question: str,
    top_k: int | None = None,
    source_ids: Sequence[int] | None = None,
):
    top_k = top_k or env_int("AGENT_TOP_K", 5)
    queryset = accessible_sources_queryset(user)
    if source_ids:
        queryset = queryset.filter(id__in=list(source_ids))
    chunks = (
        AgentKnowledgeChunk.objects.filter(source__in=queryset)
        .select_related("source", "source__author")
        .prefetch_related("source__departments")
    )
    if not chunks.exists():
        return [], []

    query_embedding = embed_texts([question], kind="query")[0]
    scored: list[tuple[float, AgentKnowledgeChunk]] = []
    for chunk in chunks:
        if not chunk.embedding:
            continue
        score = cosine_similarity(query_embedding, chunk.embedding)
        scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = scored[:top_k]
    references = [chunk_to_reference(chunk, score) for score, chunk in selected]
    return selected, references


def _legacy_ask_question(
    user,
    question: str,
    *,
    conversation: AgentConversation | None = None,
    source_ids: Sequence[int] | None = None,
    top_k: int | None = None,
):
    selected, references = retrieve_top_chunks(user, question, top_k=top_k, source_ids=source_ids)

    if conversation is None:
        conversation = AgentConversation.objects.create(
            user=user,
            title=question[:48],
            provider=get_llm_config().provider,
            model_name=get_llm_config().model,
            question_count=0,
        )

    history = list(conversation.messages.order_by("-created_at")[:6])[::-1]
    if not references:
        answer = "未检索到足够相关的知识库内容，请换个问法，或者先导入对应资料。"
        usage = {}
    else:
        messages = build_context_prompt(question, references, history)
        answer, usage = chat_completion(messages)

    AgentMessage.objects.create(
        conversation=conversation,
        role=AgentConversationRole.USER,
        content=question,
    )
    assistant_message = AgentMessage.objects.create(
        conversation=conversation,
        role=AgentConversationRole.ASSISTANT,
        content=answer,
        citations=references,
        metadata={"usage": usage},
    )

    conversation.question_count = conversation.question_count + 1
    conversation.last_question = question
    conversation.last_answer = answer
    conversation.provider = get_llm_config().provider
    conversation.model_name = get_llm_config().model
    if not conversation.title:
        conversation.title = question[:48]
    conversation.save(update_fields=["title", "provider", "model_name", "question_count", "last_question", "last_answer", "updated_at"])

    return {
        "conversation": conversation,
        "assistant_message": assistant_message,
        "references": references,
        "usage": usage,
    }


def create_feedback(*, conversation: AgentConversation, user, score: int, comment: str = "", message: AgentMessage | None = None):
    return AgentFeedback.objects.create(
        conversation=conversation,
        message=message,
        user=user,
        score=score,
        comment=comment,
    )


# ---------------------------------------------------------------------------
# LangChain 引擎实现（原 langchain_stack.py）
# ---------------------------------------------------------------------------

try:
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
    from pydantic import ConfigDict, Field

    from .llm import DashScopeEmbeddings

    class KnowledgeRetriever(BaseRetriever):
        model_config = ConfigDict(arbitrary_types_allowed=True)

        user_uid: str
        department_id: str | None = None
        is_boarder: bool = False
        source_ids: list[int] = Field(default_factory=list)
        top_k: int = 5
        embedding_model: DashScopeEmbeddings = Field(default_factory=DashScopeEmbeddings, exclude=True)

        def _source_queryset(self):
            queryset = AgentKnowledgeSource.objects.prefetch_related("departments", "chunks")
            if self.is_boarder:
                return queryset

            filters = Q(is_public=True) | Q(author_id=self.user_uid)
            if self.department_id:
                filters |= Q(departments=self.department_id)
            return queryset.filter(filters).distinct()

        def _get_relevant_documents(self, query: str, *, run_manager=None):  # type: ignore[override]
            queryset = self._source_queryset()
            if self.source_ids:
                queryset = queryset.filter(id__in=list(self.source_ids))

            chunks = (
                AgentKnowledgeChunk.objects.filter(source__in=queryset)
                .select_related("source", "source__author")
                .prefetch_related("source__departments")
            )
            if not chunks.exists():
                return []

            query_embedding = self.embedding_model.embed_query(query)
            scored: list[tuple[float, AgentKnowledgeChunk]] = []
            for chunk in chunks:
                if not chunk.embedding:
                    continue
                size = min(len(query_embedding), len(chunk.embedding))
                if not size:
                    continue
                dot = sum(float(query_embedding[index]) * float(chunk.embedding[index]) for index in range(size))
                left_norm = math.sqrt(sum(float(value) * float(value) for value in query_embedding[:size]))
                right_norm = math.sqrt(sum(float(value) * float(value) for value in chunk.embedding[:size]))
                if not left_norm or not right_norm:
                    continue
                score = dot / (left_norm * right_norm)
                scored.append((score, chunk))

            scored.sort(key=lambda item: item[0], reverse=True)
            selected = scored[: self.top_k]

            documents: list[Document] = []
            for score, chunk in selected:
                source = chunk.source
                documents.append(
                    Document(
                        page_content=chunk.content,
                        metadata={
                            "source_id": source.id,
                            "source_type": source.source_type,
                            "title": source.title,
                            "chunk_id": chunk.id,
                            "chunk_index": chunk.chunk_index,
                            "score": round(score, 6),
                            "excerpt": chunk.content[:1500],
                            "is_public": source.is_public,
                            "departments": [department.name for department in source.departments.all()],
                            "file_url": source.file.url if source.file else "",
                            "author": source.author.realname if source.author_id else "",
                            "created_at": source.created_at.isoformat() if source.created_at else "",
                            "url": "",
                            "source_origin": "knowledge",
                        },
                    )
                )
            return documents

except Exception:
    KnowledgeRetriever = None


# ---------------------------------------------------------------------------
# 公共入口（引擎选择，保持原 services.py 覆盖层行为）
# ---------------------------------------------------------------------------


def retrieve_top_chunks(
    user,
    question: str,
    top_k: int | None = None,
    source_ids: Sequence[int] | None = None,
):
    top_k = top_k or env_int("AGENT_TOP_K", 5)
    scored = _vector_search_chunks(user, question, top_k, source_ids)
    if scored is not None:
        documents = [_chunk_to_document(chunk, score) for chunk, score in scored]
        references = [chunk_to_reference(chunk, score) for chunk, score in scored]
        return documents, references
    if not _LANGCHAIN_AVAILABLE or KnowledgeRetriever is None:
        return _legacy_retrieve_top_chunks(user, question, top_k=top_k, source_ids=source_ids)
    retriever = KnowledgeRetriever(
        user_uid=user.uid,
        department_id=str(getattr(getattr(user, "department", None), "id", "")) or None,
        is_boarder=is_boarder(user),
        source_ids=list(source_ids or []),
        top_k=top_k,
    )
    documents = retriever.invoke(question)
    references = [document_to_reference(document) for document in documents]
    return documents, references


def _safe_search_web(question: str, internal_docs, web_search: bool | None = None) -> tuple[list, str | None]:
    """联网搜索的降级包装：搜索失败不中断问答，返回 (结果, 错误信息)。

    - web_search=False：显式禁用联网搜索 → ([], None)
    - web_search=True：显式强制联网搜索（忽略 auto 判断）
    - web_search=None：按 .env 配置（AGENT_WEB_SEARCH_ENABLED / MODE）走 auto 逻辑
    - 联网失败：([], 错误信息)，由调用方记录到 metadata / 提示文案。
    """
    try:
        use_web = web_search if web_search is not None else should_use_web_search(question, internal_docs)
        if not use_web:
            return [], None
        return search_web(question), None
    except AgentServiceError as exc:
        return [], str(exc)
    except Exception as exc:
        return [], f"联网搜索异常：{exc}"


def _web_error_brief(web_error: str | None) -> str:
    if not web_error:
        return ""
    return web_error if len(web_error) <= 120 else web_error[:120] + "…"


def ask_question(
    user,
    question: str,
    *,
    conversation: AgentConversation | None = None,
    source_ids: Sequence[int] | None = None,
    top_k: int | None = None,
    web_search: bool | None = None,
):
    if not _LANGCHAIN_AVAILABLE:
        return _legacy_ask_question(
            user,
            question,
            conversation=conversation,
            source_ids=source_ids,
            top_k=top_k,
        )
    if guard_enabled():
        injection_hits = scan_injection(question)
        if injection_hits:
            raise AgentServiceError(
                "检测到疑似指令注入，已拒绝处理"
                f"（命中：{'、'.join(injection_hits)}）。"
                "请不要在提问中要求助手忽略指令、泄露提示词或切换角色。"
            )

    try:
        tool_hit, tool_context, tool_calls = try_tool_call(user, question)
        internal_docs, internal_references = retrieve_top_chunks(user, question, top_k=top_k, source_ids=source_ids)
        web_docs, web_error = _safe_search_web(question, internal_docs, web_search=web_search)
        web_references = [document_to_reference(document) for document in web_docs]

        if conversation is None:
            conversation = AgentConversation.objects.create(
                user=user,
                title=question[:48],
                provider=get_chat_config().provider,
                model_name=get_chat_config().model,
                question_count=0,
            )

        history = conversation_history_scope(conversation)
        if not internal_docs and not web_docs:
            if web_error:
                answer = (
                    "未检索到足够相关的内部知识，且联网搜索暂不可用"
                    f"（{_web_error_brief(web_error)}）。请稍后重试，或先导入对应资料。"
                )
            else:
                answer = "未检索到足够相关的内部知识，也没有可用的联网结果。请换个问法，或先导入对应资料。"
            usage = {}
        else:
            answer, usage = invoke_answer(
                question=question,
                history=history,
                internal_docs=internal_docs,
                web_docs=web_docs,
                tool_context=tool_context,
                tags=["agent", "rag", "langchain", "tavily", "tools"] if tool_hit else ["agent", "rag", "langchain", "tavily"],
                metadata={
                    "user_uid": user.uid,
                    "conversation_id": conversation.id if conversation.id else None,
                    "source_count": len(internal_docs),
                    "web_count": len(web_docs),
                    "tool_used": tool_hit,
                    "tool_calls": tool_calls,
                },
            )

        AgentMessage.objects.create(
            conversation=conversation,
            role=AgentConversationRole.USER,
            content=question,
        )
        assistant_message = AgentMessage.objects.create(
            conversation=conversation,
            role=AgentConversationRole.ASSISTANT,
            content=answer,
            citations=[*internal_references, *web_references],
            metadata={
                "usage": usage,
                "stack": "langchain",
                "web_search_used": bool(web_docs),
                "web_search_requested": web_search,
                "web_error": web_error,
                "internal_reference_count": len(internal_references),
                "web_reference_count": len(web_references),
                "tool_used": tool_hit,
                "tool_calls": tool_calls,
            },
        )

        conversation.question_count = conversation.question_count + 1
        conversation.last_question = question
        conversation.last_answer = answer
        conversation.provider = get_chat_config().provider
        conversation.model_name = get_chat_config().model
        if not conversation.title:
            conversation.title = question[:48]
        conversation.metadata = {
            **(conversation.metadata or {}),
            "stack": "langchain",
            "web_search_used": bool(web_docs),
            "web_search_requested": web_search,
            "web_error": web_error,
            "internal_reference_count": len(internal_references),
            "web_reference_count": len(web_references),
            "tool_used": tool_hit,
            "tool_calls": tool_calls,
            "top_k": top_k or env_int("AGENT_TOP_K", 5),
        }
        conversation.save(
            update_fields=[
                "title",
                "provider",
                "model_name",
                "question_count",
                "last_question",
                "last_answer",
                "metadata",
                "updated_at",
            ]
        )

        return {
            "conversation": conversation,
            "assistant_message": assistant_message,
            "references": [*internal_references, *web_references],
            "usage": usage,
        }
    except Exception as exc:
        if isinstance(exc, AgentServiceError):
            raise
        raise AgentServiceError(str(exc)) from exc


def stream_ask_question(
    user,
    question: str,
    *,
    conversation: AgentConversation | None = None,
    source_ids: Sequence[int] | None = None,
    top_k: int | None = None,
    web_search: bool | None = None,
):
    """流式问答：返回一个事件生成器（供视图层封装为 SSE）。

    事件类型（dict）：
      start: {"type": "start", "conversation_id", "message_id", "references"}
      delta: {"type": "delta", "content": "内容增量"}
      usage: {"type": "usage", "usage": {...}}        # 服务端返回用量时
      done:  {"type": "done", "answer", "message_id",
              "conversation_id", "sources", "usage"}
      error: {"type": "error", "detail": "错误信息"}

    LangChain 引擎可用时走 ``llm.stream()``，否则回退 legacy 的 HTTP SSE 解析。
    """
    if guard_enabled():
        injection_hits = scan_injection(question)
        if injection_hits:
            raise AgentServiceError(
                "检测到疑似指令注入，已拒绝处理"
                f"（命中：{'、'.join(injection_hits)}）。"
                "请不要在提问中要求助手忽略指令、泄露提示词或切换角色。"
            )

    def event_stream():
        nonlocal conversation
        assistant_message: AgentMessage | None = None
        usage: dict = {}
        answer_parts: list[str] = []
        internal_references: list = []
        web_references: list = []
        web_error: str | None = None
        finalized = False

        def finalize(failed_detail: str | None = None) -> None:
            """统一落库收尾：正常结束 / 客户端断连 / 异常时都会调用，幂等。

            断连时生成器会被服务器 close（抛 GeneratorExit 到当前 yield 处），
            若不在此兜底，消息会一直停留在占位的空内容。
            """
            nonlocal finalized
            if finalized or assistant_message is None:
                return
            finalized = True
            try:
                if failed_detail and not answer_parts:
                    answer = f"（生成失败）{failed_detail}"
                else:
                    answer = "".join(answer_parts)
                stack = "langchain" if (_LANGCHAIN_AVAILABLE and _langchain_stream_answer is not None) else "legacy"
                assistant_message.content = answer
                assistant_message.citations = [*internal_references, *web_references]
                assistant_message.metadata = {
                    "usage": usage,
                    "stack": stack,
                    "web_search_used": bool(web_references),
                    "web_search_requested": web_search,
                    "web_error": web_error,
                    "stream": True,
                    "internal_reference_count": len(internal_references),
                    "web_reference_count": len(web_references),
                    "tool_used": tool_hit,
                    "tool_calls": tool_calls,
                }
                assistant_message.save(update_fields=["content", "citations", "metadata"])

                if conversation is not None:
                    conversation.question_count = conversation.question_count + 1
                    conversation.last_question = question
                    conversation.last_answer = answer
                    conversation.provider = get_chat_config().provider
                    conversation.model_name = get_chat_config().model
                    if not conversation.title:
                        conversation.title = question[:48]
                    conversation.metadata = {
                        **(conversation.metadata or {}),
                        "stack": stack,
                        "web_search_used": bool(web_references),
                        "web_search_requested": web_search,
                        "web_error": web_error,
                        "stream": True,
                        "internal_reference_count": len(internal_references),
                        "web_reference_count": len(web_references),
                        "tool_used": tool_hit,
                        "tool_calls": tool_calls,
                        "top_k": top_k or env_int("AGENT_TOP_K", 5),
                    }
                    conversation.save(
                        update_fields=[
                            "title",
                            "provider",
                            "model_name",
                            "question_count",
                            "last_question",
                            "last_answer",
                            "metadata",
                            "updated_at",
                        ]
                    )
            except Exception:
                pass

        try:
            # 0) Agent 工具决策（请假/审批等业务查询；任一失败静默降级纯 RAG）
            tool_hit, tool_context, tool_calls = try_tool_call(user, question)
            # 1) 检索内部知识（并视需要触发联网搜索）
            if _LANGCHAIN_AVAILABLE and _langchain_stream_answer is not None:
                internal_docs, internal_references = retrieve_top_chunks(
                    user, question, top_k=top_k, source_ids=source_ids
                )
                web_docs, web_error = _safe_search_web(question, internal_docs, web_search=web_search)
                web_references = [document_to_reference(document) for document in web_docs]
                has_evidence = bool(internal_docs or web_docs)
            else:
                _, internal_references = retrieve_top_chunks(
                    user, question, top_k=top_k, source_ids=source_ids
                )
                web_docs = []
                web_error = None
                web_references = []
                has_evidence = bool(internal_references)

            # 2) 会话与消息占位（流式生成前先落库，前端可拿到 message_id）
            if conversation is None:
                conversation = AgentConversation.objects.create(
                    user=user,
                    title=question[:48],
                    provider=get_chat_config().provider,
                    model_name=get_chat_config().model,
                    question_count=0,
                )
            history = conversation_history_scope(conversation)
            AgentMessage.objects.create(
                conversation=conversation,
                role=AgentConversationRole.USER,
                content=question,
            )
            assistant_message = AgentMessage.objects.create(
                conversation=conversation,
                role=AgentConversationRole.ASSISTANT,
                content="",
                citations=[*internal_references, *web_references],
                metadata={},
            )
            yield {
                "type": "start",
                "conversation_id": conversation.id,
                "message_id": assistant_message.id,
                "references": [*internal_references, *web_references],
            }

            # 3) 流式生成答案
            if not has_evidence:
                if web_error:
                    fallback = (
                        "未检索到足够相关的内部知识，且联网搜索暂不可用"
                        f"（{_web_error_brief(web_error)}）。请稍后重试，或先导入对应资料。"
                    )
                else:
                    fallback = (
                        "未检索到足够相关的内部知识，也没有可用的联网结果。请换个问法，或先导入对应资料。"
                        if _LANGCHAIN_AVAILABLE and _langchain_stream_answer is not None
                        else "未检索到足够相关的知识库内容，请换个问法，或者先导入对应资料。"
                    )
                yield {"type": "delta", "content": fallback}
                answer_parts.append(fallback)
            elif _LANGCHAIN_AVAILABLE and _langchain_stream_answer is not None:
                for kind, payload in _langchain_stream_answer(
                    question=question,
                    history=history,
                    internal_docs=internal_docs,
                    web_docs=web_docs,
                    tool_context=tool_context,
                    tags=["agent", "rag", "langchain", "tavily", "tools", "stream"] if tool_hit else ["agent", "rag", "langchain", "tavily", "stream"],
                    metadata={
                        "user_uid": user.uid,
                        "conversation_id": conversation.id,
                        "source_count": len(internal_docs),
                        "web_count": len(web_docs),
                        "tool_used": tool_hit,
                        "tool_calls": tool_calls,
                    },
                ):
                    if kind == "delta":
                        answer_parts.append(payload)
                        yield {"type": "delta", "content": payload}
                    elif kind == "usage":
                        usage = payload
            else:
                messages = build_context_prompt(question, internal_references, history)
                for kind, payload in _legacy_stream_chat_completion(messages):
                    if kind == "delta":
                        answer_parts.append(payload)
                        yield {"type": "delta", "content": payload}
                    elif kind == "usage":
                        usage = payload

            # 4) 落库收尾
            finalize()
            yield {
                "type": "done",
                "answer": "".join(answer_parts),
                "message_id": assistant_message.id,
                "conversation_id": conversation.id,
                "sources": [*internal_references, *web_references],
                "usage": usage,
            }
        except (BrokenPipeError, ConnectionResetError):
            # 客户端断开连接：保留已生成内容落库，不标记失败、不再 yield
            pass
        except Exception as exc:
            detail = str(exc) if isinstance(exc, AgentServiceError) else str(exc)
            finalize(failed_detail=detail)
            try:
                yield {"type": "error", "detail": detail}
            except Exception:
                pass
        finally:
            # 断连 / 生成器被 close（GeneratorExit）时兜底落库
            finalize()

    return event_stream()
