from django.shortcuts import render
from django.views import View
from rest_framework.views import APIView
from django.db.models import Q, Prefetch
from rest_framework.response import Response
from django.db.models import Count
#缓存
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator


from APPS.inform.models import Inform, InformRead
from APPS.inform.serializers import InformSerializers
from APPS.absent.models import Absent
from APPS.absent.serializers import AbsentSerializer
from APPS.oaauth.models import OADepartment


API_DOC_SECTIONS = [
    {
        "anchor": "auth",
        "title": "认证",
        "endpoints": [
            {
                "method": "POST",
                "path": "/auth/login",
                "auth": "否",
                "summary": "邮箱密码登录，返回 JWT 和用户信息。",
                "request": '{\n  "email": "user@example.com",\n  "password": "123456"\n}',
                "response": '{\n  "token": "JWT...",\n  "user": {...}\n}',
            },
            {
                "method": "POST",
                "path": "/auth/resetpwd",
                "auth": "是",
                "summary": "修改当前登录用户密码。",
                "request": '{\n  "oldpwd": "123456",\n  "newpwd": "654321",\n  "newpwd2": "654321"\n}',
                "response": '{\n  "密码修改成功"\n}',
            },
        ],
    },
    {
        "anchor": "absent",
        "title": "请假",
        "endpoints": [
            {
                "method": "GET",
                "path": "/absent/absent/",
                "auth": "是",
                "summary": "查看请假列表，默认查自己；传 `who=sub` 查下属。",
                "request": 'query: who=sub | who=my',
                "response": "[{...}]",
            },
            {
                "method": "POST",
                "path": "/absent/absent/",
                "auth": "是",
                "summary": "发起请假申请。",
                "request": '{\n  "title": "年假",\n  "request_content": "请假事由",\n  "absent_type_id": 1,\n  "statar_date": "2026-08-18",\n  "end_date": "2026-08-20"\n}',
                "response": "{...请假对象...}",
            },
            {
                "method": "PATCH",
                "path": "/absent/absent/{id}/",
                "auth": "是",
                "summary": "审批请假，只允许当前审批人修改状态和回复。",
                "request": '{\n  "status": 2,\n  "response_content": "同意"\n}',
                "response": "{...请假对象...}",
            },
            {
                "method": "GET",
                "path": "/type",
                "auth": "是",
                "summary": "请假类型列表。",
                "request": "-",
                "response": "[{...}]",
            },
            {
                "method": "GET",
                "path": "/responder",
                "auth": "是",
                "summary": "获取当前请假的审批人。",
                "request": "-",
                "response": '{\n  "responder": {...} | null,\n  "tip": "..."\n}',
            },
        ],
    },
    {
        "anchor": "inform",
        "title": "通知",
        "endpoints": [
            {
                "method": "GET",
                "path": "/inform/inform/",
                "auth": "是",
                "summary": "通知列表，自动过滤当前用户可见内容。",
                "request": "-",
                "response": "[{...}]",
            },
            {
                "method": "POST",
                "path": "/inform/inform/",
                "auth": "是",
                "summary": "发布通知，`department_ids` 里含 `0` 表示全员可见。",
                "request": '{\n  "title": "通知标题",\n  "content": "通知正文",\n  "department_ids": [0]\n}',
                "response": "{...通知对象...}",
            },
            {
                "method": "GET",
                "path": "/inform/inform/{id}/",
                "auth": "是",
                "summary": "查看单条通知，额外返回阅读人数。",
                "request": "-",
                "response": "{...通知对象..., \"read_count\": 0}",
            },
            {
                "method": "PATCH",
                "path": "/inform/inform/{id}/",
                "auth": "是",
                "summary": "更新通知。",
                "request": "{...}",
                "response": "{...}",
            },
            {
                "method": "DELETE",
                "path": "/inform/inform/{id}/",
                "auth": "是",
                "summary": "删除通知，仅作者可删。",
                "request": "-",
                "response": "204 No Content",
            },
            {
                "method": "POST",
                "path": "/inform/inform/read/",
                "auth": "是",
                "summary": "标记通知已读。",
                "request": '{\n  "inform_pk": 1\n}',
                "response": "{}",
            },
        ],
    },
    {
        "anchor": "staff",
        "title": "员工",
        "endpoints": [
            {
                "method": "GET",
                "path": "/staff/departments",
                "auth": "是",
                "summary": "部门列表。",
                "request": "-",
                "response": "[{...}]",
            },
            {
                "method": "GET",
                "path": "/staff/staff",
                "auth": "是",
                "summary": "员工列表，支持按部门、姓名、入职日期筛选。",
                "request": 'query: department_id, realname, data_joined[]',
                "response": "{count, next, previous, results}",
            },
            {
                "method": "POST",
                "path": "/staff/staff",
                "auth": "是",
                "summary": "新增员工并发送激活邮件，只有部门负责人可操作。",
                "request": '{\n  "realname": "张三",\n  "email": "zhangsan@example.com",\n  "password": "123456"\n}',
                "response": "{}",
            },
            {
                "method": "PATCH",
                "path": "/staff/staff/{id}",
                "auth": "是",
                "summary": "更新员工信息，支持部分字段修改。",
                "request": "{...UserSerializer字段...}",
                "response": "{...}",
            },
            {
                "method": "GET",
                "path": "/staff/active?token=...",
                "auth": "否",
                "summary": "员工激活页，邮箱链接会跳到这里。",
                "request": "-",
                "response": "HTML 页面",
            },
            {
                "method": "POST",
                "path": "/staff/active",
                "auth": "否",
                "summary": "提交激活表单。",
                "request": 'form: email, password',
                "response": '{\n  "code": 200,\n  "message": "激活成功！"\n}',
            },
            {
                "method": "GET",
                "path": "/staff/celery/text",
                "auth": "是",
                "summary": "测试 Celery 任务。",
                "request": "-",
                "response": '{\n  "detail": "OK!"\n}',
            },
            {
                "method": "GET",
                "path": "/staff/download?pks=[]",
                "auth": "是",
                "summary": "导出员工 Excel。",
                "request": 'query: pks=[1,2,3]',
                "response": "Excel 文件",
            },
            {
                "method": "POST",
                "path": "/staff/upload",
                "auth": "是",
                "summary": "导入员工 Excel。",
                "request": "multipart/form-data: file=xlsx/xls",
                "response": '{\n  "detail": "成功导入N位员工"\n}',
            },
        ],
    },
    {
        "anchor": "image",
        "title": "图片",
        "endpoints": [
            {
                "method": "POST",
                "path": "/image/upload",
                "auth": "是",
                "summary": "上传图片，供编辑器回传 URL。",
                "request": "multipart/form-data: image",
                "response": '{\n  "errno": 0,\n  "data": {\n    "url": "/media/...",\n    "alt": "",\n    "href": "/media/..."\n  }\n}',
            },
        ],
    },
    {
        "anchor": "home",
        "title": "首页统计",
        "endpoints": [
            {
                "method": "GET",
                "path": "/home/latest/inform",
                "auth": "是",
                "summary": "最近 10 条通知。",
                "request": "-",
                "response": "[{...}]",
            },
            {
                "method": "GET",
                "path": "/home/latest/absent",
                "auth": "是",
                "summary": "最近 10 条请假记录。",
                "request": "-",
                "response": "[{...}]",
            },
            {
                "method": "GET",
                "path": "/home/department/staff/count",
                "auth": "是",
                "summary": "部门员工数量统计。",
                "request": "-",
                "response": '[{"name": "...", "staff_count": 0}]',
            },
        ],
    },
]


class ApiDocsView(View):
    def get(self, request):
        default_anchor = "home"
        sections = sorted(
            API_DOC_SECTIONS,
            key=lambda section: section["anchor"] != default_anchor,
        )
        return render(
            request,
            "docs/index.html",
            {
                "sections": sections,
                "default_anchor": default_anchor,
            },
        )

# @cache_page[60*15]
# def text(APIView):
#     pass

class LatestInformView(APIView):
    """返回最新10条通知"""
    def get(self,request):
        current_user = request.user
        informs = Inform.objects.prefetch_related(Prefetch("reads",queryset=InformRead.objects.filter(user_id=current_user.uid)),"departments").filter(Q(public=True) | Q(departments=current_user.department))[:10]
        serializer = InformSerializers(informs,many=True)
        return Response(serializer.data)








class LatestAbsentView(APIView):
    """返回考勤信息"""

    def get(self,request):
        # 董事会的人，可以看到所有人的考勤信息，非董事会的人只能看到自己部门的信息
        # （用户无部门时只返回自己发起的请假，避免 500）
        current_user = request.user
        queryset = Absent.objects
        dept = current_user.department
        if dept is None:
            queryset = queryset.filter(requester_id=current_user.uid)
        elif dept.name != "董事会":
            queryset = queryset.filter(requester__department_id=current_user.department_id)
        queryset=queryset.all()[:10]
        serializer = AbsentSerializer(queryset,many=True)
        return Response(serializer.data)






class DepartmentStaffCountView(APIView):
    """员工统计"""

    @method_decorator(cache_page(60 * 5))
    def get(self,request):
        rows = OADepartment.objects.annotate(staff_count=Count("staffs")).values("name","staff_count")
        print(rows)
        print("张海毅")
        return  Response(rows)


# apps/home/views.py  安全检查
class HealthCheckView(APIView):
    def get(self, request):
        return Response({"code": 200})

