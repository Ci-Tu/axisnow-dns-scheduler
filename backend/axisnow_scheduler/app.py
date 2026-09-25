"""Flask 应用工厂：JSON API + 前端单页应用的静态文件。"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

from flask import Flask, jsonify, send_from_directory

from .api import api
from .services import geo
from .settings import settings
from .storage import config_store as store

log = logging.getLogger(__name__)

# 前端构建产物里带 hash 的文件可以长期缓存；index.html 必须每次校验
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"


def create_app() -> Flask:
    s = settings()
    app = Flask(__name__, static_folder=None)
    app.secret_key = store.get_session_key()
    app.config.update(
        # 沿用 Flask 默认的 cookie 名 "session"，1.x 升级上来的登录态不失效
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(days=s.session_days),
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=1024 * 1024,
    )
    store.load_config()  # 启动时完成配置迁移
    geo.reload()         # Web 进程自己也要能查 GeoIP（后台线程可能在别的进程）

    app.register_blueprint(api)

    @app.get("/healthz")
    def healthz():
        return jsonify({"status": "ok"})

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    dist = s.web_dist

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def spa(path: str):
        if path.startswith("api/"):
            return jsonify({"ok": False, "error": "接口不存在"}), 404
        if path and os.path.isfile(os.path.join(dist, path)):
            resp = send_from_directory(dist, path)
            if path.startswith("assets/"):
                resp.headers["Cache-Control"] = IMMUTABLE_CACHE
            return resp
        index = os.path.join(dist, "index.html")
        if not os.path.isfile(index):
            return ("前端尚未构建：请在 frontend/ 目录执行 npm run build，"
                    "或使用 Docker 镜像运行。", 503)
        resp = send_from_directory(dist, "index.html")
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    return app
