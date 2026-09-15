"""pytest 公共 fixtures：测试用户、登录与客户端。"""
import pytest
from rest_framework.test import APIClient

from APPS.oaauth.models import OADepartment, OAUser, UserStatusChoices
from APPS.absent.models import AbsentType


@pytest.fixture
def client():
    """DRF 测试客户端。"""
    return APIClient()


def _make_user(realname, email, password, dept, status=UserStatusChoices.ACTIVED):
    user = OAUser.objects.create_user(realname=realname, email=email, password=password)
    user.status = status
    user.department = dept
    user.save()
    return user


@pytest.fixture
def board_user(db):
    """董事会用户（leader），可查看全部员工。"""
    dept = OADepartment.objects.create(name="董事会", intro="决策层")
    user = _make_user("董事长", "board@test.com", "test123456", dept)
    dept.leader = user
    dept.save()
    return user


@pytest.fixture
def staff_user(db):
    """普通部门员工：产品开发部（leader 为部门经理，员工本人无管理权限）。"""
    dept = OADepartment.objects.create(name="产品开发部", intro="研发")
    leader = _make_user("部门经理", "leader@test.com", "test123456", dept)
    dept.leader = leader
    dept.save()
    return _make_user("普通员工", "staff@test.com", "test123456", dept)


@pytest.fixture
def unactive_user(db, board_user):
    """未激活用户（status=UNACTIVE），登录应被拒绝。"""
    return _make_user(
        "未激活", "unactive@test.com", "test123456", board_user.department,
        status=UserStatusChoices.UNACTIVE,
    )


@pytest.fixture
def absent_type(db):
    """请假类型：事假。"""
    return AbsentType.objects.create(name="事假")


def login(client, email, password):
    """执行登录，返回 DRF 响应对象。"""
    return client.post("/api/auth/login", {"email": email, "password": password}, format="json")


@pytest.fixture
def board_token(client, board_user):
    """董事会用户的 JWT。"""
    resp = login(client, board_user.email, "test123456")
    return resp.data["token"]


@pytest.fixture
def staff_token(client, staff_user):
    """普通员工的 JWT。"""
    resp = login(client, staff_user.email, "test123456")
    return resp.data["token"]


@pytest.fixture
def auth_client(client, board_token):
    """已携带董事会 JWT 的客户端。"""
    client.credentials(HTTP_AUTHORIZATION=f"JWT {board_token}")
    return client
