from APPS.absent.models import AbsentStatusChoices


def _get_dept(user):
    """安全获取部门对象，避免 department 为 NULL 时访问属性导致 500"""
    return getattr(user, "department", None)


# 创建请假单专用（需要修改单据状态）
def get_responder(request, validated_data):
    user = request.user
    dept = _get_dept(user)
    if dept is None:
        # 无部门用户：无审批人，单据进入待审批
        responder = None
        validated_data["status"] = AbsentStatusChoices.AUDITING
        return responder
    if dept.leader_id == user.uid:
        if dept.name == "董事会":
            responder = None
            validated_data["status"] = AbsentStatusChoices.PASS
        else:
            responder = dept.manager
            validated_data["status"] = AbsentStatusChoices.AUDITING
    else:
        responder = dept.leader
        validated_data["status"] = AbsentStatusChoices.AUDITING
    return responder


# 查询审批人专用（仅返回审批人，不操作状态）
def get_responder_simple(request):
    user = request.user
    dept = _get_dept(user)
    if dept is None:
        return None
    if dept.leader_id == user.uid:
        if dept.name == "董事会":
            responder = None
        else:
            responder = dept.manager
    else:
        responder = dept.leader
    return responder
