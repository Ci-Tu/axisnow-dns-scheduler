"""配置与会话密钥的持久化（data/config.json、data/session.key）。

约束：
- 文件一旦存在，绝不重置、绝不重新生成；损坏时只在内存里退回默认值，不覆盖原文件。
- Token、密码哈希、会话密钥永远不写日志、不返回前端。
- 所有写入都经过 mutate()：读-改-写全程持锁，调度线程与 Web 线程不会互相覆盖。

与 1.x 版本的文件格式完全兼容。
"""

from __future__ import annotations

import contextlib
import copy
import json
import logging
import os
import secrets
import threading
from typing import Any, Callable, Dict, Optional

from werkzeug.security import check_password_hash, generate_password_hash

from ..settings import DEFAULT_API_BASE, settings

log = logging.getLogger(__name__)

# 1 = 规则层直接放 slots；2 = 功能模块化；3 = 新增全局 ip_labels
CONFIG_VERSION = 3

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": CONFIG_VERSION,
    "api_base": DEFAULT_API_BASE,
    "api_token": "",
    "password_hash": "",
    "scheduler": {"enabled": True, "interval_seconds": 30},
    # Cloudflare 集成：token 需要 Zone → DNS → Edit 权限
    "cloudflare": {"token": "", "zones": []},
    # 全局 IP 标签：{ip: {"name": "东京 Oracle"}}，所有页面共用
    "ip_labels": {},
    # rule_uuid -> {"enabled", "note", "ip_notes": {ip: str}, "features": {feature_id: {...}}}
    "rules": {},
}

_lock = threading.RLock()
_cache: Optional[Dict[str, Any]] = None


# ---------- 路径 ----------

def data_dir() -> str:
    return settings().data_dir


def _config_path() -> str:
    return os.path.join(data_dir(), "config.json")


def _session_key_path() -> str:
    return os.path.join(data_dir(), "session.key")


def ensure_data_dir() -> None:
    os.makedirs(data_dir(), exist_ok=True)
    with contextlib.suppress(OSError):
        os.chmod(data_dir(), 0o700)


# ---------- 迁移 ----------

def _migrate_rule_v1(entry: Dict[str, Any]) -> None:
    """v1 → v2：把规则层的 slots / default_ips 搬进 features.tide。幂等，旧字段不删。"""
    legacy_slots = entry.get("slots")
    legacy_default = entry.get("default_ips")
    if legacy_slots is None and legacy_default is None:
        return
    tide = entry.setdefault("features", {}).setdefault("tide", {})
    if legacy_slots is not None and "slots" not in tide:
        tide["slots"] = legacy_slots
    if legacy_default is not None and "default_ips" not in tide:
        tide["default_ips"] = legacy_default
    tide.setdefault("enabled", True)


def _import_servers_json(cfg: Dict[str, Any]) -> bool:
    """1.x 的 data/servers.json 是手写的节点名单，把其中的名称并入 ip_labels（只导入一次）。"""
    path = os.path.join(data_dir(), "servers.json")
    if cfg.get("_servers_json_imported") or not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            items = json.load(fh)
    except (OSError, ValueError):
        return False
    labels = cfg.setdefault("ip_labels", {})
    for item in items if isinstance(items, list) else []:
        ip, name = (item or {}).get("ip"), (item or {}).get("name")
        if ip and name and ip not in labels:
            labels[ip] = {"name": str(name)[:40]}
    cfg["_servers_json_imported"] = True
    return True


def migrate(cfg: Dict[str, Any]) -> bool:
    """就地迁移配置结构，返回是否有改动。"""
    from ..features import all_features  # 延迟导入，避免循环依赖

    before = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
    for key, value in DEFAULT_CONFIG.items():
        cfg.setdefault(key, copy.deepcopy(value))

    for entry in (cfg.get("rules") or {}).values():
        if not isinstance(entry, dict):
            continue
        # 顺序很重要：先搬旧结构，再补默认值；反过来默认的 slots: [] 会让旧配置被静默丢弃
        _migrate_rule_v1(entry)
        features = entry.setdefault("features", {})
        for f in all_features():
            fcfg = features.get(f.id)
            if not isinstance(fcfg, dict):
                features[f.id] = dict(f.default_config())
            else:
                for k, v in f.default_config().items():
                    fcfg.setdefault(k, v)

    _import_servers_json(cfg)
    cfg["version"] = CONFIG_VERSION
    return json.dumps(cfg, sort_keys=True, ensure_ascii=False) != before


# ---------- 读写 ----------

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> Dict[str, Any]:
    """返回进程内共享的配置对象。调用方只读；要修改请用 mutate()。"""
    global _cache
    with _lock:
        if _cache is not None:
            return _cache
        ensure_data_dir()
        raw: Dict[str, Any] = {}
        corrupt = False
        if os.path.exists(_config_path()):
            try:
                with open(_config_path(), encoding="utf-8") as fh:
                    raw = json.load(fh) or {}
            except (OSError, ValueError):
                log.error("config.json 无法解析，本次以默认配置运行且不会覆盖原文件")
                corrupt = True
        cfg = _deep_merge(DEFAULT_CONFIG, raw)
        _cache = cfg
        changed = migrate(cfg)
        if not corrupt and (changed or not os.path.exists(_config_path())):
            save_config(cfg)
        return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    global _cache
    with _lock:
        ensure_data_dir()
        tmp = _config_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, _config_path())
        with contextlib.suppress(OSError):
            os.chmod(_config_path(), 0o600)
        _cache = cfg


def mutate(mutator: Callable[[Dict[str, Any]], Any]) -> Any:
    """读-改-写，全程持锁，返回 mutator 的返回值。

    在副本上修改：mutator 中途抛异常（例如校验失败）时，内存与磁盘上的配置都保持原样。
    """
    with _lock:
        cfg = copy.deepcopy(load_config())
        result = mutator(cfg)
        save_config(cfg)
        return result


def reset_cache() -> None:
    """测试用：丢弃进程内缓存。"""
    global _cache
    with _lock:
        _cache = None


def get_session_key() -> bytes:
    """会话密钥：存在则原样复用，缺失才生成 —— 这样登录态可以跨容器重建。"""
    ensure_data_dir()
    path = _session_key_path()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            value = fh.read().strip()
        if value:
            return value.encode("utf-8")
    value = secrets.token_hex(32)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(value)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)
    return value.encode("utf-8")


# ---------- 密码 ----------

def has_password(cfg: Dict[str, Any]) -> bool:
    return bool(cfg.get("password_hash"))


def set_password(cfg: Dict[str, Any], password: str) -> None:
    cfg["password_hash"] = generate_password_hash(password)


def verify_password(cfg: Dict[str, Any], password: str) -> bool:
    stored = cfg.get("password_hash") or ""
    if not stored:
        return False
    try:
        return check_password_hash(stored, password)
    except ValueError:
        return False


# ---------- 凭据（环境变量优先） ----------

def api_base(cfg: Dict[str, Any]) -> str:
    return settings().api_base or cfg.get("api_base") or DEFAULT_API_BASE


def api_token(cfg: Dict[str, Any]) -> str:
    return settings().api_token or cfg.get("api_token") or ""


def cloudflare_token(cfg: Dict[str, Any]) -> str:
    return settings().cloudflare_token or (cfg.get("cloudflare") or {}).get("token") or ""


def _meta(token: str, from_env: bool) -> Dict[str, Any]:
    # 只返回元信息，绝不返回 Token 本身
    return {
        "configured": bool(token),
        "length": len(token),
        "source": "env" if from_env else ("config" if token else ""),
        "editable": not from_env,
    }


def token_meta(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return _meta(api_token(cfg), bool(settings().api_token))


def cf_token_meta(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return _meta(cloudflare_token(cfg), bool(settings().cloudflare_token))
