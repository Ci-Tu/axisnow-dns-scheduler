"""进程内读缓存，支持 stale-while-revalidate。

- age <= fresh_ttl：直接命中；
- fresh_ttl < age <= stale_ttl 且调用方允许旧值：立即返回旧值，并在后台刷新一次（同 key 去重）；
- 其余情况：调用方自己去取，取回后 put()。

写操作之后调用 clear()，保证写后读到最新数据。
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional, Set, Tuple

log = logging.getLogger(__name__)


class ResponseCache:
    def __init__(self, fresh_ttl: float, stale_ttl: float):
        self.fresh_ttl = fresh_ttl
        self.stale_ttl = stale_ttl
        self._data: Dict[str, Tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._refreshing: Set[str] = set()

    def lookup(self, key: str, *, allow_stale: bool,
               refresh: Callable[[], Any]) -> Optional[Any]:
        """命中返回值；未命中返回 None。允许旧值时会顺带触发后台刷新。"""
        with self._lock:
            hit = self._data.get(key)
        if not hit:
            return None
        age = time.monotonic() - hit[0]
        if age <= self.fresh_ttl:
            return hit[1]
        if allow_stale and age <= self.stale_ttl:
            self._refresh_async(key, refresh)
            return hit[1]
        return None

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def _refresh_async(self, key: str, refresh: Callable[[], Any]) -> None:
        with self._lock:
            if key in self._refreshing:
                return
            self._refreshing.add(key)

        def run() -> None:
            try:
                self.put(key, refresh())
            except Exception as exc:  # noqa: BLE001 - 后台刷新失败只记录，旧值继续可用
                log.info("后台刷新失败（%s）：%s", key.split("|", 1)[-1][:60], type(exc).__name__)
            finally:
                with self._lock:
                    self._refreshing.discard(key)

        threading.Thread(target=run, name="cache-refresh", daemon=True).start()
