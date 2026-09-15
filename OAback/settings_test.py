"""测试专用配置（继承主 settings 并覆盖外部依赖）。

设计目标：
  - 不依赖 MySQL / Redis / SMTP / 外部 API，clone 后直接 `pytest` 即可运行；
  - 使用 SQLite 内存库 + locmem 邮件后端 + 本地缓存 + Celery 同步执行。

运行方式：pytest.ini 中 DJANGO_SETTINGS_MODULE 指向本模块。
"""
from .settings import *  # noqa: F401,F403

# SQLite 内存库：测试数据不落盘，每个测试用例自动隔离
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# 邮件不发真实 SMTP，存入内存（可用 django.core.mail.outbox 断言）
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# 缓存不依赖 Redis
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

# Celery 任务同步执行（激活邮件等），不投递 Redis
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
