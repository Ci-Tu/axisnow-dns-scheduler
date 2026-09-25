"""后台线程：调度、拨测采样（兼缓存预热）、GeoIP 更新。

用 data/background.lock 文件锁保证即使 gunicorn 起了多个 worker，也只有一个进程在跑。
Windows 没有 fcntl，退化为进程内单例（仅用于本地开发）。
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
from typing import List, Optional

from .. import scheduler
from ..clients.axisnow import AxisNowClient, AxisNowError, ip_pool_of
from ..settings import settings
from ..storage import config_store as store
from ..storage import history
from . import geo

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

SAMPLE_INTERVAL_SECONDS = 60

_stop = threading.Event()
_threads: List[threading.Thread] = []
_lock_fh = None


def sample_once(client: Optional[AxisNowClient] = None) -> int:
    """采一次全部拨测目标的状态写入历史；顺带预热仪表板要用的读缓存。返回采样条数。"""
    cfg = store.load_config()
    client = client or scheduler.client_for(cfg)
    if client is None:
        return 0
    rules = client.list_rules()
    for warm in (client.list_domains, client.probe_templates, client.probe_tasks):
        with contextlib.suppress(AxisNowError):
            warm()
    probe = client.probe_status([r.get("uuid") for r in rules])
    seen = set()
    rows = []
    for r in rules:
        status_by_ip = probe.get(r.get("uuid")) or {}
        for ip in ip_pool_of(r):
            item = status_by_ip.get(ip) or {}
            if ip in seen or not item.get("status"):
                continue
            seen.add(ip)
            rows.append((ip, item["status"], item.get("latency")))
    history.add_samples(rows)
    return len(rows)


def _sampler(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            sample_once()
        except Exception as exc:  # noqa: BLE001 - 采样失败不影响主流程
            log.warning("拨测采样失败：%s", type(exc).__name__)
        stop.wait(SAMPLE_INTERVAL_SECONDS)


def _acquire_lock() -> bool:
    global _lock_fh
    if fcntl is None:
        return True
    store.ensure_data_dir()
    fh = open(os.path.join(store.data_dir(), "background.lock"), "a+")  # noqa: SIM115
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return False
    _lock_fh = fh
    return True


def start() -> bool:
    if settings().disable_background:
        log.info("DISABLE_SCHEDULER=1，不启动后台线程")
        return False
    if _threads and all(t.is_alive() for t in _threads):
        return True
    if not _acquire_lock():
        log.info("其他进程已持有后台锁，本进程只提供 Web 服务")
        return False
    _stop.clear()
    _threads.clear()
    for name, target, args in (
        ("scheduler", scheduler.run_forever, (_stop,)),
        ("probe-sampler", _sampler, (_stop,)),
        ("geoip", geo.run_forever, (_stop, settings().geoip_auto_download)),
    ):
        t = threading.Thread(target=target, args=args, name=name, daemon=True)
        t.start()
        _threads.append(t)
    return True


def stop() -> None:
    _stop.set()
