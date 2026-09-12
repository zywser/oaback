from django.urls import path
from APPS.oaauth import views
from rest_framework.urls import app_name

app_name = "oaauth"
urlpatterns = [
    path("login",views.LoginView.as_view(),name="login"),
    path("resetpwd",views.ResetPwdView.as_view(),name="resetpwd"),
]
