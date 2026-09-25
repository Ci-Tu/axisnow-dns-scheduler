"""JSON API（/api/*）。导入各子模块以注册路由。"""

from . import auth, cloudflare, dashboard, domains, probe, rules, settings  # noqa: F401
from .common import api

__all__ = ["api"]
