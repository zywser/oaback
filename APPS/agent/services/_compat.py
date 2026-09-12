"""LangChain 引擎可用性检测。

与原 services.py 中 ``try: from .langchain_stack import ...`` 的语义保持一致：
只要 LangChain 相关依赖可用即视为引擎可用，否则整体回退到 legacy 实现。
"""

try:
    import langchain_core  # noqa: F401
    from langchain_openai import ChatOpenAI  # noqa: F401
    from langchain_tavily import TavilySearch  # noqa: F401
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: F401

    _LANGCHAIN_AVAILABLE = True
except Exception:
    _LANGCHAIN_AVAILABLE = False
