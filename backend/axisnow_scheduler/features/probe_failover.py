"""功能模块：拨测故障切换（把拨测不可用的 IP 自动降到最后）。

这是官方控制台没有的能力：`priority_order` 策略下，AxisNow 只按你写死的数组顺序返回 IP，
不会因为探针发现某个 IP 挂了就换一个。本模块补上这一环 ——
每个调度周期读一次拨测状态，把不可用的地址整体挪到优先级末尾；
地址恢复可用后，它会自动回到原来相对靠前的位置。

与「潮汐调度」的协作方式：
  潮汐调度（order 10）先按时间段定出顺序，
  本模块（order 20）在这个顺序**之上**再做可用性过滤（稳定分区，不打乱组内相对顺序）。
  所以两者可以同时开启：先按时间选线路，再把挂掉的剔除。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from ..constants import STRATEGY_LABELS
from .base import Desired, Feature, RuleContext

UNAVAILABLE = {"unavailable", "down", "failed", "error", "unhealthy"}


def split_by_health(
    order: List[str], probe: Dict[str, Dict[str, Any]]
) -> Tuple[List[str], List[str], List[str]]:
    """按拨测状态做稳定分区。

    返回 (可用, 不可用, 无数据的)。无拨测数据的 IP 视为可用（不能因为没探针就把它降级）。
    """
    healthy: List[str] = []
    unhealthy: List[str] = []
    unknown: List[str] = []
    for ip in order:
        status = ((probe.get(ip) or {}).get("status") or "").lower()
        if not status:
            unknown.append(ip)
        elif status in UNAVAILABLE:
            unhealthy.append(ip)
        else:
            healthy.append(ip)
    return healthy, unhealthy, unknown


class ProbeFailoverFeature(Feature):
    id = "probe_failover"
    name = "拨测故障切换"
    description = "每个周期读取拨测状态，把不可用的 IP 自动降到优先级末尾；恢复后自动回到原位"
    order = 20   # 排在潮汐调度之后，对它的结果做可用性过滤
    ui = "simple"

    def default_config(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "demote_unavailable": True,
            "min_healthy": 1,
        }

    def applicable(self, ctx: RuleContext) -> Tuple[bool, str]:
        if not ctx.ip_pool:
            return False, "该规则地址池里没有 IP 类型的地址组"
        if len(ctx.ip_pool) < 2:
            return False, "地址池只有一个 IP，没有可切换的余地"
        if not ctx.probe:
            return False, "该规则没有拨测数据（未关联拨测模板，或拨测任务未启用）"
        conf = ((ctx.remote.get("action") or {}).get("conf")) or {}
        strat = (conf.get("response_strategy") or {}).get("election_strategy")
        if strat != "priority_order":
            label = STRATEGY_LABELS.get(strat or "", strat or "未知")
            return False, f"选取策略是「{label}」，改顺序不会生效"
        return True, ""

    def desired(self, cfg: Dict[str, Any], ctx: RuleContext) -> Optional[Desired]:
        if not cfg.get("demote_unavailable", True):
            return None

        order = ctx.order_in_progress()
        healthy, unhealthy, unknown = split_by_health(order, ctx.probe)

        if not unhealthy:
            return None  # 没有故障地址，不表态
        # 全部不可用时也不动，避免把「全线故障」误判成要重排
        if len(healthy) + len(unknown) < int(cfg.get("min_healthy", 1)):
            return None

        target = healthy + unknown + unhealthy
        if target == order:
            return None
        return Desired(ip_order=target)

    def summary(self, cfg: Dict[str, Any], ctx: RuleContext) -> Dict[str, Any]:
        healthy, unhealthy, unknown = split_by_health(ctx.order_in_progress(), ctx.probe)
        return {
            "healthy": len(healthy),
            "unhealthy": len(unhealthy),
            "unknown": len(unknown),
            "demoted": [ip for ip in unhealthy],
            "active": bool(cfg.get("demote_unavailable", True)) and bool(unhealthy),
        }
