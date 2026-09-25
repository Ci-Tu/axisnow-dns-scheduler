from __future__ import annotations

import copy
from typing import Any, Dict, List

import pytest

from axisnow_scheduler import settings as settings_mod
from axisnow_scheduler.clients import axisnow as axisnow_mod
from axisnow_scheduler.storage import config_store, history

DOMAIN_UUID = "dom-1"
RULE_UUID = "rule-1"


def make_rule(uuid: str = RULE_UUID, ips: List[str] | None = None,
              strategy: str = "priority_order", domain_uuid: str = DOMAIN_UUID) -> Dict[str, Any]:
    return {
        "uuid": uuid,
        "name": "境内",
        "domain": "hub.example.com",
        "type": "A",
        "geo_isp": "internal",
        "dns_domain_uuid": domain_uuid,
        "status": "active",
        "action": {
            "method": "ip_election",
            "conf": {
                "address_pool": {"mode": "customize", "groups": [
                    {"type": "ip", "ips": list(ips or ["192.0.2.1", "192.0.2.2", "192.0.2.3"])},
                ]},
                "response_strategy": {"election_strategy": strategy, "ip_quantity": 1},
                "edge_probe_template_uuid": [],
                "ttl_conf": {"ttl": 60},
            },
        },
    }


class FakeAxisNow:
    """内存版 AxisNow，覆盖测试用到的接口。"""

    def __init__(self) -> None:
        self.domains = [{"uuid": DOMAIN_UUID, "domain": "hub.example.com", "record_type": "A",
                         "status": "active", "provider_type": "self-hosted"}]
        self.rules = {RULE_UUID: make_rule()}
        self.probe: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.updates: List[Dict[str, Any]] = []
        self.deleted_domains: List[str] = []

    # AxisNowClient 构造参数兼容
    def __call__(self, *_a: Any, **_kw: Any) -> FakeAxisNow:
        return self

    def list_domains(self):
        return copy.deepcopy(self.domains)

    def list_rules(self):
        return [copy.deepcopy(r) for r in self.rules.values()]

    def get_rule(self, uuid):
        if uuid not in self.rules:
            raise axisnow_mod.AxisNowError("not found", status=404)
        return copy.deepcopy(self.rules[uuid])

    def update_rule(self, uuid, body):
        self.updates.append(copy.deepcopy(body))
        self.rules[uuid].update({k: v for k, v in body.items() if k in axisnow_mod.RULE_FIELDS})
        return copy.deepcopy(self.rules[uuid])

    def create_rule(self, body):
        new = {**copy.deepcopy(body), "uuid": f"rule-{len(self.rules) + 1}"}
        self.rules[new["uuid"]] = new
        return new

    def delete_rule(self, uuid):
        self.rules.pop(uuid, None)

    def delete_domain(self, uuid):
        self.deleted_domains.append(uuid)
        self.domains = [d for d in self.domains if d["uuid"] != uuid]

    def probe_status(self, uuids):
        return {u: copy.deepcopy(self.probe.get(u, {})) for u in uuids if u in self.probe}

    def probe_templates(self):
        return []

    def probe_tasks(self):
        return []

    def geo_isp_options(self):
        return {"self-hosted": [{"value": "default", "label": "默认线路", "group": ""},
                                {"value": "internal", "label": "境内", "group": "地域"}]}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """每个测试一个全新的 data 目录与全新的进程内状态。"""
    settings_mod.override_settings(settings_mod.Settings(
        data_dir=str(tmp_path), port=4894, timezone_name="Asia/Shanghai", session_days=180,
        api_base=None, api_token=None, cloudflare_token=None, disable_background=True,
        geoip_auto_download=False, web_dist=str(tmp_path / "web")))
    config_store.reset_cache()
    monkeypatch.setattr(history, "_initialized_for", None)
    axisnow_mod.clear_cache()
    from axisnow_scheduler import scheduler
    scheduler._state["applied"].clear()
    yield tmp_path
    config_store.reset_cache()


@pytest.fixture
def fake(monkeypatch):
    fake = FakeAxisNow()
    from axisnow_scheduler import scheduler
    from axisnow_scheduler.api import common
    monkeypatch.setattr(common, "AxisNowClient", fake)
    monkeypatch.setattr(scheduler, "AxisNowClient", fake)
    return fake


@pytest.fixture
def client(fake):
    from axisnow_scheduler.app import create_app

    def mutate(cfg):
        cfg["api_token"] = "t" * 40
        config_store.set_password(cfg, "correct-horse")

    config_store.mutate(mutate)
    app = create_app()
    app.testing = True
    c = app.test_client()
    with c.session_transaction() as s:
        s["auth"] = True
    return c


HDR = {"X-Requested-With": "axisnow"}
