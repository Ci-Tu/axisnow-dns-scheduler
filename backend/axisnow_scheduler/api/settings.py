"""设置：AxisNow Token、调度参数、访问密码。"""

from __future__ import annotations

from flask import session

from ..clients.axisnow import AxisNowClient, AxisNowError
from ..storage import config_store as store
from .auth import validate_new_password
from .common import ApiError, api, body, ok

MIN_TOKEN_LENGTH = 20


@api.put("/settings/token")
def set_token():
    cfg = store.load_config()
    if not store.token_meta(cfg)["editable"]:
        raise ApiError("Token 由环境变量 AXISNOW_API_TOKEN 提供，不能在界面修改", 409)
    token = str(body().get("token") or "").strip()
    if len(token) < MIN_TOKEN_LENGTH:
        raise ApiError("Token 为空或长度异常")
    # 先校验再保存，避免把一个无效 Token 覆盖掉原本可用的
    try:
        AxisNowClient(store.api_base(cfg), token).list_domains()
    except AxisNowError as exc:
        raise ApiError(f"Token 校验未通过：{exc}") from None

    def mutate(c):
        c["api_token"] = token

    store.mutate(mutate)
    return ok(message="Token 已保存，连通性校验通过", token=store.token_meta(store.load_config()))


@api.delete("/settings/token")
def clear_token():
    def mutate(c):
        c["api_token"] = ""

    store.mutate(mutate)
    return ok()


@api.put("/settings/scheduler")
def set_scheduler():
    data = body()
    try:
        interval = int(data.get("interval_seconds", 30))
    except (TypeError, ValueError):
        raise ApiError("间隔必须是整数") from None
    value = {"enabled": bool(data.get("enabled", True)),
             "interval_seconds": max(10, min(interval, 3600))}

    def mutate(c):
        c["scheduler"] = value

    store.mutate(mutate)
    return ok(scheduler=value)


@api.put("/settings/password")
def set_password():
    data = body()
    if not store.verify_password(store.load_config(), str(data.get("old") or "")):
        raise ApiError("当前密码不正确")
    new = str(data.get("new") or "")
    validate_new_password(new)
    store.mutate(lambda c: store.set_password(c, new))
    # 改完密码保持当前会话有效
    session.permanent = True
    session["auth"] = True
    return ok()
