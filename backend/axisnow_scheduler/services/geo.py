"""IP → 国家 / ASN 查询，供前端显示国旗和运营商。

数据源：DB-IP Lite（CC BY 4.0，免费、无需注册），每月更新。
  - dbip-country-lite-YYYY-MM.mmdb.gz
  - dbip-asn-lite-YYYY-MM.mmdb.gz
文件放在 data/geoip/，启动时若缺失或超过 35 天，后台自动下载；下载失败不影响任何功能，
只是不显示国旗。也可以手动把 .mmdb 放进该目录（GEOIP_AUTO_DOWNLOAD=0 关闭自动下载）。

界面需要注明来源：IP Geolocation by DB-IP (https://db-ip.com)。
"""

from __future__ import annotations

import contextlib
import gzip
import ipaddress
import logging
import os
import shutil
import threading
import time
from datetime import date
from functools import lru_cache
from typing import Any, Dict, Optional

import requests

from ..storage.config_store import data_dir

log = logging.getLogger(__name__)

DOWNLOAD_URL = "https://download.db-ip.com/free/dbip-{kind}-lite-{ym}.mmdb.gz"
KINDS = ("country", "asn")
MAX_AGE_SECONDS = 35 * 24 * 3600

_readers: Dict[str, Any] = {}
_lock = threading.Lock()


def _dir() -> str:
    return os.path.join(data_dir(), "geoip")


def _path(kind: str) -> str:
    return os.path.join(_dir(), f"dbip-{kind}-lite.mmdb")


def _open(kind: str) -> Optional[Any]:
    try:
        import maxminddb
    except ImportError:  # pragma: no cover - 依赖缺失时静默降级
        return None
    path = _path(kind)
    if not os.path.exists(path):
        return None
    try:
        return maxminddb.open_database(path)
    except Exception as exc:  # noqa: BLE001 - 文件损坏时降级
        log.warning("GeoIP 数据库 %s 无法打开：%s", kind, type(exc).__name__)
        return None


def reload() -> None:
    with _lock:
        for r in _readers.values():
            with contextlib.suppress(Exception):
                r.close()
        _readers.clear()
        for kind in KINDS:
            reader = _open(kind)
            if reader is not None:
                _readers[kind] = reader
    lookup.cache_clear()


def status() -> Dict[str, Any]:
    out: Dict[str, Any] = {"attribution": "IP Geolocation by DB-IP", "url": "https://db-ip.com"}
    for kind in KINDS:
        path = _path(kind)
        out[kind] = {
            "loaded": kind in _readers,
            "updated": int(os.path.getmtime(path)) if os.path.exists(path) else None,
        }
    return out


@lru_cache(maxsize=4096)
def lookup(ip: str) -> Dict[str, Any]:
    """返回 {"country": "us"|None, "asn": int|None, "org": str|None, "private": bool}。"""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return {"country": None, "asn": None, "org": None, "private": False}
    if not addr.is_global:
        return {"country": None, "asn": None, "org": None, "private": True}

    country = asn = org = None
    reader = _readers.get("country")
    if reader is not None:
        try:
            rec = reader.get(ip) or {}
            country = ((rec.get("country") or {}).get("iso_code") or "").lower() or None
        except Exception:  # noqa: BLE001
            pass
    reader = _readers.get("asn")
    if reader is not None:
        try:
            rec = reader.get(ip) or {}
            asn = rec.get("autonomous_system_number")
            org = rec.get("autonomous_system_organization")
        except Exception:  # noqa: BLE001
            pass
    return {"country": country, "asn": asn, "org": org, "private": False}


def _months_to_try() -> list:
    today = date.today()
    prev = date(today.year - (today.month == 1), (today.month - 2) % 12 + 1, 1)
    return [today.strftime("%Y-%m"), prev.strftime("%Y-%m")]


def _download(kind: str) -> bool:
    os.makedirs(_dir(), exist_ok=True)
    for ym in _months_to_try():
        url = DOWNLOAD_URL.format(kind=kind, ym=ym)
        tmp = _path(kind) + ".download"
        try:
            with requests.get(url, stream=True, timeout=60) as resp:
                if resp.status_code != 200:
                    continue
                with open(tmp + ".gz", "wb") as fh:
                    shutil.copyfileobj(resp.raw, fh)
            with gzip.open(tmp + ".gz", "rb") as src, open(tmp, "wb") as dst:
                shutil.copyfileobj(src, dst)
            os.replace(tmp, _path(kind))
            log.info("GeoIP %s 数据库已更新（%s）", kind, ym)
            return True
        except (requests.RequestException, OSError, EOFError) as exc:
            log.info("下载 GeoIP %s（%s）失败：%s", kind, ym, type(exc).__name__)
        finally:
            for leftover in (tmp, tmp + ".gz"):
                if os.path.exists(leftover):
                    os.remove(leftover)
    return False


def _stale(kind: str) -> bool:
    path = _path(kind)
    return not os.path.exists(path) or time.time() - os.path.getmtime(path) > MAX_AGE_SECONDS


def update_if_needed() -> None:
    changed = False
    for kind in KINDS:
        if _stale(kind):
            changed = _download(kind) or changed
    if changed or not _readers:
        reload()


def run_forever(stop: threading.Event, auto_download: bool) -> None:
    reload()
    while not stop.is_set():
        if auto_download:
            try:
                update_if_needed()
            except Exception as exc:  # noqa: BLE001 - 后台线程不能退出
                log.warning("GeoIP 更新异常：%s", type(exc).__name__)
        stop.wait(24 * 3600)
