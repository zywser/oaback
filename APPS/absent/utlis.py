from APPS.absent.models import AbsentStatusChoices

# 创建请假单专用（需要修改单据状态）
def get_responder(request, validated_data):
    user = request.user
    if user.department.leader.uid == user.uid:
        if user.department.name == "董事会":
            responder = None
            validated_data["status"] = AbsentStatusChoices.PASS
        else:
            responder = user.department.manager
            validated_data["status"] = AbsentStatusChoices.AUDITING
    else:
        responder = user.department.leader
        validated_data["status"] = AbsentStatusChoices.AUDITING
    return responder

# 查询审批人专用（仅返回审批人，不操作状态）
def get_responder_simple(request):
    user = request.user
    if user.department.leader.uid == user.uid:
        if user.department.name == "董事会":
            responder = None
        else:
            responder = user.department.manager
    else:
        responder = user.department.leader
    return responder