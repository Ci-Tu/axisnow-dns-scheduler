#!/bin/sh
# 以 root 启动时：修正数据目录属主，然后降权到 PUID:PGID 运行。
# 这样既能读写旧版本（root 运行时）留下的文件，又不以 root 身份跑应用。
set -eu

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA_DIR"
    chown -R "${PUID}:${PGID}" "$DATA_DIR"
    exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$0" "$@"
fi

# 单 worker + 多线程：调度状态在进程内存里，只能有一个进程。
# 后台线程另有 data/background.lock 文件锁兜底。
exec gunicorn \
    --workers 1 \
    --threads 16 \
    --timeout 120 \
    --graceful-timeout 30 \
    --access-logfile - \
    --error-logfile - \
    --bind "0.0.0.0:${PORT}" \
    axisnow_scheduler.wsgi:app
