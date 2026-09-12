"""兼容层：LangChain 引擎实现已按职责迁入 ``APPS.agent.services`` 包。

本文件仅保留旧导入路径（``from .langchain_stack import ...``）的兼容性，
新代码请直接从 ``APPS.agent.services`` 导入。
"""
from .services import (
    AgentStackError,
    ChatConfig,
    DashScopeEmbeddings,
    EmbeddingConfig,
    KnowledgeRetriever,
    WebSearchConfig,
    build_agent_prompt,
    build_history_messages,
    conversation_history_scope,
    document_to_reference,
    env,
    env_bool,
    env_int,
    estimate_tokens,
    format_documents_for_prompt,
    get_chat_config,
    get_chat_model,
    get_embedding_config,
    get_snapshot,
    get_web_search_config,
    get_web_search_tool,
    invoke_answer,
    is_boarder,
    normalize_text,
    search_web,
    should_use_web_search,
)
