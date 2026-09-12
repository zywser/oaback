"""知识库访问控制（鉴权 / 可见性）。

包含董事会判定、单条知识源可见性与知识源查询集的权限过滤。
"""
from django.db.models import Q

from ..models import AgentKnowledgeSource


def is_boarder(user) -> bool:
    department = getattr(user, "department", None)
    return bool(department and department.name == "董事会")


def _source_is_accessible(user, source: AgentKnowledgeSource) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if is_boarder(user):
        return True
    if source.is_public:
        return True
    if source.author_id == user.uid:
        return True
    department_id = getattr(getattr(user, "department", None), "id", None)
    if department_id and source.departments.filter(id=department_id).exists():
        return True
    return False


def accessible_sources_queryset(user):
    queryset = AgentKnowledgeSource.objects.prefetch_related("departments", "chunks")
    if is_boarder(user):
        return queryset

    department = getattr(user, "department", None)
    filters = Q(is_public=True) | Q(author=user)
    if department is not None:
        filters |= Q(departments=department)
    return queryset.filter(filters).distinct()
