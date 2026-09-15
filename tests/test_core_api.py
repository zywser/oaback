"""核心业务接口测试：认证 / 员工 / 请假 / 通知。

覆盖范围（与简历项目描述对应）：
  - JWT 登录成功 / 密码错误 / 未激活用户拒绝登录
  - 全局登录中间件对未认证请求返回 403
  - 员工列表权限（董事会可查看）
  - 请假类型查询与请假单创建（responder 自动分配）
  - 通知发布（公开）与已读标记
"""
import pytest


# ---------------------------------------------------------------------------
# 认证模块（oaauth）
# ---------------------------------------------------------------------------

class TestLogin:
    url = "/api/auth/login"

    def test_login_success(self, client, board_user):
        resp = client.post(self.url, {"email": board_user.email, "password": "test123456"}, format="json")
        assert resp.status_code == 200
        assert "token" in resp.data
        assert resp.data["user"]["email"] == board_user.email

    def test_login_wrong_password(self, client, board_user):
        resp = client.post(self.url, {"email": board_user.email, "password": "wrong123"}, format="json")
        assert resp.status_code == 400
        assert "detail" in resp.data

    def test_login_unactive_user_rejected(self, client, unactive_user):
        resp = client.post(self.url, {"email": unactive_user.email, "password": "test123456"}, format="json")
        assert resp.status_code == 400
        assert "未激活" in resp.data["detail"]

    def test_login_missing_fields(self, client):
        resp = client.post(self.url, {}, format="json")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# 员工模块（staff）
# ---------------------------------------------------------------------------

class TestStaff:

    def test_staff_list_requires_auth(self, client):
        """未携带 JWT 访问员工列表 → 全局登录中间件返回 403。"""
        resp = client.get("/api/staff/staff")
        assert resp.status_code == 403

    def test_board_can_list_all_staff(self, auth_client, staff_user):
        """董事会用户可查看员工列表（分页结构）。"""
        resp = auth_client.get("/api/staff/staff")
        assert resp.status_code == 200
        assert "results" in resp.data  # PageNumberPagination 分页结构

    def test_regular_staff_cannot_list_all(self, client, staff_token, staff_user):
        """普通员工访问员工列表 → 权限不足 403（非董事会且非 leader）。"""
        client.credentials(HTTP_AUTHORIZATION=f"JWT {staff_token}")
        resp = client.get("/api/staff/staff")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# 请假模块（absent）
# ---------------------------------------------------------------------------

class TestAbsent:

    def test_absent_type_list(self, auth_client, absent_type):
        resp = auth_client.get("/api/type")
        assert resp.status_code == 200
        names = [item["name"] for item in resp.data]
        assert "事假" in names

    def test_create_absent(self, client, staff_token, staff_user, absent_type):
        client.credentials(HTTP_AUTHORIZATION=f"JWT {staff_token}")
        resp = client.post(
            "/api/absent/",
            {
                "title": "回家探亲",
                "request_content": "请三天假回老家",
                "absent_type_id": absent_type.pk,
                "statar_date": "2026-09-20",
                "end_date": "2026-09-22",
            },
            format="json",
        )
        assert resp.status_code == 201
        # 列表查询（who=my 仅返回本人请假单）
        resp = client.get("/api/absent/?who=my")
        assert resp.status_code == 200
        assert resp.data["count"] == 1


# ---------------------------------------------------------------------------
# 通知模块（inform）
# ---------------------------------------------------------------------------

class TestInform:

    def test_publish_public_inform_and_read(self, client, board_token, board_user):
        client.credentials(HTTP_AUTHORIZATION=f"JWT {board_token}")
        # 发布公开通知（department_ids=[0] 表示全员可见）
        resp = client.post(
            "/api/inform/inform/",
            {"title": "放假通知", "content": "本周五放假", "department_ids": [0]},
            format="json",
        )
        assert resp.status_code == 201
        inform_id = resp.data["id"]

        # 通知作者可在列表中看到自己发布的通知
        resp = client.get("/api/inform/inform/")
        assert resp.status_code == 200
        assert any(item["id"] == inform_id for item in resp.data["results"])

        # 标记已读
        resp = client.post("/api/inform/inform/read/", {"inform_pk": inform_id}, format="json")
        assert resp.status_code == 200

        # 重复已读幂等（不报错）
        resp = client.post("/api/inform/inform/read/", {"inform_pk": inform_id}, format="json")
        assert resp.status_code == 200
