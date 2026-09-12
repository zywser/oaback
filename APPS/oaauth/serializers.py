from rest_framework import serializers
from rest_framework import  exceptions

from .models import OAUser, UserStatusChoices,OADepartment


class LoginSerializer(serializers.Serializer):
    # 定义需要序列化的字段名，serializers会自动验证
    email = serializers.EmailField(required=True,error_messages={'required': '请输入邮箱！'})
    password = serializers.CharField(max_length=20, min_length=6,error_messages={'required': '请输入密码！'})

    def validate(self, attrs):
        """
        重写了对象级别的验证方法。
        当 DRF 完成上述字段的初步校验后，
        会将所有合法数据放入 attrs 字典中

        传入此方法，
        供你进行复杂的联合业务逻辑校验。
        """

        # 从校验通过的数据字典 attrs 中安全地提取出邮箱和密码变量。
        email = attrs.get("email")
        password = attrs.get("password")


        # 调用 User 模型类的校验方法，如果校验失败，抛出验证异常。
        if email and password:   # 如果email和password都不为空
            user = OAUser.objects.filter(email=email).first() # 查询OAUser表中email字段为email的记录，返回第一条
            if not user:   # 如果user不存在
                raise serializers.ValidationError("用户不存在！")

            if not user.check_password(password):  #
                raise serializers.ValidationError("密码错误")

            # 判断状态
            if user.status == UserStatusChoices.LOCKED:  # 如果用户状态为锁定
                raise serializers.ValidationError("账户已被锁定！")
            elif user.status == UserStatusChoices.UNACTIVE:  # 如果用户状态为未激活
                raise serializers.ValidationError("账户未激活！请联系管理员！")

            # 为了节省SQL语句查询次数，这里我们把User直接放在attrs中，方便在视图中使用
            attrs["user"] = user

        else:
            raise serializers.ValidationError("请输入用户名和密码！") # 如果email或password为空，抛出验证异常
        return attrs  # 如果所有校验均通过，返回更新后的 attrs 字典（里面现在包含了 email, password 以及 user 对象）。




class OADepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = OADepartment
        fields = "__all__"


class UserSerializer(serializers.ModelSerializer):
    """
    用户序列化器,用于返回用户数据
    """
    department = OADepartmentSerializer()
    class Meta:
        model = OAUser
        exclude = ["password", "groups", "user_permissions"]


class ResetPwdSerializer(serializers.Serializer):
    oldpwd =serializers.CharField(max_length=20,min_length=6)
    newpwd = serializers.CharField(max_length=20,min_length=6)
    newpwd2 = serializers.CharField(max_length=20,min_length=6)

    def validate(self, attrs):
        oldpwd = attrs["oldpwd"]
        newpwd = attrs["newpwd"]
        newpwd2 = attrs["newpwd2"]

        user = self.context["request"].user
        if not user.check_password(oldpwd):
            raise exceptions.ValidationError("旧密码错误！")

        if newpwd != newpwd2:
            raise exceptions.ValidationError("两次密码不一致！")
        return  attrs


