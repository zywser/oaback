import jwt
import  time
from rest_framework.authentication import TokenAuthentication, BaseAuthentication, get_authorization_header
from django.contrib.auth import get_user_model
from rest_framework import exceptions

from django.conf import settings
from .models import OAUser

User = get_user_model()


def generate_jwt(user):
    timestamp = int(time.time())+60*60*24*7
    # timestamp = time.time()+5
    return jwt.encode({"userid":user.pk,"exp":timestamp},settings.SECRET_KEY.encode("utf-8"))


class UserTokenAuthentication(BaseAuthentication):
    def authenticate(self,request):
        return  request._request.user, request._request.auth





class JWTAuthentication(BaseAuthentication):
    """
        Authorization: JWT 401f7ac837da42b97f613d789819ff93537bee6a
    """

    keyword = 'JWT'
    model = None


    """
    A custom token model may be used, but must have the following properties.

    * key -- The string identifying the token
    * user -- The user to which the token belongs
    """

    def authenticate(self, request):
        auth = get_authorization_header(request).split()

        if not auth or auth[0].lower() != self.keyword.lower().encode():
            return None

        if len(auth) == 1:
            msg = "Authentication 不可用"
            raise exceptions.AuthenticationFailed(msg)
        elif len(auth) > 2:
            msg = "Authentication 不可以！ 请提供一个空格"
            raise exceptions.AuthenticationFailed(msg)

        try:
            jwt_token = auth[1]
            jwt_info=jwt.decode(jwt_token,settings.SECRET_KEY,algorithms=["HS256"])
            user_id= jwt_info.get("userid")
            try:
                user = OAUser.objects.get(pk=user_id)
                setattr(request,"user",user)
                return user,jwt_token
            except Exception:
                msg = "用户不存在"
                raise exceptions.AuthenticationFailed(msg)
        except UnicodeError:
                msg = "token格式错误"
                raise exceptions.AuthenticationFailed(msg)
        except jwt.ExpiredSignatureError:
            msg = "token已过期"
            raise exceptions.AuthenticationFailed(msg)

        # except jwt.DecodeError:
        #     msg = "Token 过期"
        #     raise exceptions.AuthenticationFailed(msg)

