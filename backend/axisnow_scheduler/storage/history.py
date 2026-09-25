"""运行历史（SQLite：data/history.db）。

- probe_samples：每分钟一次的拨测采样，供 24h 可用率条与延迟走势；保留 7 天。
- apply_events：调度下发记录，供仪表板时间线与设置页；保留最近 500 条。

1.x 的 data/probe_history.json 会在首次启动时自动导入，原文件改名为 *.migrated 保留。
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

from .config_store import data_dir, ensure_data_dir

log = logging.getLogger(__name__)

SAMPLE_RETENTION_SECONDS = 7 * 24 * 3600
EVENT_RETENTION_ROWS = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS probe_samples (
    ip     TEXT    NOT NULL,
    t      INTEGER NOT NULL,
    status TEXT    NOT NULL,
    ms     REAL
);
CREATE INDEX IF NOT EXISTS idx_samples_ip_t ON probe_samples (ip, t);
CREATE TABLE IF NOT EXISTS apply_events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    at      TEXT    NOT NULL,
    rule    TEXT    NOT NULL,
    slot    TEXT,
    ok      INTEGER NOT NULL,
    message TEXT    NOT NULL
);
"""

_init_lock = threading.Lock()
_initialized_for: Optional[str] = None


def _db_path() -> str:
    return os.path.join(data_dir(), "history.db")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    _ensure_schema()
    conn = sqlite3.connect(_db_path(), timeout=10)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_schema() -> None:
    global _initialized_for
    path = _db_path()
    if _initialized_for == path:
        return
    with _init_lock:
        if _initialized_for == path:
            return
        ensure_data_dir()
        conn = sqlite3.connect(path, timeout=10)
        try:
            conn.executescript(_SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.commit()
            _import_legacy_json(conn)
        finally:
            conn.close()
        _initialized_for = path


def _import_legacy_json(conn: sqlite3.Connection) -> None:
    legacy = os.path.join(data_dir(), "probe_history.json")
    if not os.path.exists(legacy):
        return
    try:
        with open(legacy, encoding="utf-8") as fh:
            samples = (json.load(fh) or {}).get("samples") or {}
        rows = [
            (ip, int(x["t"]), str(x.get("s") or "unknown"), x.get("ms") or None)
            for ip, arr in samples.items() for x in arr or [] if "t" in x
        ]
        conn.executemany("INSERT INTO probe_samples (ip, t, status, ms) VALUES (?, ?, ?, ?)", rows)
        conn.commit()
        os.replace(legacy, legacy + ".migrated")
        log.info("已从 probe_history.json 导入 %d 条拨测采样", len(rows))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        log.warning("导入旧版拨测历史失败，已跳过：%s", type(exc).__name__)


# ---------- 拨测采样 ----------

def add_samples(samples: Iterable[Tuple[str, str, Optional[float]]], now: Optional[int] = None) -> None:
    """samples: [(ip, status, latency_ms|None)]"""
    ts = int(now or time.time())
    rows = [(ip, ts, status, ms) for ip, status, ms in samples]
    if not rows:
        return
    with _connect() as conn:
        conn.executemany("INSERT INTO probe_samples (ip, t, status, ms) VALUES (?, ?, ?, ?)", rows)
        conn.execute("DELETE FROM probe_samples WHERE t < ?", (ts - SAMPLE_RETENTION_SECONDS,))


def samples_since(seconds: int = 24 * 3600) -> Dict[str, List[Dict[str, Any]]]:
    """返回 {ip: [{"t", "s", "ms"}...]}，按时间升序。"""
    since = int(time.time()) - seconds
    out: Dict[str, List[Dict[str, Any]]] = {}
    with _connect() as conn:
        for ip, t, status, ms in conn.execute(
                "SELECT ip, t, status, ms FROM probe_samples WHERE t >= ? ORDER BY t", (since,)):
            out.setdefault(ip, []).append({"t": t, "s": status, "ms": ms})
    return out


def uptime_stats(samples: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(samples)
    good = sum(1 for x in samples if x.get("s") == "available")
    lat = [x["ms"] for x in samples if isinstance(x.get("ms"), (int, float))]
    return {
        "samples": total,
        "uptime": round(good * 100.0 / total, 2) if total else None,
        "avg_ms": round(sum(lat) / len(lat)) if lat else None,
    }


# ---------- 下发记录 ----------

def add_event(*, at: str, rule: str, slot: Optional[str], ok: bool, message: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO apply_events (at, rule, slot, ok, message) VALUES (?, ?, ?, ?, ?)",
            (at, rule, slot, 1 if ok else 0, message[:500]),
        )
        conn.execute(
            "DELETE FROM apply_events WHERE id NOT IN "
            "(SELECT id FROM apply_events ORDER BY id DESC LIMIT ?)", (EVENT_RETENTION_ROWS,))


def recent_events(limit: int = 30) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT at, rule, slot, ok, message FROM apply_events ORDER BY id DESC LIMIT ?",
            (max(1, min(limit, EVENT_RETENTION_ROWS)),)).fetchall()
    return [{"at": at, "rule": rule, "slot": slot, "ok": bool(ok), "message": message}
            for at, rule, slot, ok, message in rows]
