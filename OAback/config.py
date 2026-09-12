import os

from dotenv import load_dotenv


load_dotenv()


class Core:
    SECRET_KEY = os.getenv(
        "DJANGO_SECRET_KEY",
        "django-insecure-0b$6gs(hkwbusbr#x-rsda(umd^jeele@02a5%f#kjmg4v@b5q",
    )
    DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes", "on"}
    ALLOWED_HOSTS = [
        host.strip()
        for host in os.getenv("DJANGO_ALLOWED_HOSTS", "121.41.67.132,www.zywser.me,127.0.0.1,localhost").split(",")
        if host.strip()
    ]


class Email:
    EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
    EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() in {"1", "true", "yes", "on"}
    EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.qq.com")
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)


class Databases:
    ENGINE = os.getenv("DB_ENGINE", "django.db.backends.mysql")
    NAME = os.getenv("DB_NAME", "zhiliaooa")
    USER = os.getenv("DB_USER", "root")
    PASSWORD = os.getenv("DB_PASSWORD", "123456")
    HOST = os.getenv("DB_HOST", "127.0.0.1")
    PORT = int(os.getenv("DB_PORT", "3306"))


class Celery:
    CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
    CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://127.0.0.1:6379/2")


class Caches:
    BACKEND = (
        os.getenv("CACHE_BACKEND")
        or os.getenv("CACHES_BACKEND")
        or "django.core.cache.backends.redis.RedisCache"
    )
    LOCATION = os.getenv("CACHE_LOCATION") or os.getenv("CACHES_LOCATION") or "redis://127.0.0.1:6379/3"
