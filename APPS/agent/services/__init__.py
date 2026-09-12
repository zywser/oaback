"""APPS.agent.services —— agent 业务逻辑包。

原 services.py（34KB）与 langchain_stack.py（19KB）按职责拆分为：

- config:       LLM / Embedding / Web 搜索配置（含 legacy 与 LangChain 双引擎选择）
- llm:          LLM 对话与 Embedding 调用
- text:         文本归一化、分块与文件内容提取
- permissions:  知识库访问控制（鉴权 / 可见性）
- web:          联网搜索（Tavily）
- prompts:      Prompt 构建与上下文格式化
- knowledge:    RAG 知识库：入库、索引、检索、问答、反馈
- env / exceptions / _compat: 工具、异常与引擎可用性检测

对外导入路径保持不变：``from .services import ...`` 与
``from APPS.agent.services import ...`` 均继续可用。
"""
from ._compat import _LANGCHAIN_AVAILABLE
from .config import (
    ChatConfig,
    EmbeddingConfig,
    LLMConfig,
    WebSearchConfig,
    get_chat_config,
    get_config_snapshot,
    get_embedding_config,
    get_llm_config,
    get_snapshot,
    get_web_search_config,
)
from .env import env, env_bool, env_int
from .exceptions import AgentServiceError, AgentStackError
from .knowledge import (
    KnowledgeRetriever,
    ask_question,
    chunk_to_reference,
    cosine_similarity,
    create_feedback,
    ingest_source_text,
    purge_source_vectors,
    rebuild_source_index,
    retrieve_top_chunks,
    stream_ask_question,
    sync_inform_sources,
)
from .llm import DashScopeEmbeddings, chat_completion, embed_texts, get_chat_model
from .permissions import _source_is_accessible, accessible_sources_queryset, is_boarder
from .prompts import (
    build_agent_prompt,
    build_context_prompt,
    build_history_messages,
    conversation_history_scope,
    document_to_reference,
    format_documents_for_prompt,
    invoke_answer,
)
from .text import estimate_tokens, extract_text_from_file, normalize_text, split_text
from .tools import build_oa_tools, try_tool_call
from .vectorstore import get_vector_store
from .web import get_web_search_tool, search_web, should_use_web_search

__all__ = [
    "_LANGCHAIN_AVAILABLE",
    "AgentServiceError",
    "AgentStackError",
    "ChatConfig",
    "DashScopeEmbeddings",
    "EmbeddingConfig",
    "KnowledgeRetriever",
    "LLMConfig",
    "WebSearchConfig",
    "accessible_sources_queryset",
    "ask_question",
    "build_agent_prompt",
    "build_context_prompt",
    "build_history_messages",
    "build_oa_tools",
    "chat_completion",
    "chunk_to_reference",
    "conversation_history_scope",
    "cosine_similarity",
    "create_feedback",
    "document_to_reference",
    "embed_texts",
    "env",
    "env_bool",
    "env_int",
    "estimate_tokens",
    "extract_text_from_file",
    "format_documents_for_prompt",
    "get_chat_config",
    "get_chat_model",
    "get_config_snapshot",
    "get_embedding_config",
    "get_llm_config",
    "get_snapshot",
    "get_vector_store",
    "get_web_search_config",
    "get_web_search_tool",
    "ingest_source_text",
    "invoke_answer",
    "is_boarder",
    "normalize_text",
    "purge_source_vectors",
    "rebuild_source_index",
    "retrieve_top_chunks",
    "search_web",
    "should_use_web_search",
    "split_text",
    "stream_ask_question",
    "sync_inform_sources",
    "try_tool_call",
]
