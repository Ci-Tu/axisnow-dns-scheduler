"""运行时设置：全部来自环境变量，进程内只读。

所有可调项都集中在这里，其它模块不直接读 os.environ。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta, timezone, tzinfo
from functools import lru_cache
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_API_BASE = "https://api.axisnow.io/client/v1"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _default_web_dist() -> str:
    # 容器内：/app/web；源码运行：<repo>/frontend/dist
    here = Path(__file__).resolve()
    candidates = [Path("/app/web"), here.parents[2] / "frontend" / "dist"]
    for c in candidates:
        if (c / "index.html").exists():
            return str(c)
    return str(candidates[-1])


@dataclass(frozen=True)
class Settings:
    data_dir: str
    port: int
    timezone_name: str
    session_days: int
    # 以下三个若通过环境变量提供，则优先于 data/config.json，且界面上不可修改
    api_base: Optional[str]
    api_token: Optional[str]
    cloudflare_token: Optional[str]
    disable_background: bool
    geoip_auto_download: bool
    web_dist: str

    @property
    def tz(self) -> tzinfo:
        return get_tz(self.timezone_name)


@lru_cache(maxsize=8)
def get_tz(name: str) -> tzinfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        # 缺 tzdata 或名字写错时退化为 UTC+8，并保持可运行
        return timezone(timedelta(hours=8), "UTC+8")


def load_settings() -> Settings:
    return Settings(
        data_dir=os.environ.get("DATA_DIR", "/app/data"),
        port=_env_int("PORT", 4894),
        timezone_name=os.environ.get("APP_TIMEZONE") or os.environ.get("TZ") or "Asia/Shanghai",
        session_days=max(1, _env_int("SESSION_DAYS", 180)),
        api_base=os.environ.get("AXISNOW_API_BASE") or None,
        api_token=os.environ.get("AXISNOW_API_TOKEN") or None,
        cloudflare_token=os.environ.get("CLOUDFLARE_API_TOKEN") or None,
        disable_background=_env_bool("DISABLE_SCHEDULER", False),
        geoip_auto_download=_env_bool("GEOIP_AUTO_DOWNLOAD", True),
        web_dist=os.environ.get("WEB_DIST") or _default_web_dist(),
    )


_settings: Optional[Settings] = None


def settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def override_settings(value: Settings) -> None:
    """测试用：替换全局设置。"""
    global _settings
    _settings = value
