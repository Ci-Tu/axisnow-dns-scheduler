"""拨测：总览诊断、历史采样、统一模板创建、批量应用、任务清理。"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List

from .. import scheduler
from ..clients.axisnow import AxisNowError
from ..constants import label_for_geo_isp, region_of_geo_isp
from ..services.views import ip_labels, ip_view, template_probe_target
from ..storage import config_store as store
from ..storage import history
from .common import ApiError, api, axisnow, body, ok, parallel, require_confirm

HOSTNAME_RE = re.compile(r"[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+")
# 判定条件沿用官方：状态码 4xx/5xx 或首字节超过 2 秒视为异常
DEFAULT_CONDITION = ("(probe.probe_http_status_code ge 400 && "
                     "probe.probe_http_status_code le 599) or probe.probe_http_ttfb_ms gt 2000")


def _probe_template_uuid(rule: Dict[str, Any]) -> str:
    return ((((rule.get("action") or {}).get("conf") or {})
             .get("edge_probe_template_uuid")) or [""])[0] or ""


@api.get("/probe/overview")
def probe_overview():
    client = axisnow(stale=True)
    got = parallel(templates=client.probe_templates, tasks=client.probe_tasks,
                   rules=client.list_rules)
    templates, tasks, rules = got["templates"], got["tasks"], got["rules"]
    rule_probe = client.probe_status([r.get("uuid") for r in rules])
    tmap = {t.get("uuid"): t for t in templates}

    task_count: Dict[str, int] = {}
    targets: Dict[str, List[str]] = {}   # ip -> 引用它的模板名
    for tk in tasks:
        conf = tk.get("conf") or {}
        tu = conf.get("template_uuid") or ""
        task_count[tu] = task_count.get(tu, 0) + 1
        for ip in conf.get("target") or []:
            targets.setdefault(ip, []).append((tmap.get(tu) or {}).get("name") or tu[:8])

    rules_by_template: Dict[str, List[str]] = {}
    for r in rules:
        for tu in (((r.get("action") or {}).get("conf") or {})
                   .get("edge_probe_template_uuid") or []):
            rules_by_template.setdefault(tu, []).append(r.get("uuid"))

    live: Dict[str, str] = {}
    for r in rules:
        for ip, item in (rule_probe.get(r.get("uuid")) or {}).items():
            if item.get("status"):
                live[ip] = item["status"]

    def health(template_uuid: str) -> Dict[str, Any]:
        counts = {"available": 0, "unavailable": 0, "unknown": 0}
        for ru in rules_by_template.get(template_uuid, []):
            for item in (rule_probe.get(ru) or {}).values():
                status = item.get("status")
                counts[status if status in counts else "unknown"] += 1
        total = sum(counts.values())
        return {"known": total > 0, "total": total, **counts}

    out_templates = [{
        "uuid": t.get("uuid"),
        "name": t.get("name"),
        "description": t.get("description") or "",
        "enabled": t.get("enabled"),
        "referenced_count": t.get("referenced_count") or 0,
        "interval": (((t.get("conf") or {}).get("probe_policy") or {}).get("probe_interval")),
        "task_count": task_count.get(t.get("uuid"), 0),
        "health": health(t.get("uuid")),
        **template_probe_target(t.get("conf") or {}),
    } for t in templates]

    labels = ip_labels(store.load_config())
    out_tasks = []
    for tk in tasks:
        conf = tk.get("conf") or {}
        ip = (conf.get("target") or [""])[0]
        out_tasks.append({
            "uuid": tk.get("uuid"),
            "name": tk.get("name"),
            "enabled": tk.get("enabled"),
            "target": ip_view(ip, labels=labels, probe={"status": live.get(ip, "unknown")}),
            "template_uuid": conf.get("template_uuid") or "",
            "template_name": (tmap.get(conf.get("template_uuid")) or {}).get("name") or "",
        })

    duplicates = [{"ip": ip, "count": len(names), "templates": names}
                  for ip, names in sorted(targets.items(), key=lambda kv: -len(kv[1]))
                  if len(names) > 1]
    return ok(
        templates=out_templates,
        tasks=out_tasks,
        diagnosis={
            "template_count": len(templates),
            "task_count": len(tasks),
            "distinct_targets": len(targets),
            "wasted_tasks": len(tasks) - len(targets),
            "duplicates": duplicates,
        },
        rules=[{
            "uuid": r.get("uuid"),
            "name": r.get("name") or "",
            "domain": r.get("domain"),
            "geo_isp": r.get("geo_isp"),
            "geo_isp_label": label_for_geo_isp(r.get("geo_isp") or "default"),
            "geo_isp_region": region_of_geo_isp(r.get("geo_isp") or "default"),
            "probe_template_uuid": _probe_template_uuid(r),
        } for r in rules],
    )


@api.get("/probe/history")
def probe_history():
    samples = history.samples_since(24 * 3600)
    return ok(samples=samples,
              stats={ip: history.uptime_stats(arr) for ip, arr in samples.items()})


def _template_conf_from_body(data: Dict[str, Any], base_conf: Dict[str, Any]) -> Dict[str, Any]:
    scheme = str(data.get("scheme") or "http").strip().lower()
    path = str(data.get("path") or "/aegis_node_ping/").strip()
    method = str(data.get("method") or "HEAD").strip().upper()
    host_mode = str(data.get("host_mode") or "custom").strip().lower()
    host_value = str(data.get("host_value") or "").strip().lower()
    if scheme not in ("http", "https"):
        raise ApiError("协议只能是 http 或 https")
    if not path.startswith("/"):
        raise ApiError("路径必须以 / 开头")
    if method not in ("GET", "HEAD"):
        raise ApiError("方法只能是 GET 或 HEAD")
    if host_mode not in ("follow_target", "custom"):
        raise ApiError("Host 模式只能是 follow_target 或 custom")
    if host_mode == "custom" and not HOSTNAME_RE.fullmatch(host_value):
        raise ApiError("自定义 Host 时必须填写合法的测试域名")
    try:
        port = int(data.get("port") or 80)
    except (TypeError, ValueError):
        raise ApiError("端口必须是数字") from None
    if not 1 <= port <= 65535:
        raise ApiError("端口必须在 1–65535")

    conf = copy.deepcopy(base_conf)
    settings = conf.setdefault("probe_policy", {}).setdefault("settings", {})
    settings["type"] = "HTTP"
    advanced = settings.setdefault("advanced", {})
    advanced.update(scheme=scheme, port=port, path=path, method=method)
    advanced["host"] = ({"mode": "follow_target"} if host_mode == "follow_target"
                        else {"mode": "custom", "value": host_value})
    advanced.setdefault("headers", [])
    settings["conditions"] = [{"type": "dsl", "field_group_name": "HTTP",
                               "expression": DEFAULT_CONDITION}]
    return conf


@api.post("/probe/templates")
def create_probe_template():
    """以已有模板为蓝本（继承探测点组），创建一个面向自建服务器的统一 HTTP 探针模板。"""
    data = body()
    name = str(data.get("name") or "").strip()
    base_uuid = str(data.get("base_template_uuid") or "").strip()
    if not name or len(name) > 50:
        raise ApiError("模板名称必填，最多 50 个字符")
    if not base_uuid:
        raise ApiError("请选择一个蓝本模板（用来继承探测点）")
    client = axisnow()
    conf = _template_conf_from_body(data, client.get_probe_template(base_uuid).get("conf") or {})
    target = template_probe_target(conf)
    created = client.create_probe_template({
        "name": name,
        "description": (str(data.get("description") or "").strip()
                        or f"统一探针：{target['url_hint']}（{target['host_hint']}）")[:255],
        "conf": conf,
    })
    return ok(template={"uuid": created.get("uuid"), "name": created.get("name"),
                        **template_probe_target(created.get("conf") or {})})


@api.post("/probe/apply")
def apply_probe_template():
    """把模板应用到一批规则（替换 edge_probe_template_uuid）。逐条执行，部分失败会逐条报告。"""
    data = body()
    template_uuid = str(data.get("template_uuid") or "").strip()
    rule_uuids = data.get("rule_uuids") or []
    if not template_uuid:
        raise ApiError("请选择要应用的模板")
    if not isinstance(rule_uuids, list) or not rule_uuids:
        raise ApiError("请至少选择一条规则")
    client = axisnow()
    client.get_probe_template(template_uuid)

    results = []
    for ru in rule_uuids:
        try:
            remote = client.get_rule(str(ru))
            action = copy.deepcopy(remote.get("action") or {})
            action.setdefault("method", "ip_election")
            action.setdefault("__meta__", {"responseStrategyTtlUnit": "seconds"})
            action.setdefault("conf", {})["edge_probe_template_uuid"] = [template_uuid]
            client.update_rule(str(ru), {**remote, "action": action})
            scheduler.forget(str(ru))
            results.append({"uuid": ru, "ok": True})
        except AxisNowError as exc:
            results.append({"uuid": ru, "ok": False, "error": str(exc)})
    failed = sum(1 for r in results if not r["ok"])
    return ok(results=results, applied=len(results) - failed, failed=failed)


@api.delete("/probe/tasks/<task_uuid>")
def delete_probe_task(task_uuid: str):
    axisnow().delete_probe_task(task_uuid)
    return ok()


@api.post("/probe/tasks/cleanup")
def cleanup_probe_tasks():
    """同一个目标 IP 只保留一个任务（优先保留指定模板的），其余删除。"""
    require_confirm()
    keep_template = str(body().get("keep_template_uuid") or "").strip()
    client = axisnow()
    by_ip: Dict[str, List[Dict[str, Any]]] = {}
    for tk in client.probe_tasks():
        for ip in (tk.get("conf") or {}).get("target") or []:
            by_ip.setdefault(ip, []).append(tk)

    deleted, failures = [], []
    for ip, group in by_ip.items():
        group.sort(key=lambda t: (t.get("conf") or {}).get("template_uuid") != keep_template)
        for t in group[1:]:
            try:
                client.delete_probe_task(t["uuid"])
                deleted.append({"uuid": t["uuid"], "name": t.get("name"), "ip": ip})
            except AxisNowError as exc:
                failures.append({"uuid": t["uuid"], "name": t.get("name"), "error": str(exc)})
    return ok(deleted=deleted, kept=len(by_ip), failures=failures)
