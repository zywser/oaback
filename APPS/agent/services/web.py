"""联网搜索（Tavily）与搜索开关判断。"""
from __future__ import annotations

from ._compat import _LANGCHAIN_AVAILABLE
from .config import get_web_search_config
from .env import env_strip
from .exceptions import AgentServiceError
from .text import normalize_text


def _legacy_search_web(question: str):
    return []


def _legacy_should_use_web_search(question: str, internal_docs) -> bool:
    return False


# ---------------------------------------------------------------------------
# LangChain 引擎实现（原 langchain_stack.py）
# ---------------------------------------------------------------------------

if _LANGCHAIN_AVAILABLE:
    try:
        from langchain_core.documents import Document
        from langchain_tavily import TavilySearch

        def get_web_search_tool() -> TavilySearch:
            config = get_web_search_config()
            api_key = env_strip("TAVILY_API_KEY")
            if not api_key:
                raise AgentServiceError(
                    "未检测到 TAVILY_API_KEY，联网搜索不可用：请确认 .env 中已填写并保存，"
                    "然后重启 Django 服务（.env 只在进程启动时加载，运行中修改不会生效）"
                )
            return TavilySearch(
                tavily_api_key=api_key,
                api_base_url=env_strip("TAVILY_API_URL") or None,
                max_results=config.max_results,
                search_depth=config.search_depth,
                topic=config.topic,
                include_raw_content=config.include_raw_content,
            )

        def should_use_web_search(question: str, internal_docs) -> bool:
            config = get_web_search_config()
            if not config.enabled or config.mode == "off":
                return False
            if config.mode == "always":
                return True

            if not internal_docs:
                return True

            top_score = max(float(doc.metadata.get("score", 0)) for doc in internal_docs if doc.metadata)
            if top_score < float(env_strip("AGENT_INTERNAL_SCORE_THRESHOLD", "0.22")):
                return True

            keywords = (
                "最新",
                "新闻",
                "现在",
                "当前",
                "今天",
                "本周",
                "本月",
                "今年",
                "行情",
                "价格",
                "汇率",
                "政策",
                "官网",
                "公告",
                "上市",
                "搜索",
                "internet",
                "web",
                "news",
                "today",
                "latest",
            )
            lower_question = question.lower()
            return any(keyword in question or keyword in lower_question for keyword in keywords)

        def _result_title(result: dict, index: int) -> str:
            return (
                result.get("title")
                or result.get("name")
                or result.get("url")
                or result.get("source")
                or f"Web Result {index}"
            )

        def search_web(question: str) -> list[Document]:
            tool = get_web_search_tool()
            result = tool.invoke({"query": question})
            # TavilySearch._run 捕获网络/认证异常后返回 {"error": ...}，
            # 这里显式暴露，避免被静默当成“没有搜索结果”。
            if isinstance(result, dict) and result.get("error"):
                raise AgentServiceError(f"联网搜索失败：{result['error']}")
            items = []
            if isinstance(result, dict):
                items = result.get("results") or []
            elif isinstance(result, list):
                items = result

            documents: list[Document] = []
            for index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    continue
                title = _result_title(item, index)
                content = item.get("content") or item.get("raw_content") or item.get("snippet") or ""
                content = normalize_text(content)
                if not content:
                    continue
                documents.append(
                    Document(
                        page_content=content,
                        metadata={
                            "source_id": f"web-{index}",
                            "source_type": "web",
                            "title": title,
                            "chunk_id": f"web-{index}",
                            "chunk_index": index - 1,
                            "score": float(item.get("score") or 0),
                            "excerpt": content[:400],
                            "is_public": True,
                            "departments": [],
                            "file_url": "",
                            "author": item.get("source") or item.get("published") or "",
                            "created_at": item.get("published_time") or item.get("date") or "",
                            "url": item.get("url") or "",
                            "source_origin": "web",
                            "raw_content": item.get("raw_content") or "",
                        },
                    )
                )
            return documents

    except Exception:
        get_web_search_tool = None
        should_use_web_search = _legacy_should_use_web_search
        search_web = _legacy_search_web
else:
    get_web_search_tool = None
    should_use_web_search = _legacy_should_use_web_search
    search_web = _legacy_search_web
