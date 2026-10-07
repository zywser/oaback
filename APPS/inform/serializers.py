import re

from django.template.context_processors import request
from rest_framework import serializers


from .models import Inform, InformRead
from APPS.oaauth.serializers import UserSerializer, OADepartmentSerializer
from APPS.oaauth.models import OADepartment


class InformReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = InformRead
        fields = "__all__"


class InformSerializers(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    departments = OADepartmentSerializer(many=True, read_only=True)
    # department_ids： 是包含了部门id的列表
    # 如果后端要接收列表，那么就需要ListField
    department_ids = serializers.ListField(write_only=True)
    reads = InformReadSerializer(many=True, read_only=True)
    # content 为普通可写字段（发布时正常入库）；图片 host 归一化在 to_representation 输出时处理，
    # 把 /media/ 前缀的绝对 host 替换为当前请求 host，保证换环境后图片可访问。

    class Meta:
        model = Inform
        fields = "__all__"
        read_only_fields = ("public",)



    # 重写保存Inform对象的create方法
    def create(self, validated_data):
        request = self.context["request"]
        department_ids = validated_data.pop("department_ids")

        map(lambda value:int(value),department_ids)
        if 0 in department_ids:
            inform = Inform.objects.create(public=True,author=request.user,**validated_data)
        else:
            departments = OADepartment.objects.filter(id__in=department_ids).all()
            inform = Inform.objects.create(public=False,author=request.user,**validated_data)
            inform.departments.set(departments)
            inform.save()
        return  inform

    def to_representation(self, instance):
        # 输出时把 /media/ 前缀的绝对 host 归一化为当前请求 host，保证换环境后图片可访问
        data = super().to_representation(instance)
        content = data.get("content") or ""
        if not content:
            return data
        request = self.context.get("request")
        if request is None:
            return data
        try:
            current_host = f"{request.scheme}://{request.get_host()}"
            data["content"] = re.sub(r"(https?://[^/\"']+)(?=/media/)", current_host, content)
        except Exception:
            # Host 头异常（如不在 ALLOWED_HOSTS）时放弃归一化，避免整个接口 500
            pass
        return data



class ReadInformSerializer(serializers.Serializer):
    inform_pk = serializers.IntegerField(error_messages={"required":"请传入inform的id！"})
