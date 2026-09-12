from django.core.mail import send_mail

from  OAback import celery_app
from django.conf import settings



@celery_app.task(name="send_mail_task")
def send_mail_task(email,subject,message):
    send_mail(subject, recipient_list=[email], message=message, from_email=settings.DEFAULT_FROM_EMAIL)