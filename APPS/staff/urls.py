from  django.urls import path
from . import views
from rest_framework.routers import DefaultRouter

router =DefaultRouter(trailing_slash=False)
router.register("staff",views.StaffViewSet,basename="staff")
from APPS.absent.urls import urlpatterns, app_name

app_name="staff"

urlpatterns = [
    path("departments",views.DepartmentListView.as_view(),name="departments"),
    # path("staff",views.StaffView.as_view(),name="staff_view"),
    path("active",views.ActiveStaffView.as_view(),name="active_staff"),
    path("celery/text",views.CeleryTextView.as_view(),name="text_celery"),
    path("download",views.StaffDownLoadView.as_view(),name="staff_download"),
    path("upload",views.StaffUpLoadView.as_view(),name="staff_upload"),

]+ router.urls