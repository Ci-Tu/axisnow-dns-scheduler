"""把 AxisNow 原始对象 + 本地配置 + 功能求解结果，合成前端视图模型。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import features as feature_registry
from .. import scheduler
from ..clients.axisnow import election_strategy, ip_pool_of, pool_shape
from ..constants import STRATEGY_LABELS, label_for_geo_isp, region_of_geo_isp
from . import geo
from .rules import eip_uuids_of, pool_mode_of


def ip_labels(cfg: Dict[str, Any]) -> Dict[str, str]:
    return {ip: (v or {}).get("name") or "" for ip, v in (cfg.get("ip_labels") or {}).items()}


def ip_view(ip: str, *, labels: Dict[str, str], note: str = "",
            probe: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """所有页面里「一个 IP」的统一表示：国旗、运营商、全局名称、规则内备注、拨测状态。"""
    return {"ip": ip, "name": labels.get(ip, ""), "note": note, "probe": probe,
            "geo": geo.lookup(ip)}


def probe_summary(pool: List[str], probe: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    known = [probe[ip] for ip in pool if probe.get(ip)]
    if not pool or not known:
        return {"known": False, "available": 0, "unavailable": 0, "total": len(pool)}
    latencies = [x["latency"] for x in known if isinstance(x.get("latency"), (int, float))]
    return {
        "known": True,
        "available": sum(1 for x in known if x.get("status") == "available"),
        "unavailable": sum(1 for x in known if x.get("status") == "unavailable"),
        "total": len(pool),
        "monitored": len(known),
        "latency_avg": round(sum(latencies) / len(latencies), 1) if latencies else None,
    }


def rule_view(remote: Dict[str, Any], cfg: Dict[str, Any],
              probe: Optional[Dict[str, Dict[str, Any]]] = None,
              domain_name: str = "") -> Dict[str, Any]:
    uuid = remote.get("uuid") or ""
    local = (cfg.get("rules") or {}).get(uuid) or {}
    notes = local.get("ip_notes") or {}
    probe = probe or {}
    pool = ip_pool_of(remote)
    conf = ((remote.get("action") or {}).get("conf")) or {}
    response = conf.get("response_strategy") or {}
    ctx = scheduler.make_context(uuid, remote, local, probe)

    feature_cards: List[Dict[str, Any]] = []
    for f in feature_registry.all_features():
        fcfg = (local.get("features") or {}).get(f.id) or dict(f.default_config())
        ok, reason = f.applicable(ctx)
        try:
            summary = f.summary(fcfg, ctx) if ok else {}
        except Exception:  # noqa: BLE001 - 摘要只用于展示
            summary = {}
        feature_cards.append({
            "id": f.id, "name": f.name, "description": f.description, "ui": f.ui,
            "order": f.order, "enabled": bool(fcfg.get("enabled", True)),
            "applicable": ok, "reason": reason, "config": fcfg, "summary": summary,
        })

    desired = None
    if local:
        desired, _ = scheduler.resolve(local, ctx)
    strategy = election_strategy(remote) or ""
    geo_isp = remote.get("geo_isp") or "default"
    labels = ip_labels(cfg)

    return {
        "uuid": uuid,
        "name": remote.get("name") or "",
        "description": remote.get("description") or "",
        "domain": remote.get("domain") or domain_name,
        "dns_domain_uuid": remote.get("dns_domain_uuid") or "",
        "record_type": remote.get("type") or remote.get("record_type"),
        "geo_isp": geo_isp,
        "geo_isp_label": label_for_geo_isp(geo_isp),
        "geo_isp_region": region_of_geo_isp(geo_isp),
        "status": remote.get("status"),
        "group_types": pool_shape(remote),
        "election_strategy": strategy,
        "election_label": STRATEGY_LABELS.get(strategy, strategy or "—"),
        "ip_quantity": response.get("ip_quantity"),
        "trigger_interval": response.get("trigger_interval"),
        "edge_probe_templates": conf.get("edge_probe_template_uuid") or [],
        "ttl": (conf.get("ttl_conf") or {}).get("ttl"),
        "created_at": remote.get("created_at") or "",
        "updated_at": remote.get("updated_at") or "",
        "managed": bool(local),
        "enabled": bool(local.get("enabled", True)),
        "pool": pool,
        "pool_mode": pool_mode_of(remote),
        "eip_uuids": eip_uuids_of(remote),
        "ips": [ip_view(ip, labels=labels, note=notes.get(ip, ""), probe=probe.get(ip))
                for ip in pool],
        "probe_summary": probe_summary(pool, probe),
        "features": feature_cards,
        "last_applied": scheduler.last_applied(uuid),
        "desired_order": desired.ip_order if desired else None,
    }


def template_probe_target(conf: Dict[str, Any]) -> Dict[str, Any]:
    """从拨测模板 conf 里抽出「探测方式」—— 纯配置事实，不推测可用性。"""
    adv = (((conf or {}).get("probe_policy") or {}).get("settings") or {}).get("advanced") or {}
    host = adv.get("host") or {}
    scheme = (adv.get("scheme") or "https").lower()
    port = adv.get("port") or 443
    path = adv.get("path") or "/"
    host_mode = host.get("mode") or "follow_target"
    return {
        "scheme": scheme, "port": port, "path": path, "method": adv.get("method") or "GET",
        "host_mode": host_mode, "host_value": host.get("value") or "",
        "url_hint": f"{scheme}://<目标IP>:{port}{path}",
        "host_hint": "Host = 目标 IP" if host_mode == "follow_target"
        else f"Host = {host.get('value') or '(未设置)'}",
    }
