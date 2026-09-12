"""agent 业务异常。"""


class AgentServiceError(RuntimeError):
    """业务服务层错误（视图层捕获并转为 400 响应）。"""


class AgentStackError(RuntimeError):
    """LangChain 引擎层错误（原 langchain_stack.AgentStackError）。"""
