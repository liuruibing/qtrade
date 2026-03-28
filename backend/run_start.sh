#!/bin/bash

cd "$(dirname "$0")"

# 默认使用 python
if [ -f "venv/bin/python" ]; then
    PY_BIN="venv/bin/python"
    source venv/bin/activate
else
    # 优先尝试 python3.12
    if command -v python3.12 &> /dev/null; then
        PY_BIN=${1:-"python3.12"}
    else
        PY_BIN=${1:-"python"}
    fi
fi

# 运行端口，默认 8080
RUN_HOST=0.0.0.0
RUN_PORT=${2:-8080}
RUN_WORKERS=4

# 安装依赖环境
# $PY_BIN -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple/ -r requirements.txt

# 执行迁移
$PY_BIN manage.py makemigrations
$PY_BIN manage.py migrate

# 初始化数据库
# python3 manage.py init -y

# 初始化省市县数据
# python3 manage.py init_area

# 启动 Celery 定时任务
# 先停止服务，防止后续重复启动导致占用飙升
pkill -f "celery.*application.celery"

# linux
celery -A application.celery worker -B --loglevel=info > celery_worker.log 2>&1 &

## windows
## Celery worker
#celery -A application.celery worker --loglevel=info > celery_worker.log 2>&1 &
#
## Celery beat
#celery -A application.celery beat --loglevel=info > celery_beat.log 2>&1 &

# 启动项目
#$PY_BIN manage.py runserver $RUN_HOST:$RUN_PORT

# uvicorn 方式启动
./deploy_demo.sh
# 确保在虚拟环境下运行
source venv/bin/activate
# 一句话启动：设置变量 + 启动服务
CZSC_USE_PYTHON="1" uvicorn application.asgi:application --port $RUN_PORT --host $RUN_HOST --workers $RUN_WORKERS
