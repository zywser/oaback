"""Agent 工具调用：OA 业务查询工具 + LLM 工具决策。

决策流程：
  1) 关键词预筛（控制 LLM 调用成本）：问题未命中关键词直接跳过；
  2) LLM bind_tools 结构化决策：模型判断是否调用工具、调用哪个、传什么参数；
  3) 工具执行（闭包绑定当前用户，全部为 Django ORM 只读查询）；
  4) 工具结果作为额外上下文注入生成 Prompt，与 RAG 检索证据并列。

任一环节失败 / 未启用时静默降级为纯 RAG，不影响主链路。

配置（.env）：
  AGENT_TOOLS_ENABLED        true（默认）| false
  AGENT_TOOL_MAX_RESULTS     单工具返回上限，默认 10
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from APPS.absent.models import Absent, AbsentStatusChoices

from ._compat import _LANGCHAIN_AVAILABLE
from .env import env_bool_strip, env_int_strip

logger = logging.getLogger(__name__)

try:
    from langchain_core.messages import HumanMessage
    from langchain_core.tools import tool

    from .llm import get_chat_model
except Exception:  # pragma: no cover
    HumanMessage = None
    tool = None
    get_chat_model = None

# 工具触发关键词：命中任一才进入 LLM 工具决策（降低无谓调用）。
# 原则是「宁宽勿窄」——预筛只做粗排除，是否真的调用工具由 LLM 决策，
# 因此覆盖"请了几天假""我的假"等口语变体。
_TRIGGER_KEYWORDS = (
    "请假",
    "审批",
    "考勤",
    "休假",
    "年假",
    "事假",
    "病假",
    "婚假",
    "产假",
    "调休",
    "加班",
    "几天假",
    "多少天假",
    "我的假",
    "假条",
    "请假单",
    "请假记录",
    "请了",
)

_STATUS_TEXT = {
    AbsentStatusChoices.AUDITING: "审批中",
    AbsentStatusChoices.PASS: "已通过",
    AbsentStatusChoices.REJECT: "已拒绝",
}


def _status_text(status: int) -> str:
    return _STATUS_TEXT.get(status, f"未知({status})")


def _tools_enabled() -> bool:
    return env_bool_strip("AGENT_TOOLS_ENABLED", True)


def _max_results() -> int:
    return max(1, env_int_strip("AGENT_TOOL_MAX_RESULTS", 10))


def _triggered(question: str) -> bool:
    return any(keyword in question for keyword in _TRIGGER_KEYWORDS)


def _leave_days(start_date, end_date) -> int:
    if not start_date or not end_date:
        return 1
    return max((end_date - start_date).days + 1, 1)


def _format_absents(rows, header: str) -> str:
    if not rows:
        return f"{header}：无相关记录。"
    lines = [f"{header}，共 {len(rows)} 条："]
    for index, absent in enumerate(rows, start=1):
        reason = (absent.request_content or "").strip().replace("\n", " ")[:80]
        responder = absent.responder.realname if absent.responder_id else "未指定"
        lines.append(
            f"{index}. {absent.absent_type.name}「{reason or absent.title}」，"
            f"{absent.statar_date.isoformat()} ~ {absent.end_date.isoformat()}"
            f"（{_leave_days(absent.statar_date, absent.end_date)}天），"
            f"状态：{_status_text(absent.status)}，审批人：{responder}"
        )
    return "\n".join(lines)


def build_oa_tools(user):
    """构造绑定当前用户的 OA 查询工具（全部只读）。"""
    limit = _max_results()

    @tool
    def query_my_leaves(limit: int = limit, status: str = "") -> str:
        """查询当前用户自己提交的请假记录。status 可选值：审批中 / 通过 / 拒绝，留空查全部。"""
        queryset = Absent.objects.filter(requester=user).select_related("absent_type", "responder")
        code_map = {"审批中": AbsentStatusChoices.AUDITING, "通过": AbsentStatusChoices.PASS,
                    "已通过": AbsentStatusChoices.PASS, "拒绝": AbsentStatusChoices.REJECT,
                    "已拒绝": AbsentStatusChoices.REJECT, "驳回": AbsentStatusChoices.REJECT}
        code = code_map.get((status or "").strip())
        if code is not None:
            queryset = queryset.filter(status=code)
        rows = list(queryset[: max(1, min(int(limit or 10), 50))])
        return _format_absents(rows, "我的请假记录")

    @tool
    def query_my_pending_approvals(limit: int = limit) -> str:
        """查询需要当前用户审批的请假单（当前用户为审批人且状态为审批中）。"""
        rows = list(
            Absent.objects.filter(responder=user, status=AbsentStatusChoices.AUDITING)
            .select_related("absent_type", "requester")[: max(1, min(int(limit or 10), 50))]
        )
        if not rows:
            return "待我审批的请假单：无。"
        lines = [f"待我审批的请假单，共 {len(rows)} 条："]
        for index, absent in enumerate(rows, start=1):
            requester = absent.requester.realname if absent.requester_id else "未知"
            reason = (absent.request_content or "").strip().replace("\n", " ")[:80]
            lines.append(
                f"{index}. {requester} 提交的{absent.absent_type.name}「{reason or absent.title}」，"
                f"{absent.statar_date.isoformat()} ~ {absent.end_date.isoformat()}"
                f"（{_leave_days(absent.statar_date, absent.end_date)}天），"
                f"发起时间 {absent.create_time:%Y-%m-%d %H:%M}"
            )
        return "\n".join(lines)

    @tool
    def query_department_leave_stats(days: int = 30) -> str:
        """统计当前用户所在部门近 days 天（默认 30）内的请假申请汇总（人次与总请假天数）。"""
        department = getattr(user, "department", None)
        if department is None:
            return "当前用户未分配部门，无法统计部门请假情况。"
        today = timezone.now().date()
        since = today - timedelta(days=max(1, min(int(days or 30), 365)))
        rows = list(
            Absent.objects.filter(
                requester__department=department,
                statar_date__lte=today,
                end_date__gte=since,
            ).select_related("absent_type", "requester")
        )
        if not rows:
            return f"部门「{department.name}」近 {days} 天请假统计：无请假记录。"
        per_type: dict[str, tuple[int, int]] = {}
        total_days = 0
        for absent in rows:
            overlap_start = max(absent.statar_date, since)
            overlap_end = min(absent.end_date, today)
            overlap_days = max((overlap_end - overlap_start).days + 1, 1)
            total_days += overlap_days
            count, days_sum = per_type.get(absent.absent_type.name, (0, 0))
            per_type[absent.absent_type.name] = (count + 1, days_sum + overlap_days)
        lines = [
            f"部门「{department.name}」近 {days} 天请假统计：共 {len(rows)} 人次，合计 {total_days} 天。"
        ]
        for name, (count, days_sum) in sorted(per_type.items(), key=lambda item: item[1][1], reverse=True):
            lines.append(f"- {name}：{count} 人次，{days_sum} 天")
        return "\n".join(lines)

    return [query_my_leaves, query_my_pending_approvals, query_department_leave_stats]


def try_tool_call(user, question: str, *, enabled: bool | None = None):
    """尝试工具决策与执行。

    返回 (是否命中工具, 工具结果文本, 工具调用信息列表)。
    任何失败都返回未命中，由调用方降级为纯 RAG。
    """
    if not getattr(user, "is_authenticated", False):
        return False, "", []
    if enabled is False or (enabled is None and not _tools_enabled()):
        return False, "", []
    if not _triggered(question):
        return False, "", []
    if _LANGCHAIN_AVAILABLE is False or get_chat_model is None or tool is None:
        return False, "", []
    try:
        tools = build_oa_tools(user)
        llm = get_chat_model(temperature=0, max_tokens=256)
        llm_with_tools = llm.bind_tools(tools)
        response = llm_with_tools.invoke([HumanMessage(content=question)])
        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            return False, "", []

        tool_map = {item.name: item for item in tools}
        parts: list[str] = []
        call_info: list[dict] = []
        for call in tool_calls[:3]:
            name = call.get("name") or ""
            args = call.get("args") or {}
            item = tool_map.get(name)
            if item is None:
                continue
            try:
                result = item.invoke(args)
                parts.append(f"【{name}】\n{result}")
                call_info.append({"name": name, "args": args})
            except Exception as exc:  # noqa: BLE001
                parts.append(f"【{name}】执行失败：{exc}")
                call_info.append({"name": name, "args": args, "error": str(exc)})
        if not parts:
            return False, "", []
        return True, "\n\n".join(parts)[:4000], call_info
    except Exception:  # noqa: BLE001
        logger.warning("Agent 工具决策失败，降级为纯 RAG", exc_info=True)
        return False, "", []
