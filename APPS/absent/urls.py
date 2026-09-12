from django.urls import path
from APPS.oaauth import views
from  rest_framework.routers import DefaultRouter

from . import views

app_name = "absent"
router = DefaultRouter()
router.register("absent",views.AbsentViewSet)
urlpatterns = [
    path("type",views.AbsentTypeView.as_view(),name="absenttype"),
    path("responder",views.ResponderView.as_view(),name="absenttype"),
              ] + router.urls
