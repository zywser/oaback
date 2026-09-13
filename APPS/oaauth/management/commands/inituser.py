from django.core.management.base import BaseCommand
from APPS.oaauth import models


class Command(BaseCommand):
    def handle(self, *args, **options):
        """初始化User数据（幂等版本）"""

        def get_dept(name):
            return models.OADepartment.objects.filter(name=name).first()

        board = get_dept("董事会")
        product = get_dept("产品开发部")
        operator = get_dept("运营部")
        saler = get_dept("销售部")
        hr = get_dept("人事部")
        finance = get_dept("财务部")

        users_config = [
            {"email": "dongdong@qq.com", "realname": "东东", "dept": board, "superuser": True},
            {"email": "duoduo@qq.com", "realname": "多多", "dept": board, "superuser": True},
            {"email": "zhangsan@qq.com", "realname": "张三", "dept": product, "superuser": False},
            {"email": "lisi@qq.com", "realname": "李四", "dept": operator, "superuser": False},
            {"email": "wangwu@qq.com", "realname": "王五", "dept": hr, "superuser": False},
            {"email": "zhaoliu@qq.com", "realname": "赵六", "dept": finance, "superuser": False},
            {"email": "sunqi@qq.com", "realname": "孙七", "dept": saler, "superuser": False},
        ]

        user_objs = {}
        for cfg in users_config:
            try:
                existing = models.OAUser.objects.get(email=cfg["email"])
                user_objs[cfg["email"]] = existing
                self.stdout.write(f"  {cfg['email']}: already exists")
            except models.OAUser.DoesNotExist:
                if cfg["superuser"]:
                    u = models.OAUser.objects.create_superuser(
                        email=cfg["email"], realname=cfg["realname"],
                        password="111111", department=cfg["dept"]
                    )
                else:
                    u = models.OAUser.objects.create_user(
                        email=cfg["email"], realname=cfg["realname"],
                        password="111111", department=cfg["dept"]
                    )
                user_objs[cfg["email"]] = u
                self.stdout.write(f"  {cfg['email']}: created")

        dongdong = user_objs["dongdong@qq.com"]
        duoduo = user_objs["duoduo@qq.com"]
        zhangsan = user_objs["zhangsan@qq.com"]
        lisi = user_objs["lisi@qq.com"]
        wangwu = user_objs["wangwu@qq.com"]
        zhaoliu = user_objs["zhaoliu@qq.com"]
        sunqi = user_objs["sunqi@qq.com"]

        dept_configs = [
            (board, dongdong, None),
            (product, zhangsan, dongdong),
            (operator, lisi, dongdong),
            (saler, sunqi, duoduo),
            (hr, wangwu, duoduo),
            (finance, zhaoliu, duoduo),
        ]
        for dept, leader, manager in dept_configs:
            if dept:
                dept.leader = leader
                dept.manager = manager
                dept.save()

        self.stdout.write("user表数据初始化成功！")
