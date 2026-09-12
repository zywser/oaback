from rest_framework.routers import DefaultRouter
from . import views
from rest_framework.urls import path

from ..staff.urls import app_name

app_name="inform"
router = DefaultRouter()
router.register("inform",views.InformViewSet,basename="inform")

urlpatterns = [
    path("inform/read/",views.ReadInformView.as_view(),name="inform_read")
              ] + router.urls