from random import choices

from django.db import models

from APPS.oaauth.models import OAUser
# Create your models here.
class  AbsentStatusChoices(models.IntegerChoices):
    """考勤状态表"""
    # 审批中
    AUDITING = 1
    # 审核通过
    PASS = 2
    # 审批拒绝
    REJECT = 3


class AbsentType(models.Model):
    """考勤类型表"""
    name = models.CharField(max_length=200)
    create_time = models.DateTimeField(auto_now_add=True)


class Absent(models.Model):
    """考勤内容表"""
    #1. 标题
    title = models.CharField(max_length=100)
    #2. 请假内容
    request_content = models.TextField()
    #3. 请假类型
    absent_type = models.ForeignKey(AbsentType,on_delete=models.CASCADE,related_name="absents",related_query_name="absents")
    # 在一个模型中，有多个字段对同一个模型引用了外键，那么必须指定related_name为不同的值
    #4. 发起人
    requester = models.ForeignKey(OAUser,on_delete=models.CASCADE,related_name="my_absents",related_query_name="my_absents")
    #5. 审批人(可以为空)
    responder = models.ForeignKey(OAUser,on_delete=models.CASCADE,related_name="sub_absents",related_query_name="sub_absents",null=True)
    #6. 状态
    status = models.IntegerField(choices=AbsentStatusChoices,default=AbsentStatusChoices.AUDITING)
    #7. 请假开始时间
    statar_date =  models.DateField()
    #8. 请假结束时间
    end_date = models.DateField()
    #9. 请假发起时间
    create_time = models.DateTimeField(auto_now_add=True)
    #10. 审批内容回复
    response_content = models.TextField(blank=True)

    class Meta:
        ordering = ("-create_time",)