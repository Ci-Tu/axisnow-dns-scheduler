"""调度引擎。

引擎本身不含业务逻辑，只做四件事：
  1. 拉取 AxisNow 上被接管的规则
  2. 为每条规则构造 RuleContext，依次询问所有已注册的 Feature「你想改成什么样」
  3. 把各 Feature 的期望按 order 合并成一份最终下发内容
  4. 与上次下发的内容比对，有变化才 PUT，避免无意义写入

新增功能不需要改这个文件，见 features/。
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .clients.axisnow import AxisNowClient, AxisNowError, ip_pool_of, set_ip_order
from .features import Desired, RuleContext, all_features, merge_desired
from .settings import settings
from .storage import config_store as store
from .storage import history

log = logging.getLogger(__name__)

_state_lock = threading.RLock()
# applied: rule_uuid -> {"fingerprint", "order", "slot_name", "at"}；只存在内存里，
# 重启后第一次下发前会先比对线上状态，不会产生多余写入。
_state: Dict[str, Any] = {"running": False, "last_tick": None, "last_error": "", "applied": {}}


def now() -> datetime:
    return datetime.now(settings().tz)


def fingerprint(desired: Desired) -> str:
    payload = json.dumps({"ip_order": desired.ip_order, "status": desired.status},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def make_context(rule_uuid: str, remote: Dict[str, Any], rule_cfg: Dict[str, Any],
                 probe: Dict[str, Dict[str, Any]], at: Optional[datetime] = None) -> RuleContext:
    return RuleContext(uuid=rule_uuid, remote=remote, ip_pool=ip_pool_of(remote),
                       ip_notes=rule_cfg.get("ip_notes") or {}, probe=probe or {},
                       now=at or now())


def resolve(rule_cfg: Dict[str, Any], ctx: RuleContext) -> Tuple[Desired, List[Dict[str, Any]]]:
    """按 order 依次询问各 Feature，返回合并后的期望与每个功能的说明。"""
    merged = Desired()
    notes: List[Dict[str, Any]] = []
    features_cfg: Dict[str, Any] = rule_cfg.get("features") or {}

    for feature in all_features():
        fcfg = features_cfg.get(feature.id) or {}
        entry: Dict[str, Any] = {"id": feature.id, "name": feature.name, "enabled": True}

        if not fcfg.get("enabled", True):
            notes.append({**entry, "enabled": False, "applied": False, "reason": "该功能已停用"})
            continue
        ok, reason = feature.applicable(ctx)
        if not ok:
            notes.append({**entry, "applied": False, "reason": reason})
            continue

        # 让后面的功能看到「到目前为止已合并的候选顺序」，才能叠加而不是互相覆盖
        ctx.working_order = list(merged.ip_order) if merged.ip_order is not None else None
        try:
            desired = feature.desired(fcfg, ctx)
        except Exception as exc:  # noqa: BLE001 - 单个功能出错不能拖垮整轮调度
            log.warning("功能 %s 求解异常：%s", feature.id, type(exc).__name__)
            notes.append({**entry, "applied": False, "reason": f"求解异常：{type(exc).__name__}"})
            continue

        entry["summary"] = feature.summary(fcfg, ctx)
        if desired is None or desired.is_empty():
            notes.append({**entry, "applied": False, "reason": "此刻无需改动"})
        else:
            merged = merge_desired(merged, desired)
            notes.append({**entry, "applied": True, "reason": ""})
    return merged, notes


def active_slot_name(notes: List[Dict[str, Any]]) -> Optional[str]:
    for n in notes:
        if n.get("applied"):
            name = (n.get("summary") or {}).get("active_slot_name")
            if name:
                return name
    return None


def apply_desired(remote: Dict[str, Any], desired: Desired) -> Dict[str, Any]:
    """把期望增量套用到规则对象副本上，得到最终 PUT 体。"""
    updated = remote
    if desired.ip_order is not None:
        updated = set_ip_order(updated, desired.ip_order)
    if desired.status is not None:
        updated = copy.deepcopy(updated)
        updated["status"] = desired.status
    return updated


def record(rule_uuid: str, desired: Desired, slot: Optional[str], *, ok: bool, message: str) -> None:
    at = now().isoformat(timespec="seconds")
    with _state_lock:
        if ok:
            _state["applied"][rule_uuid] = {
                "fingerprint": fingerprint(desired),
                "order": desired.ip_order or [],
                "slot_name": slot,
                "at": at,
            }
    try:
        history.add_event(at=at, rule=rule_uuid, slot=slot, ok=ok, message=message)
    except Exception as exc:  # noqa: BLE001 - 历史写失败不影响调度
        log.warning("写入下发记录失败：%s", type(exc).__name__)


def client_for(cfg: Dict[str, Any]) -> Optional[AxisNowClient]:
    token = store.api_token(cfg)
    return AxisNowClient(store.api_base(cfg), token) if token else None


def tick(client: Optional[AxisNowClient] = None, at: Optional[datetime] = None) -> Dict[str, Any]:
    """执行一轮调度。永远用新鲜数据（不接受缓存旧值），避免基于过期规则下发。"""
    cfg = store.load_config()
    at = at or now()
    summary: Dict[str, Any] = {"at": at.isoformat(timespec="seconds"), "checked": 0,
                               "applied": 0, "errors": []}

    if not (cfg.get("scheduler") or {}).get("enabled", True):
        summary["skipped"] = "调度已关闭"
        return summary
    active = {k: v for k, v in (cfg.get("rules") or {}).items() if v.get("enabled", True)}
    if not active:
        summary["skipped"] = "没有启用中的规则"
        return summary

    client = client or client_for(cfg)
    if client is None:
        summary["errors"].append("尚未配置 AxisNow API Token")
        return summary

    try:
        remote_rules = {r.get("uuid"): r for r in client.list_rules()}
    except AxisNowError as exc:
        summary["errors"].append(str(exc))
        return _finish(summary)
    probe_map = client.probe_status(list(active))

    for rule_uuid, rule_cfg in active.items():
        summary["checked"] += 1
        remote = remote_rules.get(rule_uuid)
        if remote is None:
            summary["errors"].append(f"规则已不存在（…{rule_uuid[-6:]}）")
            continue
        ctx = make_context(rule_uuid, remote, rule_cfg, probe_map.get(rule_uuid) or {}, at)
        desired, notes = resolve(rule_cfg, ctx)
        if desired.is_empty():
            continue

        last = _state["applied"].get(rule_uuid)
        if last and last.get("fingerprint") == fingerprint(desired):
            continue  # 与上次下发一致
        slot = active_slot_name(notes)
        if last is None and desired.ip_order == ctx.ip_pool and desired.status is None:
            # 线上本来就是目标状态：只记住指纹，不写 AxisNow
            with _state_lock:
                _state["applied"][rule_uuid] = {"fingerprint": fingerprint(desired),
                                                "order": desired.ip_order, "slot_name": slot,
                                                "at": summary["at"]}
            continue
        try:
            client.update_rule(rule_uuid, apply_desired(remote, desired))
            record(rule_uuid, desired, slot, ok=True, message="已下发")
            summary["applied"] += 1
        except AxisNowError as exc:
            record(rule_uuid, desired, slot, ok=False, message=str(exc))
            summary["errors"].append(f"下发失败（…{rule_uuid[-6:]}）：{exc}")
    return _finish(summary)


def _finish(summary: Dict[str, Any]) -> Dict[str, Any]:
    with _state_lock:
        _state["last_tick"] = summary["at"]
        _state["last_error"] = "; ".join(summary["errors"])
    return summary


def state_snapshot() -> Dict[str, Any]:
    with _state_lock:
        return {
            "running": _state["running"],
            "last_tick": _state["last_tick"],
            "last_error": _state["last_error"],
            "applied": {k: dict(v) for k, v in _state["applied"].items()},
        }


def last_applied(rule_uuid: str) -> Optional[Dict[str, Any]]:
    with _state_lock:
        item = _state["applied"].get(rule_uuid)
        return dict(item) if item else None


def forget(rule_uuid: str) -> None:
    with _state_lock:
        _state["applied"].pop(rule_uuid, None)


def run_forever(stop: threading.Event) -> None:
    with _state_lock:
        _state["running"] = True
    log.info("调度线程已启动（%s，时区 %s）", now().isoformat(timespec="seconds"),
             settings().timezone_name)
    while not stop.is_set():
        interval = 30
        try:
            cfg = store.load_config()
            interval = max(10, min(int((cfg.get("scheduler") or {}).get("interval_seconds") or 30),
                                   3600))
            tick()
        except Exception as exc:  # noqa: BLE001 - 调度线程绝不能退出
            log.warning("调度轮次异常：%s", type(exc).__name__)
            with _state_lock:
                _state["last_error"] = f"调度轮次异常：{type(exc).__name__}"
        stop.wait(interval)
    with _state_lock:
        _state["running"] = False
