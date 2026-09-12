"""LLM / Embedding / Web 搜索的配置读取。

提供 LangChain 引擎与 legacy 引擎两套配置实现，并根据
``_compat._LANGCHAIN_AVAILABLE`` 自动选择（与原代码行为一致）。
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from ._compat import _LANGCHAIN_AVAILABLE
from .env import env, env_bool, env_int, env_bool_strip, env_int_strip, env_strip
from .security import guard_enabled


@dataclass(frozen=True)
class ChatConfig:
    provider: str
    base_url: str
    api_key: str
    model: str

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


# legacy 引擎使用的类型名（字段与 ChatConfig 完全一致）
LLMConfig = ChatConfig


@dataclass(frozen=True)
class EmbeddingConfig:
    provider: str
    base_url: str
    api_key: str
    model: str

    @property
    def ready(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)


@dataclass(frozen=True)
class WebSearchConfig:
    enabled: bool
    mode: str
    max_results: int
    topic: str
    include_raw_content: bool
    search_depth: str


# ---------------------------------------------------------------------------
# LangChain 引擎配置（原 langchain_stack.py）
# ---------------------------------------------------------------------------


def _stack_chat_config() -> ChatConfig:
    provider = env_strip("AGENT_LLM_PROVIDER", "deepseek").lower()
    if provider == "openai":
        return ChatConfig(
            provider=provider,
            base_url=env_strip("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=env_strip("OPENAI_API_KEY"),
            model=env_strip("OPENAI_MODEL", "gpt-4o-mini"),
        )
    return ChatConfig(
        provider=provider,
        base_url=env_strip("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        api_key=env_strip("DEEPSEEK_API_KEY"),
        model=env_strip("DEEPSEEK_MODEL", "deepseek-chat"),
    )


def _stack_embedding_config() -> EmbeddingConfig:
    provider = env_strip("AGENT_EMBED_PROVIDER", "qwen").lower()
    if provider == "openai":
        return EmbeddingConfig(
            provider=provider,
            base_url=env_strip("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=env_strip("OPENAI_API_KEY"),
            model=env_strip("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
        )
    return EmbeddingConfig(
        provider=provider,
        base_url=env_strip(
            "DASHSCOPE_EMBED_URL",
            "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
        ),
        api_key=env_strip("DASHSCOPE_API_KEY"),
        model=env_strip("QWEN_EMBED_MODEL", "text-embedding-v4"),
    )


def _stack_web_search_config() -> WebSearchConfig:
    return WebSearchConfig(
        enabled=env_bool_strip("AGENT_WEB_SEARCH_ENABLED", True),
        mode=env_strip("AGENT_WEB_SEARCH_MODE", "auto").lower(),
        max_results=env_int_strip("AGENT_WEB_SEARCH_MAX_RESULTS", 5),
        topic=env_strip("AGENT_WEB_SEARCH_TOPIC", "general"),
        include_raw_content=env_bool_strip("AGENT_WEB_SEARCH_INCLUDE_RAW_CONTENT", False),
        search_depth=env_strip("AGENT_WEB_SEARCH_SEARCH_DEPTH", "advanced"),
    )


def _vector_store_available() -> bool:
    """向量库当前是否可用（不影响功能，仅用于前端状态展示）。"""
    try:
        from .vectorstore import get_vector_store

        return get_vector_store() is not None
    except Exception:  # noqa: BLE001
        return False


def _stack_snapshot() -> dict:
    llm = _stack_chat_config()
    embed = _stack_embedding_config()
    web = _stack_web_search_config()
    return {
        "stack": "langchain",
        "llm": {
            "provider": llm.provider,
            "model": llm.model,
            "ready": llm.ready,
        },
        "embedding": {
            "provider": embed.provider,
            "model": embed.model,
            "ready": embed.ready,
        },
        "injection_guard": guard_enabled(),
        "web_search": {
            "enabled": web.enabled,
            "mode": web.mode,
            "max_results": web.max_results,
            "topic": web.topic,
            "ready": bool(env_strip("TAVILY_API_KEY")),
        },
        "langsmith": {
            "tracing": env_bool_strip("LANGSMITH_TRACING", False) or env_bool_strip("LANGCHAIN_TRACING_V2", False),
            "project": env_strip("LANGSMITH_PROJECT", env_strip("LANGCHAIN_PROJECT", "oa-agent")),
            "ready": bool(env_strip("LANGSMITH_API_KEY")),
        },
        "chunk_size": env_int_strip("AGENT_CHUNK_SIZE", 900),
        "chunk_overlap": env_int_strip("AGENT_CHUNK_OVERLAP", 120),
        "top_k": env_int_strip("AGENT_TOP_K", 5),
        "history_size": env_int_strip("AGENT_HISTORY_SIZE", 6),
        "vector_store": {
            "mode": env_strip("AGENT_VECTOR_STORE", "auto"),
            "available": _vector_store_available(),
        },
        "tools": {
            "enabled": env_bool_strip("AGENT_TOOLS_ENABLED", True),
        },
    }


# ---------------------------------------------------------------------------
# legacy 引擎配置（原 services.py 的 fallback 实现）
# ---------------------------------------------------------------------------


def _legacy_chat_config() -> SimpleNamespace:
    provider = env("AGENT_LLM_PROVIDER", "deepseek").lower()
    if provider == "openai":
        return SimpleNamespace(
            provider=provider,
            base_url=env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=env("OPENAI_API_KEY"),
            model=env("OPENAI_MODEL", "gpt-4o-mini"),
            ready=bool(
                env("OPENAI_BASE_URL", "https://api.openai.com/v1")
                and env("OPENAI_API_KEY")
                and env("OPENAI_MODEL", "gpt-4o-mini")
            ),
        )
    return SimpleNamespace(
        provider=provider,
        base_url=env("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        api_key=env("DEEPSEEK_API_KEY"),
        model=env("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        ready=bool(
            env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
            and env("DEEPSEEK_API_KEY")
            and env("DEEPSEEK_MODEL", "deepseek-v4-pro")
        ),
    )


def _legacy_embedding_config() -> SimpleNamespace:
    provider = env("AGENT_EMBED_PROVIDER", "qwen").lower()
    if provider == "openai":
        return SimpleNamespace(
            provider=provider,
            base_url=env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=env("OPENAI_API_KEY"),
            model=env("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
            ready=bool(
                env("OPENAI_BASE_URL", "https://api.openai.com/v1")
                and env("OPENAI_API_KEY")
                and env("OPENAI_EMBED_MODEL", "text-embedding-3-small")
            ),
        )
    return SimpleNamespace(
        provider=provider,
        base_url=env(
            "DASHSCOPE_EMBED_URL",
            "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
        ),
        api_key=env("DASHSCOPE_API_KEY"),
        model=env("QWEN_EMBED_MODEL", "text-embedding-v4"),
        ready=bool(
            env(
                "DASHSCOPE_EMBED_URL",
                "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding",
            )
            and env("DASHSCOPE_API_KEY")
            and env("QWEN_EMBED_MODEL", "text-embedding-v4")
        ),
    )


def _legacy_snapshot() -> dict:
    llm = _legacy_chat_config()
    embed = _legacy_embedding_config()
    return {
        "stack": "legacy",
        "llm": {"provider": llm.provider, "model": llm.model, "ready": llm.ready},
        "embedding": {"provider": embed.provider, "model": embed.model, "ready": embed.ready},
        "web_search": {
            "enabled": False,
            "mode": "off",
            "max_results": 0,
            "topic": "general",
            "ready": False,
        },
        "langsmith": {
            "tracing": False,
            "project": env("LANGSMITH_PROJECT", env("LANGCHAIN_PROJECT", "oa-agent")),
            "ready": bool(env("LANGSMITH_API_KEY")),
        },
        "chunk_size": env_int("AGENT_CHUNK_SIZE", 900),
        "chunk_overlap": env_int("AGENT_CHUNK_OVERLAP", 120),
        "top_k": env_int("AGENT_TOP_K", 5),
        "history_size": env_int("AGENT_HISTORY_SIZE", 6),
        "vector_store": {"mode": "none", "available": False},
        "tools": {"enabled": env_bool("AGENT_TOOLS_ENABLED", True)},
    }


# ---------------------------------------------------------------------------
# 公共入口（按引擎选择，保持原 services.py 行为）
# ---------------------------------------------------------------------------

if _LANGCHAIN_AVAILABLE:
    get_chat_config = _stack_chat_config
    get_embedding_config = _stack_embedding_config
    get_web_search_config = _stack_web_search_config
    get_config_snapshot = _stack_snapshot
else:
    get_chat_config = _legacy_chat_config
    get_embedding_config = _legacy_embedding_config

    def get_web_search_config() -> SimpleNamespace:
        return SimpleNamespace(
            enabled=False,
            mode="off",
            max_results=0,
            topic="general",
            include_raw_content=False,
            search_depth="advanced",
        )

    get_config_snapshot = _legacy_snapshot


# 兼容别名
get_llm_config = get_chat_config
get_snapshot = get_config_snapshot
