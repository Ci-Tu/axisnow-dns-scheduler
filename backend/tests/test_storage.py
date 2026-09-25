import json
import time

import pytest

from axisnow_scheduler.clients.axisnow import AxisNowClient, clear_cache
from axisnow_scheduler.storage import config_store, history


def test_v1_config_is_migrated_without_losing_slots(isolated):
    legacy = {"api_token": "x" * 30, "rules": {"r": {"enabled": True,
                                                    "slots": [{"id": "s1"}],
                                                    "default_ips": ["192.0.2.1"]}}}
    (isolated / "config.json").write_text(json.dumps(legacy), encoding="utf-8")
    cfg = config_store.load_config()
    tide = cfg["rules"]["r"]["features"]["tide"]
    assert tide["slots"] == [{"id": "s1"}]
    assert tide["default_ips"] == ["192.0.2.1"]
    assert "probe_failover" in cfg["rules"]["r"]["features"]
    assert cfg["version"] == config_store.CONFIG_VERSION


def test_servers_json_names_become_ip_labels(isolated):
    (isolated / "servers.json").write_text(json.dumps([{"ip": "192.0.2.1", "name": "东京"}]),
                                           encoding="utf-8")
    assert config_store.load_config()["ip_labels"] == {"192.0.2.1": {"name": "东京"}}


def test_corrupt_config_is_never_overwritten(isolated):
    (isolated / "config.json").write_text("{broken", encoding="utf-8")
    config_store.load_config()
    assert (isolated / "config.json").read_text(encoding="utf-8") == "{broken"


def test_failed_mutation_leaves_config_untouched():
    def boom(cfg):
        cfg["rules"]["x"] = {}
        raise ValueError("stop")

    with pytest.raises(ValueError):
        config_store.mutate(boom)
    assert "x" not in config_store.load_config()["rules"]


def test_session_key_is_stable():
    assert config_store.get_session_key() == config_store.get_session_key()


def test_legacy_probe_history_is_imported(isolated):
    now = int(time.time())
    (isolated / "probe_history.json").write_text(json.dumps(
        {"samples": {"192.0.2.1": [{"t": now, "s": "available", "ms": None}]}}), encoding="utf-8")
    samples = history.samples_since()
    assert samples["192.0.2.1"][0]["s"] == "available"
    assert (isolated / "probe_history.json.migrated").exists()


def test_uptime_stats():
    stats = history.uptime_stats([{"s": "available", "ms": 10}, {"s": "unavailable", "ms": None}])
    assert stats == {"samples": 2, "uptime": 50.0, "avg_ms": 10}


def test_post_reads_do_not_clear_cache(monkeypatch):
    """回归：旧版把 POST /edge_probe/tasks/status 当写操作，每次都清空整个缓存。"""
    calls = []

    def fake_fetch(self, method, path, params=None, json_body=None):
        calls.append((method, path))
        return {"success": True, "result": [], "result_info": {"total_count": 0}}

    monkeypatch.setattr(AxisNowClient, "_fetch", fake_fetch)
    clear_cache()
    client = AxisNowClient("https://example.invalid", "t" * 30)
    client.list_domains()
    client.probe_status(["r1"])
    client.list_domains()
    assert calls.count(("GET", "/dns_routing_domains")) == 1


def test_pagination_reads_every_page(monkeypatch):
    def fake_fetch(self, method, path, params=None, json_body=None):
        page = params["page"]
        items = [{"uuid": f"{page}-{i}"} for i in range(100 if page == 1 else 7)]
        return {"success": True, "result": items, "result_info": {"total_count": 107}}

    monkeypatch.setattr(AxisNowClient, "_fetch", fake_fetch)
    assert len(AxisNowClient("https://example.invalid", "t" * 30).list_rules()) == 107
