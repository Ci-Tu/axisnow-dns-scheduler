"""功能模块注册表。

新增功能只需两步：写好 Feature 子类，然后在这里 register()。
调度引擎、WebUI 的通用部分都会自动识别，不需要改动别处。
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .base import Desired, Feature, RuleContext, merge_desired
from .probe_failover import ProbeFailoverFeature
from .tide import TideFeature

_REGISTRY: Dict[str, Feature] = {}


def register(feature: Feature) -> Feature:
    if not feature.id:
        raise ValueError("Feature 必须有 id")
    _REGISTRY[feature.id] = feature
    return feature


def get(feature_id: str) -> Optional[Feature]:
    return _REGISTRY.get(feature_id)


def all_features() -> List[Feature]:
    """按 order 升序返回；order 大的后合并，可覆盖先前的决定。"""
    return sorted(_REGISTRY.values(), key=lambda f: (f.order, f.id))


def describe() -> List[Dict[str, object]]:
    """给前端用的功能清单。"""
    return [
        {
            "id": f.id,
            "name": f.name,
            "description": f.description,
            "order": f.order,
            "ui": f.ui,
            "default_config": f.default_config(),
        }
        for f in all_features()
    ]


# ---- 已注册的功能模块 ----
# order 小的先求值；order 大的后合并，可以覆盖/细化前面的决定。
register(TideFeature())          # 10 · 按时间段定顺序
register(ProbeFailoverFeature())  # 20 · 在顺序之上做可用性过滤

__all__ = [
    "Desired",
    "Feature",
    "RuleContext",
    "merge_desired",
    "register",
    "get",
    "all_features",
    "describe",
]
