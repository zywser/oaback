"""LLM 对话与 Embedding 调用。

包含：
- 通用 HTTP 调用帮助函数
- legacy 引擎的 OpenAI 兼容 HTTP 实现
- LangChain 引擎的 ChatOpenAI / DashScopeEmbeddings 封装
- 引擎选择入口 embed_texts / chat_completion（保持原 services.py 行为）
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Sequence

from ._compat import _LANGCHAIN_AVAILABLE
from .config import get_embedding_config, get_llm_config
from .env import env
from .exceptions import AgentServiceError


# ---------------------------------------------------------------------------
# 通用 HTTP 帮助函数
# ---------------------------------------------------------------------------


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 120) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise AgentServiceError(f"LLM API 请求失败: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise AgentServiceError(f"LLM API 请求失败: {exc.reason}") from exc


def _extract_error_message(response: dict) -> str:
    if not isinstance(response, dict):
        return "未知错误"
    if "error" in response:
        error = response["error"]
        if isinstance(error, dict):
            return error.get("message") or error.get("code") or "未知错误"
        return str(error)
    if "message" in response:
        return str(response["message"])
    return "未知错误"


# ---------------------------------------------------------------------------
# legacy 引擎的 OpenAI 兼容 HTTP 实现
# ---------------------------------------------------------------------------


def _openai_chat_completion(
    config,
    messages: Sequence[dict],
    temperature: float = 0.2,
    max_tokens: int = 1200,
) -> tuple[str, dict]:
    payload = {
        "model": config.model,
        "messages": list(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if config.provider == "deepseek":
        thinking = env("DEEPSEEK_THINKING", "disabled").lower()
        if thinking in {"disabled", "false", "0"}:
            payload["thinking"] = {"type": "disabled"}
        else:
            payload["reasoning_effort"] = env("DEEPSEEK_REASONING_EFFORT", "low")

    response = _post_json(
        config.base_url.rstrip("/") + "/chat/completions",
        payload,
        {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AgentServiceError(f"LLM 返回格式异常: {_extract_error_message(response)}") from exc
    return content, response.get("usage", {})


def _openai_embedding(config, texts: Sequence[str], kind: str = "document") -> list[list[float]]:
    if config.provider == "openai":
        payload = {
            "model": config.model,
            "input": list(texts),
        }
    else:
        payload = {
            "model": config.model,
            "input": {"texts": list(texts)},
            "parameters": {"text_type": kind},
        }
    endpoint = config.base_url.rstrip("/")
    if config.provider == "openai":
        endpoint = endpoint + "/embeddings"
    response = _post_json(
        endpoint,
        payload,
        {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
    )
    if config.provider == "openai":
        items = response.get("data", [])
        return [list(item.get("embedding", [])) for item in items]
    items = response.get("output", {}).get("embeddings", [])
    return [list(item.get("embedding", [])) for item in items]


def _legacy_chat_completion(messages: Sequence[dict], temperature: float = 0.2, max_tokens: int = 1200) -> tuple[str, dict]:
    config = get_llm_config()
    if not config.ready:
        raise AgentServiceError("对话模型未配置，请先填写 .env")
    if config.provider in {"deepseek", "openai"}:
        return _openai_chat_completion(config, messages, temperature=temperature, max_tokens=max_tokens)
    raise AgentServiceError(f"暂不支持的对话提供方: {config.provider}")


def _stream_openai_chat(
    config,
    messages: Sequence[dict],
    temperature: float = 0.2,
    max_tokens: int = 1200,
    timeout: int = 300,
):
    """OpenAI 兼容接口的 SSE 流式调用（legacy 引擎）。

    逐行解析 ``data: {...}`` 事件，yield (kind, payload)：
      ("delta", str)  - 内容增量
      ("usage", dict) - token 用量（若服务端返回）
      ("finish", str) - 结束原因（finish_reason）
    """
    payload = {
        "model": config.model,
        "messages": list(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if config.provider == "deepseek":
        thinking = env("DEEPSEEK_THINKING", "disabled").lower()
        if thinking in {"disabled", "false", "0"}:
            payload["thinking"] = {"type": "disabled"}
        else:
            payload["reasoning_effort"] = env("DEEPSEEK_REASONING_EFFORT", "low")

    url = config.base_url.rstrip("/") + "/chat/completions"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise AgentServiceError(f"LLM API 请求失败: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise AgentServiceError(f"LLM API 请求失败: {exc.reason}") from exc

    for raw_line in response:
        line = raw_line.decode("utf-8", errors="ignore").strip()
        if not line.startswith("data:"):
            continue
        data_str = line[len("data:"):].strip()
        if data_str == "[DONE]":
            break
        try:
            chunk = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        if chunk.get("usage"):
            yield ("usage", chunk["usage"])
        choices = chunk.get("choices") or []
        if not choices:
            continue
        first = choices[0] if isinstance(choices[0], dict) else {}
        delta = first.get("delta") or {}
        content = delta.get("content")
        if content:
            yield ("delta", content)
        finish = first.get("finish_reason")
        if finish:
            yield ("finish", finish)


def _legacy_stream_chat_completion(
    messages: Sequence[dict],
    temperature: float = 0.2,
    max_tokens: int = 1200,
):
    """legacy 引擎的流式对话，yield (kind, payload)。"""
    config = get_llm_config()
    if not config.ready:
        raise AgentServiceError("对话模型未配置，请先填写 .env")
    if config.provider in {"deepseek", "openai"}:
        yield from _stream_openai_chat(config, messages, temperature=temperature, max_tokens=max_tokens)
        return
    raise AgentServiceError(f"暂不支持的对话提供方: {config.provider}")


def stream_chat_completion(
    messages: Sequence[dict],
    temperature: float = 0.2,
    max_tokens: int = 1200,
):
    """流式对话的公共入口（legacy 路径）。

    与 ``chat_completion`` 一致：LangChain 引擎可用时请走
    ``ask_question``/``stream_ask_question`` 的编排。
    """
    if not _LANGCHAIN_AVAILABLE:
        yield from _legacy_stream_chat_completion(messages, temperature=temperature, max_tokens=max_tokens)
        return
    raise AgentServiceError("流式对话已迁移到 LangChain 引擎，请使用 stream_ask_question")


def _legacy_embed_texts(texts: Sequence[str], kind: str = "document") -> list[list[float]]:
    config = get_embedding_config()
    if not config.ready:
        raise AgentServiceError("嵌入模型未配置，请先填写 .env")
    if not texts:
        return []
    if config.provider in {"qwen", "openai"}:
        return _openai_embedding(config, texts, kind=kind)
    raise AgentServiceError(f"暂不支持的嵌入提供方: {config.provider}")


# ---------------------------------------------------------------------------
# LangChain 引擎封装
# ---------------------------------------------------------------------------

try:
    from langchain_core.embeddings import Embeddings as _BaseEmbeddings
    from langchain_openai import ChatOpenAI

    class DashScopeEmbeddings(_BaseEmbeddings):
        def __init__(self):
            self.config = get_embedding_config()

        def _embed(self, texts: Sequence[str], kind: str) -> list[list[float]]:
            if not self.config.ready:
                raise AgentServiceError("嵌入模型未配置，请先填写 .env")
            if not texts:
                return []

            if self.config.provider == "openai":
                payload = {
                    "model": self.config.model,
                    "input": list(texts),
                }
                endpoint = self.config.base_url.rstrip("/") + "/embeddings"
            else:
                payload = {
                    "model": self.config.model,
                    "input": {"texts": list(texts)},
                    "parameters": {"text_type": kind},
                }
                endpoint = self.config.base_url.rstrip("/")

            response = _post_json(
                endpoint,
                payload,
                {
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
            )

            if self.config.provider == "openai":
                items = response.get("data", [])
                return [list(item.get("embedding", [])) for item in items]

            items = response.get("output", {}).get("embeddings", [])
            return [list(item.get("embedding", [])) for item in items]

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return self._embed(texts, kind="document")

        def embed_query(self, text: str) -> list[float]:
            return self._embed([text], kind="query")[0]

    def get_chat_model(temperature: float = 0.2, max_tokens: int = 1200) -> ChatOpenAI:
        config = get_llm_config()
        if not config.ready:
            raise AgentServiceError("对话模型未配置，请先填写 .env")
        if config.provider not in {"deepseek", "openai"}:
            raise AgentServiceError(f"暂不支持的对话提供方: {config.provider}")
        return ChatOpenAI(
            model=config.model,
            base_url=config.base_url,
            api_key=config.api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )

except Exception:
    DashScopeEmbeddings = None
    get_chat_model = None


# ---------------------------------------------------------------------------
# 公共入口（引擎选择，保持原 services.py 覆盖层行为）
# ---------------------------------------------------------------------------


def embed_texts(texts: Sequence[str], kind: str = "document") -> list[list[float]]:
    if not texts:
        return []
    if not _LANGCHAIN_AVAILABLE or DashScopeEmbeddings is None:
        return _legacy_embed_texts(texts, kind=kind)
    try:
        return DashScopeEmbeddings().embed_documents(list(texts))
    except Exception as exc:
        raise AgentServiceError(str(exc)) from exc


def chat_completion(messages: Sequence[dict], temperature: float = 0.2, max_tokens: int = 1200) -> tuple[str, dict]:
    if not _LANGCHAIN_AVAILABLE:
        return _legacy_chat_completion(messages, temperature=temperature, max_tokens=max_tokens)
    raise AgentServiceError("chat_completion 已迁移到 LangChain 引擎，请直接使用 ask_question")
