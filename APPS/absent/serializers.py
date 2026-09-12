from rest_framework import serializers
from rest_framework import exceptions


from .models import Absent,AbsentType,AbsentStatusChoices
from APPS.oaauth.serializers import UserSerializer
from .utlis import get_responder



class AbsentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = AbsentType
        fields = "__all__"


class AbsentSerializer(serializers.ModelSerializer):
    # read_only: 这个参数，只会在将ORM模型系列化成字典时会将这个字段序列化
    # write_only：这个参数，只会在将data进行校验的时候再回用到

    absent_type = AbsentTypeSerializer(read_only=True)
    absent_type_id = serializers.IntegerField(write_only=True)
    requester = UserSerializer(read_only=True)
    responder = UserSerializer(read_only=True)
    class Meta:
        model = Absent
        fields = "__all__"


    def validate_absent_type_id(self, attrs):
        exists = AbsentType.objects.filter(pk=attrs).exists()
        if not  exists:
            raise exceptions.ValidationError("考勤类型不存在")
        return attrs








    # create
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        # 获取审批者
        responder = get_responder(request, validated_data)

        absent = Absent.objects.create(**validated_data,requester=user,responder=responder)
        return absent






    #updata
    def update(self, instance, validated_data):
        if instance.status != AbsentStatusChoices.AUDITING:
            raise exceptions.APIException(detail="不能修改已经确定的请假数据！")

        requester = self.context["request"]
        user = requester.user
        if instance.responder.uid != user.uid:
            raise  exceptions.AuthenticationFailed(detail="您无权处理改考勤！")
        instance.status = validated_data["status"]
        instance.response_content = validated_data["response_content"]
        instance.save()
        return instance


