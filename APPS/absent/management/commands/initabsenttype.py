from django.core.management.base import BaseCommand
from APPS.absent.models import AbsentType


class Command(BaseCommand):
    def handle(self, *args, **options):
        """初始化考勤类型（幂等：已存在则跳过，不产生重复记录）"""
        absent_types = ["事假", "病假", "工伤假", "婚假", "丧假", "产假", "探亲假", "公假", "年休假"]
        created = 0
        for name in absent_types:
            if not AbsentType.objects.filter(name=name).exists():
                AbsentType.objects.create(name=name)
                created += 1
        self.stdout.write(f"考勤类型数据初始化成功！新增 {created} 条（已存在 {len(absent_types) - created} 条）")
