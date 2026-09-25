"""功能模块（Feature）基类与数据结构。

一个 Feature 就是一条「自定义能力」：它观察某条 AxisNow DNS 规则当前的线上状态，
决定自己想把它改成什么样子。调度引擎负责把多个 Feature 的期望合并后统一下发。

要新增一个功能（比如「按拨测质量自动排序」「闲时降 TTL」「故障自动切池」）：

    1. 在 app/features/ 下新建 xxx.py
    2. 定义 class XxxFeature(Feature)，填 id / name / description / order
    3. 实现 applicable() 与 desired()
    4. 在 app/features/__init__.py 里 register(XxxFeature())

不需要改调度引擎、不需要改 WebUI 的通用部分；规则页会自动多出一个该功能的配置分区。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class RuleContext:
    """调度引擎传给 Feature 的只读上下文。

    两个顺序字段的区别很重要：

    - ``ip_pool``：**远端当前**的顺序，是事实，整个求解过程不变。
      需要「以线上现状为基准」的功能（如潮汐调度）应该用它。
    - ``working_order``：**本次求解到目前为止的候选顺序**。引擎在询问每个功能之前
      会把它更新为已合并的结果，因此 order 较大的功能应当基于它计算，
      才能叠加在前一个功能的决策之上，而不是把它覆盖掉。
    """

    uuid: str
    remote: Dict[str, Any]          # AxisNow 返回的规则原始对象
    ip_pool: List[str]              # 远端当前 IP 池顺序（不变）
    ip_notes: Dict[str, str]        # IP -> 备注（用户配置，跨功能共享）
    probe: Dict[str, Dict[str, Any]]  # IP -> {status, avg_connect_latency}
    now: datetime                   # 带调度时区
    values: Dict[str, List[str]] = field(default_factory=dict)  # 其它地址组（eip/eip_tag/domain）
    working_order: Optional[List[str]] = None  # 引擎维护的候选顺序

    def order_in_progress(self) -> List[str]:
        """当前候选顺序；还没有功能表态时退化为远端顺序。"""
        return list(self.working_order or self.ip_pool)


@dataclass
class Desired:
    """一个 Feature 对规则的期望状态的**增量描述**。

    None 表示「这一项我不表态」，交给别的 Feature 决定或保持线上原值。
    以后要扩展 TTL、选举策略、启用状态等，直接在这里加字段即可。
    """

    ip_order: Optional[List[str]] = None
    status: Optional[str] = None

    def is_empty(self) -> bool:
        return self.ip_order is None and self.status is None


def merge_desired(base: Desired, extra: Desired) -> Desired:
    """按顺序合并：order 越大的 Feature 越晚合并，可以覆盖前面的决定。"""
    return Desired(
        ip_order=extra.ip_order if extra.ip_order is not None else base.ip_order,
        status=extra.status if extra.status is not None else base.status,
    )


class Feature:
    """所有功能模块的基类。"""

    id: str = ""
    name: str = ""
    description: str = ""
    # 数值越小越先被求值；数值越大越晚，因而可以覆盖前面功能的结果
    order: int = 100
    # 前端渲染提示：'slots' 表示用时间段编辑器，'none' 表示无需额外界面
    ui: str = "none"

    # ---------- 需要子类实现 ----------

    def applicable(self, ctx: RuleContext) -> Tuple[bool, str]:
        """该功能对这条规则是否可用。第二个返回值是不可用原因（可用时给空串）。"""
        return False, "该功能未实现"

    def desired(self, cfg: Dict[str, Any], ctx: RuleContext) -> Optional[Desired]:
        """返回期望的增量改动；返回 None 表示此刻不改动。"""
        return None

    # ---------- 可选覆写 ----------

    def default_config(self) -> Dict[str, Any]:
        return {}

    def summary(self, cfg: Dict[str, Any], ctx: RuleContext) -> Dict[str, Any]:
        """给规则页 / 列表页用的展示摘要。"""
        return {}

    def validate(self, cfg: Dict[str, Any]) -> Optional[str]:
        """校验配置合法性，返回错误信息；None 表示通过。"""
        return None
