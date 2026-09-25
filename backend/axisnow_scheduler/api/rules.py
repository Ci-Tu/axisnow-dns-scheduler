"""路由规则：列表、详情、增删改、纳管、功能模块配置、潮汐时间段、下发与同步。"""

from __future__ import annotations

from typing import Any, Dict, List

from .. import features as feature_registry
from .. import scheduler
from ..clients.axisnow import ip_pool_of
from ..features.tide import make_slot, normalize_order, validate_slot
from ..services import rules as rule_service
from ..services.views import rule_view
from ..storage import config_store as store
from .common import ApiError, api, axisnow, body, ok, parallel, require_confirm

MAX_NOTE_LENGTH = 32


def _domain_names(domains: List[Dict[str, Any]]) -> Dict[str, str]:
    return {d.get("uuid"): d.get("domain") or "" for d in domains}


def _ip_pool(rule_uuid: str) -> List[str]:
    pool = ip_pool_of(axisnow().get_rule(rule_uuid))
    if not pool:
        raise ApiError("该规则的地址池里没有 IP 类型的地址组")
    return pool


# ---------- 读取 ----------

@api.get("/rules")
def list_rules():
    client = axisnow(stale=True)
    got = parallel(domains=client.list_domains, rules=client.list_rules)
    probe = client.probe_status([r.get("uuid") for r in got["rules"]])
    cfg = store.load_config()
    names = _domain_names(got["domains"])
    return ok(
        rules=[rule_view(r, cfg, probe.get(r.get("uuid")) or {},
                         names.get(r.get("dns_domain_uuid"), "")) for r in got["rules"]],
        scheduler=scheduler.state_snapshot(),
    )


@api.get("/rules/<rule_uuid>")
def get_rule(rule_uuid: str):
    client = axisnow(stale=True)
    got = parallel(remote=lambda: client.get_rule(rule_uuid),
                   probe=lambda: client.probe_status([rule_uuid]))
    return ok(rule=rule_view(got["remote"], store.load_config(), got["probe"].get(rule_uuid)))


# ---------- 增删改（写 AxisNow） ----------

@api.post("/rules")
def create_rule():
    data = body()
    domain_uuid = str(data.get("dns_domain_uuid") or "").strip()
    geo_isp = str(data.get("geo_isp") or "").strip()
    if not domain_uuid:
        raise ApiError("请选择所属调度域")
    if not geo_isp:
        raise ApiError("请选择线路")

    client = axisnow()
    got = parallel(domains=client.list_domains, rules=client.list_rules)
    domain = next((d for d in got["domains"] if d.get("uuid") == domain_uuid), None)
    if domain is None:
        raise ApiError("找不到该调度域")

    pool_mode = str(data.get("pool_mode") or "custom_ips").strip()
    ips = rule_service.normalize_ips(data.get("ips")) if pool_mode == "custom_ips" else []
    pool = rule_service.build_address_pool(pool_mode, ips=ips, eip_uuids=data.get("eip_uuids"))
    siblings = [r for r in got["rules"] if r.get("dns_domain_uuid") == domain_uuid]
    action = rule_service.build_action(
        strategy=data.get("election_strategy") or "priority_order",
        ip_quantity=data.get("ip_quantity") or 1,
        pool=pool,
        probe_template=str(data.get("edge_probe_template_uuid") or "").strip(),
        ttl_conf=rule_service.derive_ttl_conf(domain, siblings,
                                              rule_service.parse_ttl(data.get("ttl"))),
        trigger_interval=data.get("trigger_interval"),
    )
    payload = {
        "type": domain.get("record_type") or "A",
        "geo_isp": geo_isp,
        "dns_domain_uuid": domain_uuid,
        "name": str(data.get("name") or "").strip()[:100],
        "description": str(data.get("description") or "").strip()[:255],
        "status": "active",
        "action": action,
    }
    if domain.get("domain"):
        payload["domain"] = domain["domain"]
    return ok(rule=client.create_rule(payload))


@api.put("/rules/<rule_uuid>")
def update_rule(rule_uuid: str):
    client = axisnow()
    payload = rule_service.build_updated_rule(client.get_rule(rule_uuid), body())
    updated = client.update_rule(rule_uuid, payload)
    new_pool = ip_pool_of({"action": payload["action"]})

    def mutate(cfg):
        entry = (cfg.get("rules") or {}).get(rule_uuid)
        if isinstance(entry, dict):
            rule_service.reconcile_pool(entry, new_pool)

    store.mutate(mutate)
    scheduler.forget(rule_uuid)
    return ok(rule=updated)


@api.delete("/rules/<rule_uuid>")
def delete_rule(rule_uuid: str):
    require_confirm()
    axisnow().delete_rule(rule_uuid)
    store.mutate(lambda cfg: (cfg.get("rules") or {}).pop(rule_uuid, None))
    scheduler.forget(rule_uuid)
    return ok()


# ---------- 纳管 ----------

@api.post("/rules/<rule_uuid>/adopt")
def adopt_rule(rule_uuid: str):
    pool = _ip_pool(rule_uuid)

    def mutate(cfg):
        entry = rule_service.ensure_rule_entry(cfg, rule_uuid)
        entry["enabled"] = True
        tide = entry["features"].setdefault("tide", {})
        if not tide.get("default_ips"):
            tide["default_ips"] = list(pool)

    store.mutate(mutate)
    return ok()


@api.post("/rules/<rule_uuid>/release")
def release_rule(rule_uuid: str):
    store.mutate(lambda cfg: (cfg.get("rules") or {}).pop(rule_uuid, None))
    scheduler.forget(rule_uuid)
    return ok()


@api.post("/rules/<rule_uuid>/enabled")
def set_rule_enabled(rule_uuid: str):
    enabled = bool(body().get("enabled"))

    def mutate(cfg):
        rule_service.ensure_rule_entry(cfg, rule_uuid)["enabled"] = enabled

    store.mutate(mutate)
    return ok(enabled=enabled)


@api.post("/rules/<rule_uuid>/notes")
def set_ip_note(rule_uuid: str):
    data = body()
    ip = str(data.get("ip") or "").strip()
    note = str(data.get("note") or "").strip()
    if not ip:
        raise ApiError("缺少 IP")
    if len(note) > MAX_NOTE_LENGTH:
        raise ApiError(f"备注最多 {MAX_NOTE_LENGTH} 个字符")

    def mutate(cfg):
        notes = rule_service.ensure_rule_entry(cfg, rule_uuid).setdefault("ip_notes", {})
        if note:
            notes[ip] = note
        else:
            notes.pop(ip, None)

    store.mutate(mutate)
    return ok()


# ---------- 功能模块 ----------

def _feature(fid: str):
    f = feature_registry.get(fid)
    if f is None:
        raise ApiError(f"功能模块不存在：{fid}", 404)
    return f


@api.post("/rules/<rule_uuid>/features/<fid>/enabled")
def set_feature_enabled(rule_uuid: str, fid: str):
    _feature(fid)
    enabled = bool(body().get("enabled"))

    def mutate(cfg):
        rule_service.ensure_rule_entry(cfg, rule_uuid)["features"][fid]["enabled"] = enabled

    store.mutate(mutate)
    return ok(enabled=enabled)


@api.post("/rules/<rule_uuid>/features/<fid>/config")
def patch_feature_config(rule_uuid: str, fid: str):
    """浅合并功能配置；复杂功能（如潮汐）请用各自的专用接口。"""
    feature = _feature(fid)
    patch = body().get("config")
    if not isinstance(patch, dict):
        raise ApiError("config 必须是对象")

    def mutate(cfg):
        current = rule_service.ensure_rule_entry(cfg, rule_uuid)["features"].setdefault(fid, {})
        candidate = {**current, **patch}
        message = feature.validate(candidate)
        if message:
            raise ApiError(message)
        current.clear()
        current.update(candidate)
        return dict(current)

    return ok(config=store.mutate(mutate))


# ---------- 潮汐调度 ----------

def _tide(cfg: Dict[str, Any], rule_uuid: str) -> Dict[str, Any]:
    return rule_service.ensure_rule_entry(cfg, rule_uuid)["features"]["tide"]


@api.post("/rules/<rule_uuid>/tide/slots")
def save_tide_slot(rule_uuid: str):
    data = body()
    message = validate_slot(data)
    if message:
        raise ApiError(message)
    pool = _ip_pool(rule_uuid)

    def mutate(cfg):
        tide = _tide(cfg, rule_uuid)
        if not tide.get("default_ips"):
            tide["default_ips"] = list(pool)
        slot = make_slot(data, pool, existing_id=str(data.get("id") or ""))
        slots = tide.setdefault("slots", [])
        for i, s in enumerate(slots):
            if s.get("id") == slot["id"]:
                slots[i] = slot
                break
        else:
            slots.append(slot)
        return slot

    return ok(slot=store.mutate(mutate))


@api.delete("/rules/<rule_uuid>/tide/slots/<slot_id>")
def delete_tide_slot(rule_uuid: str, slot_id: str):
    def mutate(cfg):
        tide = _tide(cfg, rule_uuid)
        tide["slots"] = [s for s in tide.get("slots") or [] if s.get("id") != slot_id]

    store.mutate(mutate)
    return ok()


@api.post("/rules/<rule_uuid>/tide/slots/reorder")
def reorder_tide_slots(rule_uuid: str):
    ids = body().get("ids")
    if not isinstance(ids, list):
        raise ApiError("ids 必须是数组")

    def mutate(cfg):
        tide = _tide(cfg, rule_uuid)
        slots = tide.get("slots") or []
        by_id = {s.get("id"): s for s in slots}
        ordered = [by_id[i] for i in ids if i in by_id]
        tide["slots"] = ordered + [s for s in slots if s.get("id") not in ids]

    store.mutate(mutate)
    return ok()


def _ordered_ips_from_body(rule_uuid: str) -> List[str]:
    ips = body().get("ips")
    if not isinstance(ips, list) or not all(isinstance(i, str) for i in ips):
        raise ApiError("ips 必须是字符串数组")
    return normalize_order(ips, _ip_pool(rule_uuid))


@api.post("/rules/<rule_uuid>/tide/slots/<slot_id>/ips")
def set_tide_slot_ips(rule_uuid: str, slot_id: str):
    ordered = _ordered_ips_from_body(rule_uuid)

    def mutate(cfg):
        for s in _tide(cfg, rule_uuid).get("slots") or []:
            if s.get("id") == slot_id:
                s["ips"] = ordered
                return True
        return False

    if not store.mutate(mutate):
        raise ApiError("时间段不存在", 404)
    return ok(ips=ordered)


@api.post("/rules/<rule_uuid>/tide/order")
def set_tide_base_order(rule_uuid: str):
    """基准顺序：没有任何时间段命中时使用。"""
    ordered = _ordered_ips_from_body(rule_uuid)

    def mutate(cfg):
        _tide(cfg, rule_uuid)["default_ips"] = ordered

    store.mutate(mutate)
    return ok(default_ips=ordered)


# ---------- 下发与同步 ----------

@api.post("/rules/<rule_uuid>/apply")
def apply_now(rule_uuid: str):
    """立即按当前时间求解并下发一次（忽略「与上次一致」的短路）。"""
    client = axisnow()
    remote = client.get_rule(rule_uuid)
    if not ip_pool_of(remote):
        raise ApiError("该规则的地址池里没有 IP 类型的地址组")
    entry = (store.load_config().get("rules") or {}).get(rule_uuid) or {}
    probe = client.probe_status([rule_uuid]).get(rule_uuid) or {}
    ctx = scheduler.make_context(rule_uuid, remote, entry, probe)
    desired, notes = scheduler.resolve(entry, ctx)
    if desired.is_empty():
        reasons = "；".join(n["reason"] for n in notes if n.get("reason"))
        raise ApiError(f"当前没有任何功能需要改动这条规则。{reasons}")
    client.update_rule(rule_uuid, scheduler.apply_desired(remote, desired))
    slot = scheduler.active_slot_name(notes)
    scheduler.record(rule_uuid, desired, slot, ok=True, message="手动下发")
    return ok(order=desired.ip_order, slot_name=slot)


@api.post("/rules/<rule_uuid>/sync")
def sync_pool(rule_uuid: str):
    """把 AxisNow 最新的 IP 池同步进本地配置（新增 IP 进入各功能顺序末尾）。"""
    pool = ip_pool_of(axisnow().get_rule(rule_uuid))
    store.mutate(lambda cfg: rule_service.reconcile_pool(
        rule_service.ensure_rule_entry(cfg, rule_uuid), pool))
    return ok(pool=pool)


@api.post("/scheduler/tick")
def run_tick():
    return ok(result=scheduler.tick())
