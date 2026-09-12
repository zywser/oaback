from django.shortcuts import render
from rest_framework.views import APIView
from  datetime import datetime
from rest_framework.response import Response
from rest_framework import status

from .serializers import LoginSerializer,UserSerializer,ResetPwdSerializer
from .authentications import generate_jwt



class LoginView(APIView):
    """登录视图"""
    def post(self,request):
        # POST请求逻辑
       serializer = LoginSerializer(data=request.data)  # 创建序列化对象


       if serializer.is_valid():  # 如果序列化验证成功
           user = serializer.validated_data.get("user") # 获取用户对象
           user.last_login = datetime.now() # 更新用户最后登录时间
           user.save()  # 保存用户对象
           token = generate_jwt(user) # 生成JWT token
           return Response({"token":token,"user":UserSerializer(user).data})
       else:
           print(serializer.errors)
           # def 返回响应是非200的时候，他的参数名为 detail 所有这里我们也改为detail，保持一致
           detail = list(serializer.errors.values())[0][0]

           return Response({"detail":detail},status = status.HTTP_400_BAD_REQUEST)


class ResetPwdView(APIView):
    def post(self,request):
        serializer= ResetPwdSerializer(data=request.data,context={"request":request})
        if serializer.is_valid():
           newpwd = serializer.validated_data.get("newpwd")
           request.user.set_password(newpwd)
           request.user.save()
           return  Response({"密码修改成功"})

        print(serializer.errors)
        detail = list(serializer.errors.values())[0][0]
        return  Response({"detail":detail},status=status.HTTP_400_BAD_REQUEST)
