from django.core.management.base import BaseCommand
from APPS.oaauth import models

DEPARTMENTS = [
    ("董事会", "董事会"),
    ("产品开发部", "产品设计，技术开发"),
    ("运营部", "客户运营，产品运营"),
    ("销售部", "销售产品"),
    ("人事部", "员工招聘，员工培训，员工考核"),
    ("财务部", "财务报表，财务审核"),
]

class Command(BaseCommand):
    def handle(self, *args, **options):
        for name, intro in DEPARTMENTS:
            if not models.OADepartment.objects.filter(name=name).exists():
                models.OADepartment.objects.create(name=name, intro=intro)
        self.stdout.write("数据初始化成功！")
