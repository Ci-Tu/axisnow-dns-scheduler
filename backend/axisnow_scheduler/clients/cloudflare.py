"""Cloudflare API v4 客户端（只用 DNS 记录相关能力）。

用途：把 AxisNow 调度域一键 CNAME 到自己的域名上。
所需 Token 权限：Zone → DNS → Edit。

⚠️ 接入 AxisNow 的记录必须是 DNS only（proxied=false）：开了 CF 代理，访客拿到的是
CF 的 IP，AxisNow 的按线路调度就完全失效了。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import requests

from .cache import ResponseCache

log = logging.getLogger(__name__)

API_BASE = "https://api.cloudflare.com/client/v4"

# 这些记录类型不支持 proxied 字段
TYPES_WITHOUT_PROXY = ("MX", "TXT", "NS", "SRV", "CAA", "LOC", "PTR")

_CACHE = ResponseCache(fresh_ttl=30.0, stale_ttl=600.0)


class CloudflareError(RuntimeError):
    """调用 Cloudflare API 失败。消息已确保不含凭据。"""

    def __init__(self, message: str, status: Optional[int] = None,
                 errors: Optional[Any] = None, need_permission: bool = False):
        super().__init__(message)
        self.status = status
        self.errors = errors
        # 权限不足（HTTP 401/403 或 CF code 10000 / 9109），前端据此给出更明确的提示
        self.need_permission = need_permission


def _summarize(errors: Any) -> str:
    if not isinstance(errors, list) or not errors:
        return "接口返回错误"
    parts = []
    for item in errors[:3]:
        if isinstance(item, dict):
            parts.append(f"[{item.get('code')}] {item.get('message') or ''}".strip())
        else:
            parts.append(str(item)[:120])
    return "; ".join(p for p in parts if p)


class CloudflareClient:
    def __init__(self, token: str, *, timeout: int = 25, allow_stale: bool = False):
        self.token = token or ""
        self.timeout = timeout
        self.allow_stale = allow_stale
        self.session = requests.Session()
        self.session.trust_env = False

    def _fetch(self, method: str, path: str, params: Any = None, json_body: Any = None) -> Any:
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        try:
            resp = self.session.request(method, f"{API_BASE}{path}", params=params,
                                        json=json_body, headers=headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise CloudflareError(f"网络请求失败：{type(exc).__name__}") from exc
        try:
            payload = resp.json()
        except ValueError:
            raise CloudflareError(f"接口返回非 JSON（HTTP {resp.status_code}）",
                                  status=resp.status_code) from None
        if resp.status_code >= 400 or not payload.get("success", False):
            errors = payload.get("errors")
            need_perm = resp.status_code in (401, 403) or any(
                isinstance(e, dict) and e.get("code") in (10000, 9109) for e in errors or [])
            raise CloudflareError(
                f"Cloudflare 报错（HTTP {resp.status_code}）：{_summarize(errors)}",
                status=resp.status_code, errors=errors, need_permission=need_perm)
        return payload

    def _request(self, method: str, path: str, *, params: Any = None,
                 json_body: Any = None) -> Any:
        if not self.token:
            raise CloudflareError("尚未配置 Cloudflare API Token")
        if method != "GET":
            payload = self._fetch(method, path, params, json_body)
            _CACHE.clear()
            return payload
        key = f"{self.token[-6:]}|{path}|" + json.dumps(params, sort_keys=True)

        def load() -> Any:
            return self._fetch(method, path, params, None)

        cached = _CACHE.lookup(key, allow_stale=self.allow_stale, refresh=load)
        if cached is not None:
            return cached
        payload = load()
        _CACHE.put(key, payload)
        return payload

    def verify_token(self) -> Dict[str, Any]:
        """校验 Token；不走缓存，保证「保存 Token」时拿到的是实时结果。"""
        if not self.token:
            raise CloudflareError("尚未配置 Cloudflare API Token")
        return self._fetch("GET", "/user/tokens/verify").get("result") or {}

    def list_zones(self) -> List[Dict[str, Any]]:
        payload = self._request("GET", "/zones", params={"per_page": 50, "page": 1})
        return [{
            "id": z.get("id"),
            "name": z.get("name"),
            "status": z.get("status"),
            "type": z.get("type"),
            "account": (z.get("account") or {}).get("name"),
        } for z in payload.get("result") or []]

    def list_records(self, zone_id: str, *, name: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"per_page": 100, "page": 1}
        if name:
            params["name"] = name
        payload = self._request("GET", f"/zones/{zone_id}/dns_records", params=params)
        return [{
            "id": r.get("id"),
            "type": r.get("type"),
            "name": r.get("name"),
            "content": r.get("content"),
            "proxied": r.get("proxied"),
            "ttl": r.get("ttl"),
            "comment": r.get("comment"),
            "zone_id": zone_id,
        } for r in payload.get("result") or []]

    def create_record(self, zone_id: str, *, type: str, name: str, content: str,  # noqa: A002
                      ttl: int = 1, proxied: bool = False, comment: str = "") -> Dict[str, Any]:
        body: Dict[str, Any] = {"type": type, "name": name, "content": content, "ttl": int(ttl)}
        if type.upper() not in TYPES_WITHOUT_PROXY:
            body["proxied"] = bool(proxied)
        if comment:
            body["comment"] = comment[:100]
        return self._request("POST", f"/zones/{zone_id}/dns_records",
                             json_body=body).get("result") or {}

    def delete_record(self, zone_id: str, record_id: str) -> None:
        self._request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")
