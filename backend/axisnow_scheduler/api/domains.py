"""调度域：列表（含规则）、新建（托管 / 自托管）、删除、第三方记录预检；以及表单选项。"""

from __future__ import annotations

import re
from typing import Any, Dict, List

from .. import scheduler
from ..constants import (
    ADDRESS_POOL_MODES,
    STRATEGIES_WITHOUT_ALL_EIPS,
    STRATEGY_HELP,
    STRATEGY_LABELS,
    TRIGGER_INTERVAL_OPTIONS,
)
from ..services.views import ip_labels, ip_view, rule_view
from ..storage import config_store as store
from .common import ApiError, api, axisnow, body, ok, optional, parallel, require_confirm

SUBDOMAIN_RE = re.compile(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?")
GEO_SPLIT_VALUES = ("internal", "oversea")


def _lines_for(provider_type: str, geo: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    lines = geo.get(provider_type) or geo.get("self-hosted") or []
    # 平台托管的调度域（alibaba-cloud 后缀）实际走的是平台线路表
    if provider_type == "alibaba-cloud" and not any(o["value"] == "internal" for o in lines):
        lines = geo.get("self-hosted") or lines
    return lines


@api.get("/domains")
def list_domains():
    client = axisnow(stale=True)
    got = parallel(domains=client.list_domains, rules=client.list_rules,
                   geo=client.geo_isp_options)
    probe = client.probe_status([r.get("uuid") for r in got["rules"]])
    cfg = store.load_config()

    by_domain: Dict[str, List[Dict[str, Any]]] = {}
    for r in got["rules"]:
        by_domain.setdefault(r.get("dns_domain_uuid") or "", []).append(r)

    out = []
    for d in got["domains"]:
        provider_type = d.get("provider_type") or ""
        lines = _lines_for(provider_type, got["geo"])
        zone_conf = d.get("zone_conf") or {}
        out.append({
            "uuid": d.get("uuid"),
            "domain": d.get("domain"),
            "name": d.get("name") or "",
            "record_type": d.get("record_type"),
            "status": d.get("status"),
            "provider_type": provider_type,
            "provider_source": d.get("provider_source"),
            "zone": zone_conf.get("zone") or "",
            "zone_plan": zone_conf.get("plan") or "",
            "supports_geo_split": any(o["value"] in GEO_SPLIT_VALUES for o in lines),
            "rules": [rule_view(r, cfg, probe.get(r.get("uuid")) or {}, d.get("domain") or "")
                      for r in by_domain.get(d.get("uuid") or "", [])],
        })
    return ok(domains=out)


@api.post("/domains/check-records")
def check_records():
    data = body()
    domain = str(data.get("domain") or "").strip()
    provider_uuid = str(data.get("dns_provider_uuid") or "").strip()
    if not domain or not provider_uuid:
        raise ApiError("域名与 DNS 服务商都是必填")
    result = axisnow().check_3rd_records(domain=domain, dns_provider_uuid=provider_uuid,
                                         record_type=str(data.get("record_type") or "A"))
    return ok(result=result)


def _managed_payload(client, data: Dict[str, Any]) -> Dict[str, Any]:
    """AxisNow 托管：子域名前缀 + 平台提供的 zone 后缀。"""
    prefix = str(data.get("prefix") or "").strip().lower()
    zone_name = str(data.get("zone") or "").strip().lower()
    zone_uuid = str(data.get("dns_zone_uuid") or "").strip()
    provider_uuid = str(data.get("dns_provider_uuid") or "").strip()
    if not prefix:
        raise ApiError("请填写子域名前缀")
    if not SUBDOMAIN_RE.fullmatch(prefix):
        raise ApiError("子域名前缀格式不正确（小写字母、数字、连字符）")
    if not zone_name:
        raise ApiError("请选择托管域名后缀")
    if not provider_uuid or not zone_uuid:
        for p in client.system_dns_providers():
            zone = next((z for z in p.get("zones") or []
                         if (z.get("name") or "").lower() == zone_name), None)
            if zone:
                provider_uuid = provider_uuid or p.get("uuid") or ""
                zone_uuid = zone_uuid or zone.get("uuid") or ""
                break
    if not provider_uuid:
        raise ApiError("找不到该后缀对应的托管提供商")
    payload = {"domain": f"{prefix}.{zone_name}", "dns_provider_uuid": provider_uuid,
               "provider_source": "platform"}
    if zone_uuid:
        payload["dns_zone_uuid"] = zone_uuid
    return payload


def _self_hosted_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    domain = str(data.get("domain") or "").strip().lower()
    provider_uuid = str(data.get("dns_provider_uuid") or "").strip()
    if not domain:
        raise ApiError("请填写完整域名")
    if not provider_uuid:
        raise ApiError("请选择 DNS 服务商")
    if len(domain) > 255 or " " in domain or "." not in domain:
        raise ApiError("域名格式看起来不正确")
    payload = {"domain": domain, "dns_provider_uuid": provider_uuid,
               "provider_source": "self-hosted"}
    if data.get("dns_zone_uuid"):
        payload["dns_zone_uuid"] = str(data["dns_zone_uuid"])
    return payload


@api.post("/domains")
def create_domain():
    data = body()
    record_type = str(data.get("record_type") or "A").strip().upper()
    if record_type not in ("A", "CNAME"):
        raise ApiError("记录类型只能是 A 或 CNAME")
    mode = str(data.get("mode") or "managed").strip()
    client = axisnow()
    if mode == "managed":
        payload = _managed_payload(client, data)
    elif mode == "self":
        payload = _self_hosted_payload(data)
    else:
        raise ApiError(f"不支持的模式：{mode}")
    payload.update(record_type=record_type,
                   name=str(data.get("name") or "").strip()[:100],
                   description=str(data.get("description") or "").strip()[:255])
    return ok(domain=client.create_domain(payload))


@api.delete("/domains/<domain_uuid>")
def delete_domain(domain_uuid: str):
    require_confirm()
    client = axisnow()
    # 先记下该域下的规则，删除后一并清理本地配置
    rule_uuids = [r.get("uuid") for r in client.list_rules()
                  if r.get("dns_domain_uuid") == domain_uuid]
    client.delete_domain(domain_uuid)

    def mutate(cfg):
        for uuid in rule_uuids:
            (cfg.get("rules") or {}).pop(uuid, None)

    store.mutate(mutate)
    for uuid in rule_uuids:
        scheduler.forget(uuid)
    return ok(removed_rules=len(rule_uuids))


@api.get("/options")
def form_options():
    """新建 / 编辑域名与规则时需要的全部下拉选项。"""
    client = axisnow(stale=True)
    got = parallel(
        geo=client.geo_isp_options,
        templates=client.probe_templates,
        providers=client.list_providers,
        domains=client.list_domains,
        system_providers=optional(client.system_dns_providers),
        eips=optional(client.list_eips),
    )

    managed = [{
        "uuid": p.get("uuid"),
        "name": p.get("name"),
        "type": p.get("type"),
        "description": p.get("description"),
        "zones": [{"uuid": z.get("uuid"), "name": z.get("name")}
                  for z in p.get("zones") or [] if z.get("name")],
    } for p in got["system_providers"]]

    # 已存在调度域引用、但不在自有服务商列表里的，是平台市场托管的服务商
    known = {p.get("uuid") for p in got["providers"]} | {p["uuid"] for p in managed}
    market: Dict[str, Dict[str, Any]] = {}
    for d in got["domains"]:
        pu = d.get("dns_provider_uuid")
        if pu and pu not in known and pu not in market:
            market[pu] = {"uuid": pu, "name": f"官方托管 · {d.get('provider_type') or '未知'}",
                          "type": d.get("provider_type"), "managed": True,
                          "source": d.get("provider_source") or "platform"}

    labels = ip_labels(store.load_config())
    return ok(
        geo_isp=got["geo"],
        probe_templates=[{"uuid": t.get("uuid"), "name": t.get("name"),
                          "enabled": t.get("enabled")} for t in got["templates"]],
        providers=[{"uuid": p.get("uuid"), "name": p.get("name"), "type": p.get("type"),
                    "source": p.get("source") or "self-hosted"} for p in got["providers"]]
        + list(market.values()),
        managed_providers=managed,
        eips=[{"uuid": e.get("uuid"), "name": e.get("name") or "", "tag": e.get("tag") or "",
               "status": e.get("status") or "",
               **ip_view(e.get("ip") or e.get("address") or "", labels=labels)}
              for e in got["eips"]],
        address_pool_modes=[{"value": k, "label": v} for k, v in ADDRESS_POOL_MODES.items()],
        no_all_eips_strategies=list(STRATEGIES_WITHOUT_ALL_EIPS),
        strategies=[{"value": k, "label": v, "help": STRATEGY_HELP.get(k, "")}
                    for k, v in STRATEGY_LABELS.items()],
        trigger_intervals=TRIGGER_INTERVAL_OPTIONS,
    )
