import os
import sys
from celery import Celery
from celery.signals import after_setup_logger
import logging

# 设置django的settings模块，celery会读取这个模块中的配置信息
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OAback.settings')

app = Celery('OAback')

## 日志管理
@after_setup_logger.connect
def setup_loggers(logger, *args, **kwargs):
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # add filehandler
    fh = logging.FileHandler('logs.log')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)
    logger.addHandler(fh)

# 配置从settins.py中读取celery配置信息，所有Celery配置信息都要以CELERY_开头
app.config_from_object('django.conf:settings', namespace='CELERY')

# 修复：Windows 上 celery 默认的 prefork 并发池无法正常工作（Windows 无 fork 机制，
# 任务处理时 fast_trace_task 解包 _localized 为空列表，报
# ValueError: not enough values to unpack (expected 3, got 0)）。
# 改用线程池：共享进程内存、保留并发能力，且无需额外依赖。
# 仅在 Windows 平台生效，Linux/生产环境仍使用默认 prefork 池。
if sys.platform == "win32":
    app.conf.worker_pool = "threads"

# 自动发现任务，任务可以写在app/tasks.py中
app.autodiscover_tasks()

# 测试任务
# 1. bind=True，在任务函数中，第一个参数就是任务对象（Task），如果没有设置这个参数，或者bind=False，那么任务函数就不会有任务对象参数
# 2. ignore_result=True，就不会保存任务的执行结果
@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')