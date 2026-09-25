"""Cloudflare 集成：Token 管理、Zone 列表、已接入记录总览、一键创建 / 删除记录。"""

from __future__ import annotations

from typing import Any, Dict, List

from flask import request

from ..clients.cloudflare import CloudflareClient, CloudflareError
from ..storage import config_store as store
from .common import (
    ApiError,
    api,
    axisnow,
    body,
    cloudflare,
    ok,
    optional,
    parallel,
    require_confirm,
)

MIN_TOKEN_LENGTH = 20


def _norm(host: Any) -> str:
    return str(host or "").strip().lower().rstrip(".")


def _records_by_zone(client: CloudflareClient, zones: List[Dict[str, Any]]):
    per_zone = parallel(**{z["id"]: (lambda zid=z["id"]: client.list_records(zid)) for z in zones})
    for z in zones:
        for r in per_zone[z["id"]]:
            yield z, r


@api.get("/cloudflare/status")
def cf_status():
    cfg = store.load_config()
    meta = store.cf_token_meta(cfg)
    out: Dict[str, Any] = {"token": meta, "verified": False, "message": "尚未配置 Cloudflare Token"}
    if meta["configured"]:
        try:
            info = cloudflare().verify_token()
            out["verified"] = info.get("status") == "active"
            out["message"] = "Token 有效" if out["verified"] else f"Token 状态：{info.get('status')}"
        except CloudflareError as exc:
            out.update(message=str(exc), need_permission=exc.need_permission)
    return ok(**out)


@api.put("/cloudflare/token")
def cf_set_token():
    if not store.cf_token_meta(store.load_config())["editable"]:
        raise ApiError("Token 由环境变量 CLOUDFLARE_API_TOKEN 提供，不能在界面修改", 409)
    token = str(body().get("token") or "").strip()
    if len(token) < MIN_TOKEN_LENGTH:
        raise ApiError("Token 为空或长度异常")
    try:
        info = CloudflareClient(token).verify_token()
    except CloudflareError as exc:
        raise ApiError(f"Token 校验失败：{exc}") from None

    def mutate(cfg):
        cfg.setdefault("cloudflare", {})["token"] = token

    store.mutate(mutate)
    return ok(verified=info.get("status") == "active", message="Token 已保存并校验通过",
              token=store.cf_token_meta(store.load_config()))


@api.delete("/cloudflare/token")
def cf_clear_token():
    def mutate(cfg):
        cfg.setdefault("cloudflare", {})["token"] = ""

    store.mutate(mutate)
    return ok()


@api.get("/cloudflare/zones")
def cf_zones():
    return ok(zones=cloudflare(stale=True).list_zones())


@api.get("/cloudflare/linked")
def cf_linked():
    """反查：哪些 CF 记录已经指向某个 AxisNow 调度域。"""
    target = _norm(request.args.get("target"))
    if not target:
        raise ApiError("缺少 target")
    client = cloudflare(stale=True)
    records = []
    for z, r in _records_by_zone(client, client.list_zones()):
        if _norm(r.get("content")) == target:
            records.append({**r, "zone_name": z["name"]})
    return ok(records=records)


@api.get("/cloudflare/overview")
def cf_overview():
    """总览：Token 可见的 Zone + 已指向 AxisNow 调度域的记录。"""
    if not store.cf_token_meta(store.load_config())["configured"]:
        return ok(configured=False, zones=[], links=[])
    client = cloudflare(stale=True)
    # 客户端要在请求线程里构造（读取 request 参数），再把方法交给线程池
    try:
        axis_domains_fn = optional(axisnow(stale=True).list_domains)
    except ApiError:
        axis_domains_fn = list
    got = parallel(zones=client.list_zones, axis=axis_domains_fn)
    axis_domains = {_norm(d.get("domain")) for d in got["axis"]}
    links = [{**r, "zone_name": z["name"], "matched_domain": _norm(r.get("content"))}
             for z, r in _records_by_zone(client, got["zones"])
             if _norm(r.get("content")) in axis_domains]
    return ok(configured=True, zones=got["zones"], links=links)


@api.post("/cloudflare/records")
def cf_create_record():
    """在自己的 Cloudflare 上创建指向调度域的记录。强制 DNS only（proxied=false）。"""
    data = body()
    zone_id = str(data.get("zone_id") or "").strip()
    name = _norm(data.get("name"))
    content = _norm(data.get("content"))
    rtype = str(data.get("type") or "CNAME").strip().upper()
    if not zone_id:
        raise ApiError("请选择 Cloudflare 域名（Zone）")
    if not name or not content:
        raise ApiError("记录名与目标都是必填")
    if rtype not in ("CNAME", "A"):
        raise ApiError("只支持创建 CNAME 或 A 记录")
    if rtype == "CNAME" and name == content:
        raise ApiError("CNAME 目标不能和记录名相同")
    try:
        ttl = int(data.get("ttl") or 1)
    except (TypeError, ValueError):
        ttl = 1
    if ttl != 1 and not 60 <= ttl <= 86400:
        raise ApiError("TTL 只能是 1（自动）或 60–86400")

    client = cloudflare()
    clash = [r for r in client.list_records(zone_id, name=name)
             if r.get("type") in ("A", "AAAA", "CNAME")]
    if clash:
        raise ApiError(f"该域名下已有 {clash[0]['type']} 记录（{clash[0]['content']}），"
                       "请先删除或改用别的记录名", 409, existing=clash)
    record = client.create_record(zone_id, type=rtype, name=name, content=content, ttl=ttl,
                                  proxied=False, comment="AxisNow DNS Scheduler")
    return ok(record=record)


@api.delete("/cloudflare/records/<zone_id>/<record_id>")
def cf_delete_record(zone_id: str, record_id: str):
    require_confirm()
    cloudflare().delete_record(zone_id, record_id)
    return ok()
