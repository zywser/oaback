# ===== 后端镜像：Django + uWSGI（Python 3.13）=====
FROM python:3.13

# 将项目代码拷贝到容器 /www
COPY . /www/
WORKDIR /www

# 安装项目依赖（清华源）
# uWSGI 不锁版本：Python 3.13 需要 uwsgi >= 2.0.27，2.0.25.1 会编译失败
RUN pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt \
    && pip install -i https://pypi.tuna.tsinghua.edu.cn/simple uwsgi

# uWSGI socket / 日志目录（socket 与前端 nginx 容器通过共享卷互通）
RUN mkdir -p /data/log /data/sock

EXPOSE 8000

# 启动流程：收集静态文件 → 建表 → 初始化数据 → 导入种子知识 → Celery(后台) → uWSGI(前台)
# 注意：Celery 入口为 OAback（大写，包目录名），不是 oaback
ENTRYPOINT ["sh", "-c", "\
python manage.py collectstatic --noinput && \
python manage.py migrate && \
python manage.py initdep && \
python manage.py inituser && \
python manage.py initabsenttype && \
python manage.py import_knowledge_seed && \
celery -A OAback worker -l INFO --concurrency=1 --detach && \
uwsgi --ini uwsgi.docker.ini"]
