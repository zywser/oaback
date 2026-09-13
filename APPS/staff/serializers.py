from django.core.validators import FileExtensionValidator
from rest_framework import serializers
from APPS.oaauth.models import OAUser


class AddStaffSerializer(serializers.Serializer):
    realname = serializers.CharField(max_length=20,error_messages={"required":"请输入用户名！"})
    email = serializers.EmailField(error_messages={"required":"请输入邮箱","invalid":"请输入正确格式的邮箱！"})
    password = serializers.CharField(max_length=20,error_messages={"required":"请输入密码！"})

    def validate(self, attrs):
        request = self.context["request"]
        email = attrs.get("email")
        # 1. 验证邮箱是否存在
        email_exists = OAUser.objects.filter(email=email).exists()
        if email_exists:
            raise serializers.ValidationError("该邮箱已存在！")

        # 2.验证当前用户是否是部门的leader（部门为空或非leader → 无权限，避免 500）
        dept = request.user.department
        if dept is None or dept.leader_id != request.user.uid:
            raise serializers.ValidationError("非部门领导，不能添加员工！")
        return attrs



class ActiveStaffSerializer(serializers.Serializer):
    email = serializers.EmailField(error_messages={"required": "请输入邮箱", "invalid": "请输入正确格式的邮箱！"})
    password = serializers.CharField(max_length=20, error_messages={"required": "请输入密码！"})

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        user = OAUser.objects.filter(email=email).first()

        if not user or not user.check_password(password):
            raise serializers.ValidationError("邮箱或密码错误！")

        attrs["user"] = user
        return  attrs


class StaffUpLoadSerializer(serializers.Serializer):
    file = serializers.FileField(
        validators=[FileExtensionValidator(["xlsx", "xls"])],
        error_messages={"required": "请上传正确的文件！",}
    )
