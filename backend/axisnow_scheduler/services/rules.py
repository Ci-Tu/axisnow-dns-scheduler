"""规则的构建与本地配置维护。

这里只放纯逻辑（无 HTTP、无 Flask），便于测试：
- 表单 → AxisNow 规则 action 的构建与校验
- 本地规则配置（纳管、IP 备注、各功能里保存的 IP 顺序）的维护
"""

from __future__ import annotations

import ipaddress
from typing import Any, Dict, List, Optional

from ..constants import (
    ADDRESS_POOL_MODES,
    NON_IP_GROUP_TYPES,
    STRATEGIES_WITHOUT_ALL_EIPS,
    STRATEGY_LABELS,
    TRIGGER_INTERVAL_OPTIONS,
)
from ..features import all_features
from ..features.tide import normalize_order

MAX_IPS_PER_GROUP = 50
# Cloudflare 的 ttl_conf 不接受 plan 字段
PROVIDERS_WITHOUT_PLAN = ("cloudflare",)


class ValidationError(ValueError):
    """用户输入不合法，消息可直接展示给用户。"""


# ---------- 表单 → action ----------

def normalize_ips(raw: Any, *, allow_empty: bool = False) -> List[str]:
    """校验并规范化 IP 列表：去重、保序、必须是合法 IPv4/IPv6。"""
    if not isinstance(raw, list):
        raise ValidationError("IP 列表格式不正确")
    out: List[str] = []
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        try:
            ip = str(ipaddress.ip_address(text))
        except ValueError:
            raise ValidationError(f"不是合法的 IP 地址：{text}") from None
        if ip not in out:
            out.append(ip)
    if not out and not allow_empty:
        raise ValidationError("地址池至少需要一个 IP")
    if len(out) > MAX_IPS_PER_GROUP:
        raise ValidationError(f"单个地址组最多 {MAX_IPS_PER_GROUP} 个 IP")
    return out


def build_address_pool(mode: str, *, ips: Optional[List[str]] = None,
                       eip_uuids: Optional[List[str]] = None,
                       extra_groups: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """按 AxisNow 的三种地址池模式构造 address_pool。

    - all_eips    : {"mode":"all_valid_eips"}
    - custom_eips : {"mode":"customize","groups":[{type:eip, eip_uuids}]}
    - custom_ips  : {"mode":"customize","groups":[{type:ip, ips}]}
    extra_groups 里的 eip_tag / domain 等分组原样保留。
    """
    if mode not in ADDRESS_POOL_MODES:
        raise ValidationError(f"不支持的地址池模式：{mode}")
    if mode == "all_eips":
        return {"mode": "all_valid_eips"}
    if mode == "custom_eips":
        uuids = [str(u).strip() for u in eip_uuids or [] if str(u).strip()]
        if not uuids:
            raise ValidationError("「指定 EIP」至少需要选择一个 EIP")
        head: Dict[str, Any] = {"type": "eip", "eip_uuids": uuids}
    else:
        if not ips:
            raise ValidationError("「自定义 IP」至少需要一个 IP 地址")
        head = {"type": "ip", "ips": list(ips)}
    extras = [g for g in extra_groups or []
              if isinstance(g, dict) and g.get("type") in NON_IP_GROUP_TYPES
              and g.get("type") != head["type"]]
    return {"mode": "customize", "groups": [head, *extras]}


def build_action(*, strategy: str, ip_quantity: Any, pool: Dict[str, Any],
                 probe_template: str = "", ttl_conf: Optional[Dict[str, Any]] = None,
                 trigger_interval: Any = None) -> Dict[str, Any]:
    """构造规则的 action（A 记录 / ip_election）。"""
    if strategy not in STRATEGY_LABELS:
        raise ValidationError(f"不支持的选取策略：{strategy}")
    try:
        qty = int(ip_quantity)
    except (TypeError, ValueError):
        raise ValidationError("返回地址数量必须是整数") from None
    if not 1 <= qty <= 10:
        raise ValidationError("返回地址数量必须在 1 到 10 之间")
    if pool.get("mode") == "all_valid_eips" and strategy in STRATEGIES_WITHOUT_ALL_EIPS:
        raise ValidationError("「所有 EIP」不能配合「顺序」选取策略；AxisNow 只允许它搭配随机或优选")

    response: Dict[str, Any] = {"ip_quantity": qty, "election_strategy": strategy}
    if strategy == "quality_optimized":
        try:
            interval = int(trigger_interval or TRIGGER_INTERVAL_OPTIONS[0])
        except (TypeError, ValueError):
            interval = TRIGGER_INTERVAL_OPTIONS[0]
        if interval not in TRIGGER_INTERVAL_OPTIONS:
            raise ValidationError("优选的评估周期只能是 5 或 10 分钟")
        response["trigger_interval"] = interval

    return {
        "method": "ip_election",
        "__meta__": {"responseStrategyTtlUnit": "seconds"},
        "conf": {
            "address_pool": pool,
            "edge_probe_template_uuid": [probe_template] if probe_template else [],
            "response_strategy": response,
            "ttl_conf": dict(ttl_conf or {"ttl": 60}),
        },
    }


def parse_ttl(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        ttl = int(value)
    except (TypeError, ValueError):
        raise ValidationError("TTL 必须是整数") from None
    if not 1 <= ttl <= 86400:
        raise ValidationError("TTL 必须在 1–86400 秒之间")
    return ttl


def derive_ttl_conf(domain: Dict[str, Any], sibling_rules: List[Dict[str, Any]],
                    ttl: Optional[int] = None) -> Dict[str, Any]:
    """新规则的 ttl_conf：优先复用同域已有规则（字段组合一定合法），否则按服务商拼最小集合。"""
    for r in sibling_rules:
        tc = (((r.get("action") or {}).get("conf")) or {}).get("ttl_conf")
        if isinstance(tc, dict) and tc:
            out = dict(tc)
            if ttl:
                out["ttl"] = ttl
            return out
    provider_type = domain.get("provider_type") or ""
    plan = (domain.get("zone_conf") or {}).get("plan")
    out: Dict[str, Any] = {"ttl": ttl or 60}
    if provider_type:
        out["provider_type"] = provider_type
    if plan and provider_type not in PROVIDERS_WITHOUT_PLAN:
        out["plan"] = plan
    return out


def pool_mode_of(rule: Dict[str, Any]) -> str:
    pool = (((rule.get("action") or {}).get("conf") or {}).get("address_pool")) or {}
    if pool.get("mode") == "all_valid_eips":
        return "all_eips"
    if any(g.get("type") == "eip" for g in pool.get("groups") or []):
        return "custom_eips"
    return "custom_ips"


def eip_uuids_of(rule: Dict[str, Any]) -> List[str]:
    pool = (((rule.get("action") or {}).get("conf") or {}).get("address_pool")) or {}
    return [u for g in pool.get("groups") or [] if g.get("type") == "eip"
            for u in g.get("eip_uuids") or []]


def build_updated_rule(remote: Dict[str, Any], body: Dict[str, Any]) -> Dict[str, Any]:
    """编辑规则：body 里没给的字段一律沿用线上现状。返回 PUT 体。"""
    conf = ((remote.get("action") or {}).get("conf")) or {}
    old_pool = conf.get("address_pool") or {}
    old_groups = old_pool.get("groups") or []
    response = conf.get("response_strategy") or {}

    pool_mode = str(body.get("pool_mode") or pool_mode_of(remote)).strip()
    ips: List[str] = []
    if pool_mode == "custom_ips":
        raw = body.get("ips")
        if raw is None:
            raw = next((g.get("ips") or [] for g in old_groups if g.get("type") == "ip"), [])
        ips = normalize_ips(list(raw))
    eip_uuids = None
    if pool_mode == "custom_eips":
        eip_uuids = body.get("eip_uuids")
        if eip_uuids is None:
            eip_uuids = eip_uuids_of(remote)
    pool = build_address_pool(pool_mode, ips=ips, eip_uuids=eip_uuids, extra_groups=old_groups)

    ttl_conf = dict(conf.get("ttl_conf") or {}) or {"ttl": 60}
    ttl = parse_ttl(body.get("ttl"))
    if ttl:
        ttl_conf["ttl"] = ttl

    if "edge_probe_template_uuid" in body:
        probe_template = str(body.get("edge_probe_template_uuid") or "").strip()
    else:
        probe_template = (conf.get("edge_probe_template_uuid") or [""])[0] or ""

    action = build_action(
        strategy=body.get("election_strategy") or response.get("election_strategy")
        or "priority_order",
        ip_quantity=body.get("ip_quantity") or response.get("ip_quantity") or 1,
        pool=pool,
        probe_template=probe_template,
        ttl_conf=ttl_conf,
        trigger_interval=body.get("trigger_interval") or response.get("trigger_interval"),
    )

    payload: Dict[str, Any] = {k: remote[k] for k in ("domain", "type", "dns_domain_uuid")
                               if remote.get(k) is not None}
    payload["geo_isp"] = str(body.get("geo_isp") or remote.get("geo_isp") or "default").strip()
    name = body.get("name")
    payload["name"] = str(remote.get("name") or "" if name is None else name).strip()[:100]
    desc = body.get("description")
    payload["description"] = str(remote.get("description") or "" if desc is None else desc)[:255]
    status = body.get("status") or remote.get("status") or "active"
    payload["status"] = status if status in ("active", "paused") else "active"
    payload["action"] = action
    return payload


# ---------- 本地规则配置 ----------

def ensure_rule_entry(cfg: Dict[str, Any], rule_uuid: str) -> Dict[str, Any]:
    """取（必要时创建）某条规则的本地配置，并补齐所有功能的默认配置。"""
    rules = cfg.setdefault("rules", {})
    entry = rules.get(rule_uuid)
    if not isinstance(entry, dict):
        entry = rules[rule_uuid] = {}
    entry.setdefault("enabled", True)
    entry.setdefault("note", "")
    entry.setdefault("ip_notes", {})
    features = entry.setdefault("features", {})
    for f in all_features():
        features.setdefault(f.id, dict(f.default_config()))
    return entry


def reconcile_pool(entry: Dict[str, Any], pool: List[str]) -> None:
    """地址池变化后，把本地各功能里保存的 IP 顺序与备注对齐到新池。

    - 已不在池里的 IP 从顺序和备注中移除；
    - 池里新增的 IP 追加到各顺序末尾。
    地址池不是 IP 模式（pool 为空）时不做任何改动，避免误删配置。
    """
    if not pool:
        return
    pool_set = set(pool)
    for fcfg in (entry.get("features") or {}).values():
        if not isinstance(fcfg, dict):
            continue
        if isinstance(fcfg.get("default_ips"), list) and fcfg["default_ips"]:
            fcfg["default_ips"] = normalize_order(fcfg["default_ips"], pool)
        for slot in fcfg.get("slots") or []:
            if isinstance(slot, dict) and isinstance(slot.get("ips"), list):
                slot["ips"] = normalize_order(slot["ips"], pool)
    notes = entry.get("ip_notes") or {}
    for ip in [ip for ip in notes if ip not in pool_set]:
        notes.pop(ip, None)
