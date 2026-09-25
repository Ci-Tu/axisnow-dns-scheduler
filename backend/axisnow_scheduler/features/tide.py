"""功能模块：潮汐调度（按时间段切换 IP 优先级顺序）。"""

from __future__ import annotations

import uuid as uuidlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ..constants import STRATEGY_LABELS
from .base import Desired, Feature, RuleContext


def parse_hhmm(value: str) -> Optional[Tuple[int, int]]:
    try:
        hh, mm = str(value).split(":")
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, AttributeError):
        return None
    return None


def slot_matches(slot: Dict[str, Any], now: datetime) -> bool:
    """判断某个时间段此刻是否生效。now 必须已带调度时区。"""
    if not slot.get("enabled", True):
        return False
    start = parse_hhmm(slot.get("start"))
    end = parse_hhmm(slot.get("end"))
    if start is None or end is None:
        return False

    days = slot.get("days")
    if not days:
        days = [0, 1, 2, 3, 4, 5, 6]
    try:
        days = {int(d) for d in days}
    except (TypeError, ValueError):
        days = {0, 1, 2, 3, 4, 5, 6}

    today = now.date()

    # start == end 视为全天
    if start == end:
        return today.weekday() in days

    # 普通时间段
    if start < end:
        if today.weekday() not in days:
            return False
        begin = now.replace(hour=start[0], minute=start[1], second=0, microsecond=0)
        finish = now.replace(hour=end[0], minute=end[1], second=0, microsecond=0)
        return begin <= now < finish

    # 跨午夜：起始日按 days 判定，次日 end 之前仍算命中
    start_t = datetime(2000, 1, 1, start[0], start[1]).time()
    end_t = datetime(2000, 1, 1, end[0], end[1]).time()
    if now.time() >= start_t:
        return today.weekday() in days
    yesterday = today - timedelta(days=1)
    return yesterday.weekday() in days and now.time() < end_t


def pick_slot(slots: List[Dict[str, Any]], now: datetime) -> Optional[Dict[str, Any]]:
    """时间重叠时取列表中第一个命中的。"""
    for slot in slots or []:
        if slot_matches(slot, now):
            return slot
    return None


def normalize_order(ips: List[str], pool: List[str]) -> List[str]:
    """池内合法项按给定顺序在前，池里遗漏的 IP 按池顺序补到末尾。"""
    pool_set = set(pool)
    ordered = [ip for ip in dict.fromkeys(ips) if ip in pool_set]
    seen = set(ordered)
    return ordered + [ip for ip in pool if ip not in seen]


def order_for(cfg: Dict[str, Any], slot: Optional[Dict[str, Any]], pool: List[str]) -> List[str]:
    """目标顺序：命中时间段用该段顺序，否则用基准顺序；池中新增 IP 追加到末尾。"""
    base = list((slot or {}).get("ips") or []) or list(cfg.get("default_ips") or [])
    return normalize_order(base, pool)


def validate_slot(body: Dict[str, Any]) -> Optional[str]:
    for label, key in (("开始时间", "start"), ("结束时间", "end")):
        value = str(body.get(key) or "")
        if parse_hhmm(value) is None:
            return f"{label}格式应为 HH:MM"
    days = body.get("days") or []
    try:
        days = [int(d) for d in days]
    except (TypeError, ValueError):
        return "星期取值非法"
    if not days or any(d < 0 or d > 6 for d in days):
        return "至少选择一个有效的星期"
    name = str(body.get("name") or "")
    if len(name) > 40:
        return "时间段名称最多 40 个字符"
    ips = body.get("ips")
    if ips is not None and not (isinstance(ips, list) and all(isinstance(i, str) for i in ips)):
        return "ips 必须是字符串数组"
    return None


def make_slot(body: Dict[str, Any], pool: List[str], existing_id: str = "") -> Dict[str, Any]:
    start = str(body.get("start") or "00:00")
    end = str(body.get("end") or "00:00")
    s_hhmm, e_hhmm = parse_hhmm(start), parse_hhmm(end)
    days = sorted({int(d) for d in (body.get("days") or [0, 1, 2, 3, 4, 5, 6])})
    ips = body.get("ips")
    ordered = normalize_order(ips, pool) if isinstance(ips, list) else list(pool)
    return {
        "id": existing_id or uuidlib.uuid4().hex[:12],
        "name": (str(body.get("name") or "").strip()[:40]) or f"{start} - {end}",
        "start": start,
        "end": end,
        "days": days,
        "ips": ordered,
        "enabled": bool(body.get("enabled", True)),
        # start > end 即跨午夜；start == end 视为全天，不算跨午夜
        "cross_midnight": bool(s_hhmm and e_hhmm and s_hhmm > e_hhmm),
    }


class TideFeature(Feature):
    id = "tide"
    name = "潮汐调度"
    description = "按时间段（使用系统设置的时区）自动调整该规则 IP 的优先级顺序"
    order = 10
    ui = "slots"

    def default_config(self) -> Dict[str, Any]:
        return {"enabled": True, "default_ips": [], "slots": []}

    def applicable(self, ctx: RuleContext) -> Tuple[bool, str]:
        if not ctx.ip_pool:
            return False, "该规则地址池里没有 IP 类型的地址组"
        conf = ((ctx.remote.get("action") or {}).get("conf")) or {}
        strat = (conf.get("response_strategy") or {}).get("election_strategy")
        if strat != "priority_order":
            label = STRATEGY_LABELS.get(strat or "", strat or "未知")
            return False, f"选取策略是「{label}」，只有「顺序」策略才受 IP 排列影响"
        return True, ""

    def desired(self, cfg: Dict[str, Any], ctx: RuleContext) -> Optional[Desired]:
        slot = pick_slot(cfg.get("slots") or [], ctx.now)
        return Desired(ip_order=order_for(cfg, slot, ctx.ip_pool))

    def summary(self, cfg: Dict[str, Any], ctx: RuleContext) -> Dict[str, Any]:
        slots = cfg.get("slots") or []
        slot = pick_slot(slots, ctx.now)
        return {
            "slot_count": len(slots),
            "active_slot_id": (slot or {}).get("id"),
            "active_slot_name": (slot or {}).get("name"),
        }
