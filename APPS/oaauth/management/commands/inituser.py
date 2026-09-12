from django.core.management.base import BaseCommand

from APPS.oaauth import models


class Command(BaseCommand):
    def handle(self, *args, **options):
        """初始化User数据"""

        # 获取员工表数据
        board = models.OADepartment.objects.get(name="董事会")
        product = models.OADepartment.objects.get(name="产品开发部")
        operator = models.OADepartment.objects.get(name="运营部")
        saler = models.OADepartment.objects.get(name="销售部")
        hr = models.OADepartment.objects.get(name="人事部")
        finance = models.OADepartment.objects.get(name="财务部")

        """董事会员工，都是superuser用户"""
        # 1. 东东：属于董事会的larder
        dongdong = models.OAUser.objects.create_superuser(email="dongdong@qq.com", realname="东东", password="111111",
                                                          department=board)

        # 2.多多：董事会
        duoduo = models.OAUser.objects.create_superuser(email="duoduo@qq.com", realname="多多", password="111111",
                                                        department=board)

        # 3.张三：产品开发部的larder
        zhangsan = models.OAUser.objects.create_user(email="zhangsan@qq.com", realname="张三", password="111111",
                                                     department=product)

        # 4. 李四：运营部门的larder
        lisi = models.OAUser.objects.create_user(email="lisi@qq.com", realname="李四", password="111111",
                                                 department=operator)

        # 5. 王五：人事部的larder
        wangwu = models.OAUser.objects.create_user(email="wangwu@qq.com", realname="王五", password="111111",
                                                   department=hr)

        # 6. 赵六：财务部的larder
        zhaoliu = models.OAUser.objects.create_user(email="zhaoliu@qq.com", realname="赵六", password="111111",
                                                    department=finance)

        # 7. 孙七：销售部的larder
        sunqi = models.OAUser.objects.create_user(email="sunqi@qq.com", realname="孙七", password="111111",
                                                  department=saler)



        """给部门指定larder和manager"""

        # 1. 董事会
        board.leader = dongdong
        board.manager = None

        # 2. 产品开发部
        product.leader = zhangsan
        product.manager = dongdong


        # 3. 运营部
        operator.leader = lisi
        operator.manager = dongdong


        # 4. 销售部
        saler.leader = sunqi
        saler.manager = duoduo


        # 5. 人事部
        hr.leader = wangwu
        hr.manager = duoduo


        # 6. 财务部
        finance.leader = zhaoliu
        finance.manager = duoduo


        """保存数据"""
        board.save()
        product.save()
        operator.save()
        saler.save()
        hr.save()
        finance.save()
        self.stdout.write("user表数据初始化成功！")




