"""仪表板聚合接口，以及全局 IP 名称。"""

from __future__ import annotations

import ipaddress
from typing import Any, Dict

from .. import scheduler
from ..clients.axisnow import ip_pool_of
from ..constants import label_for_geo_isp
from ..services.views import ip_labels, ip_view
from ..storage import config_store as store
from ..storage import history
from .common import ApiError, api, axisnow, body, ok, parallel

MAX_LABEL_LENGTH = 40


@api.get("/dashboard")
def dashboard():
    client = axisnow(stale=True)
    got = parallel(domains=client.list_domains, rules=client.list_rules,
                   templates=client.probe_templates, tasks=client.probe_tasks)
    rules = got["rules"]
    probe = client.probe_status([r.get("uuid") for r in rules])
    cfg = store.load_config()
    samples = history.samples_since(24 * 3600)
    labels = ip_labels(cfg)

    rules_per_domain: Dict[str, int] = {}
    for r in rules:
        key = r.get("dns_domain_uuid") or ""
        rules_per_domain[key] = rules_per_domain.get(key, 0) + 1

    # 节点 = 所有规则地址池里出现过的 IP（去重），附带它出现在哪些线路里
    nodes: Dict[str, Dict[str, Any]] = {}
    for r in rules:
        status_by_ip = probe.get(r.get("uuid")) or {}
        for ip in ip_pool_of(r):
            node = nodes.get(ip)
            if node is None:
                node = nodes[ip] = {
                    **ip_view(ip, labels=labels, probe=status_by_ip.get(ip)),
                    **history.uptime_stats(samples.get(ip) or []),
                    "lines": [],
                }
            label = label_for_geo_isp(r.get("geo_isp") or "default")
            if label not in node["lines"]:
                node["lines"].append(label)

    managed = cfg.get("rules") or {}
    events = history.recent_events(12)
    domain_names = {d.get("uuid"): d.get("domain") for d in got["domains"]}
    rule_names = {r.get("uuid"): (r.get("domain") or domain_names.get(r.get("dns_domain_uuid"))
                                  or "", label_for_geo_isp(r.get("geo_isp") or "default"))
                  for r in rules}
    for e in events:
        domain, line = rule_names.get(e["rule"], ("已删除的规则", ""))
        e.update(domain=domain, line=line)

    return ok(
        counts={
            "domains": len(got["domains"]),
            "rules": len(rules),
            "managed_rules": sum(1 for u in managed if u in rule_names),
            "probe_templates": len(got["templates"]),
            "probe_tasks": len(got["tasks"]),
        },
        domains=[{"uuid": d.get("uuid"), "domain": d.get("domain"),
                  "record_type": d.get("record_type"), "status": d.get("status"),
                  "provider_type": d.get("provider_type"),
                  "rules": rules_per_domain.get(d.get("uuid") or "", 0)}
                 for d in got["domains"]],
        nodes=list(nodes.values()),
        events=events,
        scheduler={**(cfg.get("scheduler") or {}),
                   **{k: v for k, v in scheduler.state_snapshot().items() if k != "applied"}},
        cloudflare=store.cf_token_meta(cfg),
    )


@api.get("/events")
def events():
    return ok(events=history.recent_events(100))


@api.put("/ip-labels")
def set_ip_label():
    """给 IP 起一个全局名称（例如「东京 Oracle」），所有页面共用。空名称表示删除。"""
    data = body()
    raw_ip = str(data.get("ip") or "").strip()
    name = str(data.get("name") or "").strip()
    try:
        ip = str(ipaddress.ip_address(raw_ip))
    except ValueError:
        raise ApiError("不是合法的 IP 地址") from None
    if len(name) > MAX_LABEL_LENGTH:
        raise ApiError(f"名称最多 {MAX_LABEL_LENGTH} 个字符")

    def mutate(cfg):
        labels = cfg.setdefault("ip_labels", {})
        if name:
            labels[ip] = {"name": name}
        else:
            labels.pop(ip, None)

    store.mutate(mutate)
    return ok()
