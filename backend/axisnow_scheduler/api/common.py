"""API 公共设施：鉴权、CSRF、统一错误、客户端构造、并发取数。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional, TypeVar

from flask import Blueprint, current_app, jsonify, request, session

from ..clients.axisnow import AxisNowClient, AxisNowError
from ..clients.cloudflare import CloudflareClient, CloudflareError
from ..services.rules import ValidationError
from ..storage import config_store as store

api = Blueprint("api", __name__, url_prefix="/api")

# 前端每个写请求都带这个头。自定义头会触发 CORS 预检，跨站表单/脚本无法伪造。
CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "axisnow"

_POOL = ThreadPoolExecutor(max_workers=8, thread_name_prefix="upstream")

F = TypeVar("F", bound=Callable[..., Any])


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, **extra: Any):
        super().__init__(message)
        self.status = status
        self.extra = extra


def ok(**data: Any):
    return jsonify({"ok": True, **data})


def body() -> Dict[str, Any]:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def logged_in() -> bool:
    return bool(session.get("auth"))


def public(view: F) -> F:
    """标记无需登录的接口。"""
    view.public = True  # type: ignore[attr-defined]
    return view


def parallel(**calls: Callable[[], Any]) -> Dict[str, Any]:
    """并发执行若干互不依赖的上游请求；任一失败原样抛出。"""
    futures = {k: _POOL.submit(fn) for k, fn in calls.items()}
    return {k: f.result() for k, f in futures.items()}


def optional(fn: Callable[[], Any], default: Any = None) -> Callable[[], Any]:
    """包一层：上游失败时返回默认值，用于非关键数据。"""
    def run() -> Any:
        try:
            return fn()
        except (AxisNowError, CloudflareError):
            return [] if default is None else default
    return run


def axisnow(*, stale: bool = False) -> AxisNowClient:
    """stale=True 只用于纯展示接口；请求带 ?fresh=1（刷新按钮）时强制取新数据。"""
    cfg = store.load_config()
    token = store.api_token(cfg)
    if not token:
        raise ApiError("尚未配置 AxisNow API Token，请先到「设置」页填写", 409, code="no_token")
    if stale and request.args.get("fresh") == "1":
        stale = False
    return AxisNowClient(store.api_base(cfg), token, allow_stale=stale)


def cloudflare(*, stale: bool = False, token: Optional[str] = None) -> CloudflareClient:
    token = token or store.cloudflare_token(store.load_config())
    if not token:
        raise ApiError("尚未配置 Cloudflare API Token", 409, code="no_cf_token")
    if stale and request.args.get("fresh") == "1":
        stale = False
    return CloudflareClient(token, allow_stale=stale)


@api.before_request
def _guard():
    view = current_app.view_functions.get(request.endpoint or "")
    if request.method not in ("GET", "HEAD", "OPTIONS") \
            and request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        return jsonify({"ok": False, "error": "缺少请求来源校验头"}), 403
    if view is not None and getattr(view, "public", False):
        return None
    if not logged_in():
        return jsonify({"ok": False, "error": "未登录", "code": "unauthorized"}), 401
    return None


@api.errorhandler(ApiError)
def _api_error(exc: ApiError):
    return jsonify({"ok": False, "error": str(exc), **exc.extra}), exc.status


@api.errorhandler(ValidationError)
def _validation_error(exc: ValidationError):
    return jsonify({"ok": False, "error": str(exc)}), 400


@api.errorhandler(AxisNowError)
def _axisnow_error(exc: AxisNowError):
    return jsonify({"ok": False, "error": str(exc), "upstream": "axisnow"}), 502


@api.errorhandler(CloudflareError)
def _cloudflare_error(exc: CloudflareError):
    status = 403 if exc.need_permission else 502
    return jsonify({"ok": False, "error": str(exc), "upstream": "cloudflare",
                    "need_permission": exc.need_permission}), status


@api.errorhandler(404)
def _not_found(_exc):
    return jsonify({"ok": False, "error": "接口不存在"}), 404


def require_confirm() -> None:
    if not body().get("confirm"):
        raise ApiError("该操作需要显式确认")
