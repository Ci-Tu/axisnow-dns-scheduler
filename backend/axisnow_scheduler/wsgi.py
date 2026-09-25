"""WSGI 入口：gunicorn axisnow_scheduler.wsgi:app

后台线程（调度、拨测采样、GeoIP 更新）在这里启动，并由文件锁保证全局只有一份。
"""

from __future__ import annotations

import logging
import os

from .app import create_app
from .services import background

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

app = create_app()
background.start()
