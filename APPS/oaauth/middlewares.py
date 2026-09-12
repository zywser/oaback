from  django.utils.deprecation import MiddlewareMixin
from rest_framework.authentication import get_authorization_header
from  rest_framework import  exceptions
import  jwt
from  django.conf import  settings
from django.http.response import JsonResponse
from rest_framework.status import HTTP_403_FORBIDDEN
from django.contrib.auth.models import AnonymousUser
from django.shortcuts import reverse


from APPS.oaauth.models import OAUser


class LoginCheckMiddleware(MiddlewareMixin):
    keyword = "JWT"

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.white_list = ["/auth"]



    def process_request(self,request):
        # 1. 如果返回None，那么会正常执行（包括执行视图、执行其他中间件代码）
        # 2. 如果返回的是一个HttpResponse对象，那么将不会执行视图，以及后面的代码
        # self.white_list=["/auth/login","/staff/active","/docs"]
        self.white_list = [reverse("oaauth:login"),reverse("staff:active_staff"),reverse("api_docs")]

        if request.path in self.white_list or request.path.startswith(settings.MEDIA_URL):
            request.user = AnonymousUser()
            request.auth = None
            return None
        try:
            auth = get_authorization_header(request).split()

            if not auth or auth[0].lower() != self.keyword.lower().encode():
                raise  exceptions.ValidationError("请传入JWT！")

            if len(auth) == 1:
                msg = "Authentication 不可用"
                raise exceptions.AuthenticationFailed(msg)
            elif len(auth) > 2:
                msg = "Authentication 不可以！ 请提供一个空格"
                raise exceptions.AuthenticationFailed(msg)

            try:
                jwt_token = auth[1]
                jwt_info = jwt.decode(jwt_token, settings.SECRET_KEY, algorithms=["HS256"])
                user_id = jwt_info.get("userid")
                try:
                    # 绑定当前User对象到request对象上
                    user = OAUser.objects.get(pk=user_id)
                    request.user = user
                    request.auth = jwt_token

                except Exception:
                    msg = "用户不存在"
                    raise exceptions.AuthenticationFailed(msg)
            except UnicodeError:
                msg = "token格式错误"
                raise exceptions.AuthenticationFailed(msg)
            except jwt.ExpiredSignatureError:
                msg = "token已过期"
                raise exceptions.AuthenticationFailed(msg)

        except Exception as e:
            return JsonResponse(data={"detail":"请先登录"},status=HTTP_403_FORBIDDEN)


