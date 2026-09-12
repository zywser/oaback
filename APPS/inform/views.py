from rest_framework import viewsets, status
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Prefetch
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator

from .models import Inform, InformRead
from .serializers import InformSerializers, ReadInformSerializer


class InformViewSet(viewsets.ModelViewSet):
    queryset = Inform.objects.all()
    serializer_class = InformSerializers

    def get_queryset(self):
        #  get_queryset：获取数据集方法

        # inform.publish = True  这种情况代表所有人都能看见
        # inform.departments     这种情况代表一个部门的可以看见，不是一个部门的看不见。
        # inform.author = request.user    这种情况代表通知是我自己发布的，我自己也要能看到

        # 如果多个条件并查，可以使用Q函数
        queryset = self.queryset.select_related("author").prefetch_related(
            Prefetch("reads", queryset=InformRead.objects.filter(user_id=self.request.user.uid)), "departments").filter(
            Q(public=True) | Q(departments=self.request.user.department) | Q(author=self.request.user)).distinct()
        return queryset

    def destroy(self, request, *args, **kwargs):
        # destroy：删除方法

        # 1. 获取前端想要删除的那条通知记录实例
        instance = self.get_object()

        # 2. 判断：这条通知的发布人uid == 当前登录用户uid
        if instance.author.uid == request.user.uid:
            # 3. 校验通过，执行删除（底层调用 instance.delete()）
            self.perform_destroy(instance)
            # 返回成功无内容 204
            return Response(status=status.HTTP_204_NO_CONTENT)
        else:
            # 4. 不是本人发布，无权删除，返回401未授权
            return Response(status=status.HTTP_401_UNAUTHORIZED)

    def retrieve(self, request, *args, **kwargs):
        # retrieve：查询单条数据方法
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        data["read_count"] = InformRead.objects.filter(inform_id=instance.id).count()
        return Response(data=data)


class ReadInformView(APIView):
    def post(self, request):
        serializer = ReadInformSerializer(data=request.data)
        if serializer.is_valid():  # 如果数据验证成功
            inform_pk = serializer.validated_data.get("inform_pk")  # 获取主键（inform_pk）
            # 查找数据库这条数据是否存在
            exists = InformRead.objects.filter(inform_id=inform_pk, user_id=request.user.uid).exists()
            if exists:  # 如果存在
                return Response()  # 什么都不干，返回200
            else:  # 如果不存在

                # 进行异常处理
                try:
                    InformRead.objects.create(inform_id=inform_pk, user_id=request.user.uid)  # 写入数据库，表示阅读量+1

                except Exception as e:  # 如果出现异常（写入失败）
                    print(e)  # 打印错误信息
                    return Response(data={"detail": "阅读失败！"}, status=status.HTTP_400_BAD_REQUEST)  # 返回错误信息和400状态码
                return Response()  # 存储完成后返回状态码200
        else:
            # 如果数据没有验证成功，就直接返回错误信息和400状态码
            return Response(data={"detail": list(serializer.errors.values())[0][0]}, status=status.HTTP_400_BAD_REQUEST)
