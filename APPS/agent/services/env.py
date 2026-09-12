"""环境变量读取工具。

- env / env_int / env_bool：legacy 引擎使用（保持原 services.py 行为）。
- env_strip / env_int_strip / env_bool_strip：LangChain 引擎配置使用（保持原 langchain_stack.py 行为）。
"""

import os


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on", "enabled"}


def env_strip(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_int_strip(name: str, default: int) -> int:
    try:
        return int(env_strip(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_bool_strip(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
