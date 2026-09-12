from  rest_framework import mixins
from rest_framework.viewsets import GenericViewSet
from rest_framework.response import Response
from  rest_framework.views import APIView


from .models import Absent,AbsentType,AbsentStatusChoices
from .serializers import AbsentSerializer,AbsentTypeSerializer
from .utlis import  get_responder_simple
from APPS.oaauth.serializers import UserSerializer



# Create your views here.

# 1.发起考勤（create）
# 2.处理考勤（update）
# 3.查看自己的考勤列表（list?who=my）
# 4.查看下属的考勤列表（list?who=sub）

class AbsentViewSet(mixins.CreateModelMixin,



                   mixins.UpdateModelMixin,
                   mixins.ListModelMixin,
                   GenericViewSet):

    queryset = Absent.objects.all()
    serializer_class = AbsentSerializer

    def update(self, request, *args, **kwargs):
        """默认情况下，如果修改某一条数据，那么要把序列化中指定的字段都上传
        如果想要修改一部分数据，那么可以在kwargs中设置partial=True
        """
        kwargs["partial"] = True
        return super().update(request,*args,**kwargs)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        who = request.query_params.get("who")

        if who and who=="sub":
            results = queryset.filter(responder=request.user)
        else:
            results= queryset.filter(requester = request.user)


            # 分页
            #  result：代表符合要求的数据
            # get_serializer方法：会做分页逻辑
        page = self.paginate_queryset(results)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            # get_paginated_response()：除了返回序列化的数据，还会返回总数据是多少，上一页url是多少
            return self.get_paginated_response(serializer.data)

        serializer = self.serializer_class(results,many=True)
        return  Response(data=serializer.data)

# 1. 请假类型
class AbsentTypeView(APIView):
    def get(self,request):
        types = AbsentType.objects.all()
        serializer = AbsentTypeSerializer(types,many=True)
        return Response(serializer.data)



# 2. 显示审批者
class ResponderView(APIView):
    def get(self, request):
        responder = get_responder_simple(request)
        # 处理董事会responder为None的序列化报错
        if responder is None:
            return Response({
                "responder": None,
                "tip": "董事会领导无需审批人"
            })
        serializers = UserSerializer(responder)
        return Response(serializers.data)