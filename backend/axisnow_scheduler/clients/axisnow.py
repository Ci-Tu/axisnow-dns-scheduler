"""AxisNow 客户端 API 封装。

base = https://api.axisnow.io/client/v1 ，认证 `Authorization: Bearer <token>`。
响应信封：{"success", "errors", "messages", "result", "result_info": {page, per_page, total_count}}

优先级顺序语义：action.conf.address_pool.groups[i].ips[] 的**数组顺序**即优先级，
配合 action.conf.response_strategy.election_strategy = "priority_order" 生效。
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any, Dict, List, Optional

import requests

from ..constants import PLATFORM_LINE_ORDER, group_of_geo_isp, label_for_geo_isp
from .cache import ResponseCache

log = logging.getLogger(__name__)

# PUT / POST 规则时允许提交的字段（严格按 OpenAPI 中 A 记录请求体 schema）
RULE_FIELDS = ("domain", "type", "geo_isp", "name", "description", "dns_domain_uuid",
               "action", "status")
DOMAIN_CREATE_FIELDS = ("name", "description", "domain", "dns_provider_uuid", "dns_zone_uuid",
                        "record_type", "provider_source")

PER_PAGE = 100
MAX_PAGES = 50

# 所有实例共享：20 秒内视为新鲜；展示类接口在 10 分钟内可以先用旧值再后台刷新
_CACHE = ResponseCache(fresh_ttl=20.0, stale_ttl=600.0)


class AxisNowError(RuntimeError):
    """调用 AxisNow API 失败。message 已确保不含凭据。"""

    def __init__(self, message: str, status: Optional[int] = None, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


def _summarize_errors(payload: Any) -> str:
    """把 errors 压成一行可读文本，避免把整包响应（可能含地址）打进日志。"""
    if not isinstance(payload, dict):
        return "接口返回格式异常"
    errs = payload.get("errors")
    if isinstance(errs, list) and errs:
        parts = []
        for item in errs[:3]:
            if isinstance(item, dict):
                code = item.get("code") or item.get("error_code") or ""
                msg = item.get("message") or item.get("error_message") or ""
                parts.append(f"{code} {msg}".strip())
            else:
                parts.append(str(item)[:120])
        return "; ".join(p for p in parts if p) or "接口返回错误"
    msgs = payload.get("messages")
    if isinstance(msgs, list) and msgs:
        return str(msgs[0])[:200]
    return "接口返回错误"


def clear_cache() -> None:
    _CACHE.clear()


class AxisNowClient:
    """allow_stale=True 只给纯展示接口用；任何「读后写」路径都必须用默认值 False，
    否则可能基于 10 分钟前的规则去覆盖线上。"""

    def __init__(self, base_url: str, token: str, *, timeout: int = 25,
                 allow_stale: bool = False):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.timeout = timeout
        self.allow_stale = allow_stale
        self.session = requests.Session()
        self.session.trust_env = False  # 不继承容器里的代理环境变量

    # ---------- 底层 ----------

    def _fetch(self, method: str, path: str, params: Any = None, json_body: Any = None) -> Any:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        try:
            resp = self.session.request(method, f"{self.base_url}{path}", params=params,
                                        json=json_body, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            # 只输出异常类型，绝不打印请求头
            raise AxisNowError(f"网络请求失败：{type(exc).__name__}") from exc
        try:
            payload = resp.json()
        except ValueError:
            raise AxisNowError(f"接口返回非 JSON（HTTP {resp.status_code}）",
                               status=resp.status_code) from None
        if resp.status_code >= 400 or not payload.get("success", False):
            raise AxisNowError(
                f"接口报错（HTTP {resp.status_code}）：{_summarize_errors(payload)}",
                status=resp.status_code, detail=payload.get("errors"))
        return payload

    def request(self, method: str, path: str, *, params: Any = None, json_body: Any = None,
                read: Optional[bool] = None) -> Any:
        """read=None 时 GET 视为读。注意 /edge_probe/tasks/status 等「POST 形式的读」
        必须显式传 read=True，否则会被当成写操作清空缓存。"""
        if not self.token:
            raise AxisNowError("尚未配置 AxisNow API Token")
        if read is None:
            read = method == "GET"
        if not read:
            payload = self._fetch(method, path, params, json_body)
            _CACHE.clear()
            return payload

        key = f"{self.base_url}|{self.token[-6:]}|{method} {path}|" + json.dumps(
            [params, json_body], sort_keys=True, ensure_ascii=False)

        def load() -> Any:
            return self._fetch(method, path, params, json_body)

        cached = _CACHE.lookup(key, allow_stale=self.allow_stale, refresh=load)
        if cached is not None:
            return cached
        payload = load()
        _CACHE.put(key, payload)
        return payload

    def _list(self, path: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """拉取全部分页。服务端要求 per_page >= 5。"""
        out: List[Dict[str, Any]] = []
        for page in range(1, MAX_PAGES + 1):
            payload = self.request("GET", path,
                                   params={**(params or {}), "page": page, "per_page": PER_PAGE})
            items = payload.get("result") or []
            out.extend(items)
            total = (payload.get("result_info") or {}).get("total_count")
            if not items or len(items) < PER_PAGE or (total is not None and len(out) >= total):
                break
        return out

    # ---------- 调度域 ----------

    def list_domains(self) -> List[Dict[str, Any]]:
        return self._list("/dns_routing_domains")

    def create_domain(self, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = {k: body[k] for k in DOMAIN_CREATE_FIELDS if body.get(k) not in (None, "")}
        return self.request("POST", "/dns_routing_domains", json_body=payload).get("result") or {}

    def delete_domain(self, domain_uuid: str) -> None:
        self.request("DELETE", f"/dns_routing_domains/{domain_uuid}")

    def check_3rd_records(self, *, domain: str, dns_provider_uuid: str,
                          record_type: str = "A") -> Dict[str, Any]:
        """新建调度域之前预检：该域名在第三方 DNS 上是否已有冲突记录。"""
        body = {"domain": domain, "dns_provider_uuid": dns_provider_uuid,
                "record_type": record_type}
        return self.request("POST", "/dns_routing_domains/3rd_records", json_body=body,
                            read=True).get("result") or {}

    # ---------- 规则 ----------

    def list_rules(self) -> List[Dict[str, Any]]:
        return self._list("/dns_routing_rules")

    def get_rule(self, rule_uuid: str) -> Dict[str, Any]:
        result = self.request("GET", f"/dns_routing_rules/{rule_uuid}").get("result")
        if not isinstance(result, dict):
            raise AxisNowError("未取到规则详情")
        return result

    def create_rule(self, body: Dict[str, Any]) -> Dict[str, Any]:
        payload = {k: body[k] for k in RULE_FIELDS if k in body}
        return self.request("POST", "/dns_routing_rules", json_body=payload).get("result") or {}

    def update_rule(self, rule_uuid: str, rule: Dict[str, Any]) -> Dict[str, Any]:
        payload = {k: rule[k] for k in RULE_FIELDS if k in rule}
        return self.request("PUT", f"/dns_routing_rules/{rule_uuid}",
                            json_body=payload).get("result") or {}

    def delete_rule(self, rule_uuid: str) -> None:
        self.request("DELETE", f"/dns_routing_rules/{rule_uuid}")

    # ---------- 拨测 ----------

    def probe_status(self, rule_uuids: List[str]) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """按规则批量查询地址拨测状态：{rule_uuid: {ip: {"status", "latency"}}}。

        拿不到时返回空字典而不是抛错 —— 拨测状态是锦上添花，不能拖垮整个页面。
        AxisNow 对 HTTP 拨测返回的 avg_connect_latency 恒为 0，0 视为「无数据」。
        """
        uuids = sorted(dict.fromkeys(u for u in rule_uuids if u))
        if not uuids:
            return {}
        body = {
            "filter_type": "dns_routing_rules",
            "filter": {"or": [{"and": [
                {"field": "dns_rule_uuid", "operator": "in", "value": uuids}]}]},
        }
        try:
            payload = self.request("POST", "/edge_probe/tasks/status", json_body=body, read=True)
        except AxisNowError as exc:
            log.info("拨测状态获取失败：%s", exc)
            return {}

        out: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for entry in payload.get("result") or []:
            if not isinstance(entry, dict) or not entry.get("uuid"):
                continue
            bucket = out.setdefault(entry["uuid"], {})
            for item in entry.get("list") or entry.get("addresses") or []:
                if isinstance(item, dict) and item.get("target"):
                    bucket[item["target"]] = {
                        "status": item.get("status") or "unknown",
                        "latency": item.get("avg_connect_latency") or None,
                    }
        return out

    def probe_tasks(self) -> List[Dict[str, Any]]:
        return self._list("/edge_probe/tasks")

    def delete_probe_task(self, task_uuid: str) -> None:
        self.request("DELETE", f"/edge_probe/tasks/{task_uuid}")

    def probe_templates(self) -> List[Dict[str, Any]]:
        return self._list("/edge_probe/templates")

    def get_probe_template(self, template_uuid: str) -> Dict[str, Any]:
        return self.request("GET", f"/edge_probe/templates/{template_uuid}").get("result") or {}

    def create_probe_template(self, body: Dict[str, Any]) -> Dict[str, Any]:
        return self.request("POST", "/edge_probe/templates", json_body=body).get("result") or {}

    # ---------- 线路、服务商、EIP ----------

    def geo_isp_options(self) -> Dict[str, List[Dict[str, Any]]]:
        """线路表：{provider_type: [{"value","label","display","group","plan"}...]}。
        同一 provider_type 的多个 plan 合并去重。"""
        raw = self.request("GET", "/policy/metadata/geo_isp").get("result")
        if isinstance(raw, dict):
            raw = raw.get("list") or []
        out: Dict[str, List[Dict[str, Any]]] = {}
        for group in raw or []:
            if not isinstance(group, dict):
                continue
            bucket = out.setdefault(group.get("provider_type") or "unknown", [])
            seen = {item["value"] for item in bucket}
            for plan in group.get("list") or []:
                for opt in (plan or {}).get("options") or []:
                    value = opt.get("value")
                    if value is None or value in seen:
                        continue
                    seen.add(value)
                    display = opt.get("displayName") or ""
                    bucket.append({
                        "value": value,
                        "label": label_for_geo_isp(str(value), display),
                        "display": display,
                        "group": group_of_geo_isp(str(value), display),
                        "plan": (plan or {}).get("provider_plan"),
                    })
            bucket.sort(key=lambda x: (
                PLATFORM_LINE_ORDER.index(x["value"])
                if x["value"] in PLATFORM_LINE_ORDER else 99, x["label"]))
        return out

    def system_dns_providers(self) -> List[Dict[str, Any]]:
        """平台托管的 DNS 提供商及其 zone（后缀）。不在 /dns_providers 里，必须单独 POST。"""
        return self.request("POST", "/system_dns_providers", json_body={},
                            read=True).get("result") or []

    def list_providers(self) -> List[Dict[str, Any]]:
        return self._list("/dns_providers")

    def list_eips(self) -> List[Dict[str, Any]]:
        return self._list("/eips")


# ---------- 规则对象工具 ----------

def ip_pool_of(rule: Dict[str, Any]) -> List[str]:
    """第一个 type=ip 地址组里的 IP（按优先级顺序）。"""
    conf = ((rule.get("action") or {}).get("conf")) or {}
    for g in (conf.get("address_pool") or {}).get("groups") or []:
        if g.get("type") == "ip":
            return list(g.get("ips") or [])
    return []


def pool_shape(rule: Dict[str, Any]) -> List[str]:
    """地址池里各分组的类型，形如 ['ip', 'eip_tag']。"""
    conf = ((rule.get("action") or {}).get("conf")) or {}
    return [g.get("type") for g in (conf.get("address_pool") or {}).get("groups") or []]


def election_strategy(rule: Dict[str, Any]) -> Optional[str]:
    conf = ((rule.get("action") or {}).get("conf")) or {}
    return (conf.get("response_strategy") or {}).get("election_strategy")


def set_ip_order(rule: Dict[str, Any], ordered_ips: List[str]) -> Dict[str, Any]:
    """在规则副本上把第一个 type=ip 地址组按 ordered_ips 重排。

    不在池里的 IP 忽略；池里有但没列出的按原顺序补到末尾，保证新增 IP 不会被丢掉。
    """
    new_rule = copy.deepcopy(rule)
    pool = new_rule.setdefault("action", {}).setdefault("conf", {}).setdefault("address_pool", {})
    target = next((g for g in pool.get("groups") or [] if g.get("type") == "ip"), None)
    if target is None:
        raise AxisNowError("该规则的地址池中没有 IP 类型的地址组，无法调整顺序")
    current = list(target.get("ips") or [])
    known = set(current)
    ordered = [ip for ip in dict.fromkeys(ordered_ips) if ip in known]
    ordered += [ip for ip in current if ip not in set(ordered)]
    target["ips"] = ordered
    return new_rule
