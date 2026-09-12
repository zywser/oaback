from django.core.serializers import serialize
from django.template.context_processors import request
from numpy.ma.core import append
from rest_framework.generics import ListAPIView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import send_mail
from django.conf import settings
from django.urls import reverse
from django.shortcuts import render
from django.views import View
from django.http.response import JsonResponse
from urllib import parse
from rest_framework.generics import ListCreateAPIView,UpdateAPIView
from rest_framework import exceptions
from rest_framework import viewsets
from rest_framework import mixins
from datetime import datetime
import json
import pandas as  pd
from django.http import HttpResponse
from django.db import transaction


from APPS.oaauth.models import OADepartment
from APPS.oaauth.serializers import OADepartmentSerializer
from .serializers import AddStaffSerializer,ActiveStaffSerializer,StaffUpLoadSerializer
from APPS.oaauth.models import OAUser,UserStatusChoices
from utils import aeser
from OAback.celery import debug_task
from .tasks import send_mail_task
from APPS.oaauth.serializers import UserSerializer
from .paginations import StaffPagination

aes = aeser.AESer(settings.SECRET_KEY)


def send_active_email(request, email):
    """发送邮件逻辑"""
    token = aes.encrypt(email)
    active_path = reverse("staff:active_staff") + "?" + parse.urlencode({"token": token})
    active_url = request.build_absolute_uri(active_path)

    message = f"请点击以下链接激活账号：{active_url}"
    subject = f"【XXXXX】账号激活"

    # send_mail(subject, recipient_list=[email], message=message, from_email=settings.DEFAULT_FROM_EMAIL)
    send_mail_task.delay(email, subject, message)  # 使用异步任务必须加上delay()


class DepartmentListView(ListAPIView):
    queryset = OADepartment.objects.all()
    serializer_class = OADepartmentSerializer




class StaffViewSet(
    viewsets.GenericViewSet,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin
                ):
    queryset = OAUser.objects.all()
    pagination_class = StaffPagination

    def get_serializer_class(self):
        if self.request.method in ["GET","PUT"]:
            return UserSerializer
        else:
            return AddStaffSerializer

    # 获取员工列表
    def get_queryset(self):
        print(self.request.query_params)
        department_id = self.request.query_params.get("department_id")
        realname = self.request.query_params.get("realname")
        date_joined = self.request.query_params.getlist("data_joined[]")


        queryset = self.queryset
        # 返回员工逻辑：
        # 1. 如果是董事会的，那么返回所以员工
        # 2. 如果不是董事会的，但是是部门到的leader，那么就返回部门的员工
        # 3. 如果不是董事会的，也不是部门的leader，那么就抛出403 Forbidden（没有权限）错误
        user = self.request.user
        if user.department.name !="董事会":
            if user.uid != user.department.leader.uid:
                raise exceptions.PermissionDenied()
            else:
                queryset = queryset.filter(department_id=user.department_id)
        else:
            if department_id:
                queryset = queryset.filter(department_id=department_id)


        if realname:
            queryset = queryset.filter(realname__icontains=realname)

        if date_joined:
            try:
                start_data = datetime.strptime(date_joined[0],"%Y-%m-%d")
                end_data = datetime.strptime(date_joined[1],"%Y-%m-%d")
                queryset = queryset.filter(date_joined__range=(start_data,end_data.replace(hour=23,minute=59,second=59)))
            except Exception  :
                pass
        return queryset.order_by("-date_joined").all()


    # 添加员工
    def create(self, request,*args,**kwargs):
        # 如果用的是视图集（ListAPIView）,那么视图集会自动把request放到context中
        # 如果直接继承自APIView，那么就需要手动将request对象传给serializer.context中
        serializer = AddStaffSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            # 获取验证完成的数据
            realname = serializer.validated_data["realname"]
            email = serializer.validated_data["email"]
            password = serializer.validated_data["password"]

            # 把获取到的数据保存到数据库
            user = OAUser.objects.create_user(email=email, realname=realname, password=password)  # 创建用户
            department = request.user.department  # 获取当前用户部门信息
            user.department = department  # 把获取到的部门信息赋值给创建好的用户的部门
            user.save()

            # 发送邮箱链接
            send_active_email(request,email)
            return Response()

        else:
            return Response(data={"detail", list(serializer.errors.values())[0][0]}, status=status.HTTP_400_BAD_REQUEST)



    def update(self, request, *args, **kwargs):
        """默认情况下，如果修改某一条数据，那么要把序列化中指定的字段都上传
        如果想要修改一部分数据，那么可以在kwargs中设置partial=True
        """
        kwargs["partial"] = True
        return super().update(request,*args,**kwargs)


    # 删除员工
    def destroy(self, request, *args, **kwargs):
        # get_object 内部会先按 get_queryset() 做权限过滤：
        # 董事会可删除任意员工，部门 leader 只能删除本部门员工
        instance = self.get_object()
        # 不允许删除当前登录账号自己
        if instance.pk == request.user.pk:
            raise exceptions.PermissionDenied("不能删除当前登录账号！")
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)







class ActiveStaffView(View):
    """
    激活员工的过程：
    1.用户访问激活链接的时候，会返回一个含有表单的页面，视图中可以获取到token，为了用户提交表单的时候，post函数中能知道这个token
    我们可以子啊返回页面之前，先把token存在cookie中
    2. 校验用户上传的邮箱和密码是否正确，并且解密token中的邮箱，与用户提交的邮箱进行对比，如果都相同，那么激活成功
    """
    def get(self, request):
        # 获取token，并把token存储在cookie中，方便下次用户传过来
        token = request.GET.get("token")
        response = render(request, "staff/active.html")
        response.set_cookie("token",token)
        return response
    def post(self,request):
        """从cookie中获取token"""
        try:
            token = request.COOKIES.get("token")   # 获取token
            email = aes.decrypt(token)  #解密邮箱
            serializer = ActiveStaffSerializer(data=request.POST)  # 使用Django的request.POST方法获取request对象
            if serializer.is_valid():
                form_email = serializer.validated_data.get("email")  # 表单邮箱
                user = serializer.validated_data.get("user")

                if email != form_email:
                    return JsonResponse({"code":400,"mesage":"邮箱错误"})
                user.status = UserStatusChoices.ACTIVED
                user.save()
                return JsonResponse({"code":200,"message":"激活成功！"})
            else:
                detail = list(serializer.errors.values())[0][0]
                return JsonResponse({"code":400,"message":detail})

        except Exception as e:
            return JsonResponse({"code":400,"message":"token错误！"})







class CeleryTextView(APIView):
    def get(self,request):
        debug_task.delay()
        return Response({"detail":"OK!"})




class StaffDownLoadView(APIView):
    def get(self,request):
        #----------------过滤字段--------------------
        pks = request.query_params.get("pks")  #通过pks字段来获取数据
        try:
            pks = json.loads(pks)  # 把oks转换成json格式
        except Exception:
            # 转换不了就抛出异常
            return  Response({"detail":"员工参数错误！！"},status=status.HTTP_400_BAD_REQUEST)



        try:
            # 获取用户对象和指定queryset对象
            current_user = request.user
            queryset = OAUser.objects

            # ---------------权限校验----------------------
            if current_user.department.name != "董事会":
            # 判断部门名称是不是叫 “董事会”
                if current_user.department.leader_id != current_user.uid:
                # 如果登录的用户的领导的uid不等于当前登录用户的uid
                    return Response({"detail":"没有权限下载!"}, status=status.HTTP_403_FORBIDDEN)
                else:
                    # 如果是部门leader，那么就先过滤本部门的员工
                    queryset = queryset.filter(department_id=current_user.department_id)

            # 如果是董事会，执行以下操作
            # 筛选pks字段传过来的数据，在pk这个字段名容器中查找
            queryset = queryset.filter(pk__in=pks)
            # 使用.values方法查找我们指定的字段，并得到result对象
            result = queryset.values("realname", "email", "department__name", "date_joined", "status")


            #------------------------------下载Excel---------------------------
            # 使用 pd.DataFrame把result对象转化成DataFrame对象（因为result是queryset对象，所以使用list（）转换成列表对象）
            staff_df = pd.DataFrame(list(result))
            # 使用pandas中的.rename方法把我们的字段名写成中文
            staff_df = staff_df.rename(columns={"realname": "真实姓名",
                 "email": "邮箱",
                 "department__name": "部门名称",
                 "date_joined": "入职时间",
                 "status": "状态"})
            # 使用Django自带的HttpResponse构建Excel 文件下载响应
            # 作用：用来告诉浏览器：本次接口返回的内容不是普通 JSON / 网页，而是 .xlsx Excel 文件，浏览器会自动触发下载弹窗。
            response = HttpResponse(content_type="application/xlsx")
            response['Content-Disposition'] = 'attachment; filename="员工信息.xlsx"'

            # 把员工的staff_df写入到Response
            with pd.ExcelWriter(response) as writer:
                staff_df.to_excel(writer, sheet_name="员工信息")
            return response
        except Exception as  e:
            print(e)
            return Response({"detail":str(e)},status=status.HTTP_400_BAD_REQUEST)




class StaffUpLoadView(APIView):
    def post(self, request):
        # 1. 校验上传文件
        serializer = StaffUpLoadSerializer(data=request.data)
        if not serializer.is_valid():
            # 取出第一条错误信息
            first_err = next(iter(serializer.errors.values()))[0]
            return Response({"detail": first_err}, status=status.HTTP_400_BAD_REQUEST)

        file = serializer.validated_data.get("file")
        current_user = request.user

        # 2. 权限校验：非董事会 且 不是部门leader 禁止导入
        dept = current_user.department
        if dept.name != "董事会" and dept.leader_id != current_user.uid:
            return Response({"detail": "您没有权限导入员工！！"}, status=status.HTTP_403_FORBIDDEN)

        # 初始化存储待批量创建的用户列表
        user_list = []
        # 标记是否为管理员（董事会）
        is_admin = (dept.name == "董事会")

        try:
            staff_df = pd.read_excel(file)
        except Exception as e:
            return Response({"detail": f"Excel文件读取失败：{str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # 遍历Excel每一行
        for idx, row in staff_df.iterrows():
            try:
                # 1. 读取基础字段，缺失列直接抛错
                email = row["邮箱"]
                realname = row["姓名"]

                # 2. 区分权限获取部门
                if is_admin:
                    # 董事会：从Excel读取部门
                    dept_name = row["部门"]
                    target_dept = OADepartment.objects.filter(name=dept_name).first()
                    if not target_dept:
                        return Response({"detail": f"第{idx+1}行：部门【{dept_name}】不存在！"}, status=status.HTTP_400_BAD_REQUEST)
                else:
                    # 部门leader：固定当前用户部门，不读取Excel部门
                    target_dept = dept

                # 3. 构建用户对象
                new_user = OAUser(
                    email=email,
                    realname=realname,
                    department=target_dept,
                    status=UserStatusChoices.UNACTIVE
                )
                new_user.set_password("111111")
                user_list.append(new_user)

            except KeyError as ke:
                # 缺失指定列
                return Response({"detail": f"第{idx+1}行：Excel缺少【{ke}】列，请检查模板！"}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                # 单行数据其他错误
                return Response({"detail": f"第{idx+1}行数据错误：{str(e)}，请检查邮箱、姓名、部门"}, status=status.HTTP_400_BAD_REQUEST)

        # 批量入库（事务保证原子性）
        try:
            with transaction.atomic():
                OAUser.objects.bulk_create(user_list)
        except Exception as e:
            return Response({"detail": f"批量保存员工失败：{str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        # 批量发送激活邮件
        for user in user_list:
            send_active_email(request, user.email)

        return Response({"detail": f"成功导入{len(user_list)}位员工"}, status=status.HTTP_200_OK)




