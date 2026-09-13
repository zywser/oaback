from django.urls import path
from . import views




app_name="home"
urlpatterns=[
    path("latest/inform",views.LatestInformView.as_view(),name="latest_inform"),
    path("latest/absent",views.LatestAbsentView.as_view(),name="latest_absent"),
    path("department/staff/count",views.DepartmentStaffCountView.as_view(),name="department_staff_count"),
    path('health', views.HealthCheckView.as_view(), name='health_check') # 安全检查路由

]