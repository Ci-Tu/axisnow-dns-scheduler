"""登录、首次设置密码、退出、全局元信息。

会话策略：登录后 session 永久有效（默认 180 天，SESSION_DAYS 可调），密钥固定存放在
data/session.key，容器重启、升级、重建都不会掉线。
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime
from typing import Deque, Dict

from flask import request, session

from .. import __version__
from .. import features as feature_registry
from ..services import geo
from ..settings import settings
from ..storage import config_store as store
from .common import ApiError, api, body, logged_in, ok, public

MIN_PASSWORD_LENGTH = 8
# 同一来源 10 分钟内最多失败 10 次
MAX_FAILURES = 10
FAILURE_WINDOW_SECONDS = 600

_failures: Dict[str, Deque[float]] = defaultdict(deque)
_failures_lock = threading.Lock()


def _client_key() -> str:
    return request.headers.get("X-Real-IP") or request.remote_addr or "unknown"


def _check_rate_limit() -> None:
    now = time.monotonic()
    with _failures_lock:
        q = _failures[_client_key()]
        while q and now - q[0] > FAILURE_WINDOW_SECONDS:
            q.popleft()
        if len(q) >= MAX_FAILURES:
            raise ApiError("尝试次数过多，请 10 分钟后再试", 429)


def _record_failure() -> None:
    with _failures_lock:
        _failures[_client_key()].append(time.monotonic())


def _start_session() -> None:
    session.clear()
    session.permanent = True
    session["auth"] = True


def validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ApiError(f"密码至少 {MIN_PASSWORD_LENGTH} 位")


@api.get("/auth/state")
@public
def auth_state():
    cfg = store.load_config()
    return ok(authenticated=logged_in(), setup_required=not store.has_password(cfg),
              session_days=settings().session_days, version=__version__)


@api.post("/auth/setup")
@public
def auth_setup():
    data = body()
    password = str(data.get("password") or "")
    if password != str(data.get("confirm") or ""):
        raise ApiError("两次输入的密码不一致")
    validate_new_password(password)

    def mutate(cfg):
        # 并发保护：只有在确实没有密码时才允许初始化
        if store.has_password(cfg):
            raise ApiError("已经设置过密码，请直接登录", 409)
        store.set_password(cfg, password)

    store.mutate(mutate)
    _start_session()
    return ok()


@api.post("/auth/login")
@public
def auth_login():
    _check_rate_limit()
    password = str(body().get("password") or "")
    if not store.verify_password(store.load_config(), password):
        _record_failure()
        raise ApiError("密码错误", 401)
    _start_session()
    return ok()


@api.post("/auth/logout")
@public
def auth_logout():
    session.clear()
    return ok()


@api.get("/meta")
def meta():
    cfg = store.load_config()
    s = settings()
    return ok(
        version=__version__,
        timezone=s.timezone_name,
        now=datetime.now(s.tz).isoformat(timespec="seconds"),
        session_days=s.session_days,
        token=store.token_meta(cfg),
        cloudflare=store.cf_token_meta(cfg),
        scheduler=cfg.get("scheduler") or {},
        features=feature_registry.describe(),
        geoip=geo.status(),
    )
