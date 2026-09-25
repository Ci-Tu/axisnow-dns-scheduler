from axisnow_scheduler.storage import config_store

from .conftest import DOMAIN_UUID, HDR, RULE_UUID


def test_requires_login(fake):
    from axisnow_scheduler.app import create_app
    c = create_app().test_client()
    assert c.get("/api/rules").status_code == 401
    assert c.get("/api/auth/state").get_json()["setup_required"] is True


def test_setup_then_login_flow(fake):
    from axisnow_scheduler.app import create_app
    c = create_app().test_client()
    r = c.post("/api/auth/setup", json={"password": "short", "confirm": "short"}, headers=HDR)
    assert r.status_code == 400
    r = c.post("/api/auth/setup", json={"password": "long-enough", "confirm": "long-enough"},
               headers=HDR)
    assert r.status_code == 200
    assert c.get("/api/auth/state").get_json()["authenticated"] is True
    # 已设置过密码后不能再次初始化
    r = c.post("/api/auth/setup", json={"password": "another-one", "confirm": "another-one"},
               headers=HDR)
    assert r.status_code == 409


def test_login_rate_limit(client):
    fresh = client.application.test_client()
    for _ in range(10):
        assert fresh.post("/api/auth/login", json={"password": "wrong"},
                          headers=HDR).status_code == 401
    assert fresh.post("/api/auth/login", json={"password": "correct-horse"},
                      headers=HDR).status_code == 429


def test_writes_require_csrf_header(client):
    assert client.post(f"/api/rules/{RULE_UUID}/adopt").status_code == 403


def test_list_rules(client, fake):
    data = client.get("/api/rules").get_json()
    rule = data["rules"][0]
    assert rule["uuid"] == RULE_UUID
    assert rule["geo_isp_label"] == "境内" and rule["geo_isp_region"] == "cn"
    assert [i["ip"] for i in rule["ips"]] == ["192.0.2.1", "192.0.2.2", "192.0.2.3"]
    assert rule["ips"][0]["geo"]["private"] is True  # 文档保留地址不是公网
    assert rule["managed"] is False


def test_adopt_and_tide_slot(client, fake):
    assert client.post(f"/api/rules/{RULE_UUID}/adopt", headers=HDR).status_code == 200
    r = client.post(f"/api/rules/{RULE_UUID}/tide/slots", headers=HDR, json={
        "name": "夜间", "start": "22:00", "end": "06:00", "days": [0, 1, 2, 3, 4, 5, 6],
        "ips": ["192.0.2.3"]})
    slot = r.get_json()["slot"]
    assert slot["cross_midnight"] and slot["ips"] == ["192.0.2.3", "192.0.2.1", "192.0.2.2"]
    tide = config_store.load_config()["rules"][RULE_UUID]["features"]["tide"]
    assert tide["default_ips"] == ["192.0.2.1", "192.0.2.2", "192.0.2.3"]


def test_invalid_slot_is_rejected(client, fake):
    r = client.post(f"/api/rules/{RULE_UUID}/tide/slots", headers=HDR,
                    json={"start": "25:00", "end": "06:00", "days": [0]})
    assert r.status_code == 400


def test_update_rule_reconciles_local_config(client, fake):
    client.post(f"/api/rules/{RULE_UUID}/adopt", headers=HDR)
    client.post(f"/api/rules/{RULE_UUID}/notes", headers=HDR,
                json={"ip": "192.0.2.3", "note": "old"})
    r = client.put(f"/api/rules/{RULE_UUID}", headers=HDR,
                   json={"ips": ["192.0.2.2", "192.0.2.4"]})
    assert r.status_code == 200
    entry = config_store.load_config()["rules"][RULE_UUID]
    assert entry["features"]["tide"]["default_ips"] == ["192.0.2.2", "192.0.2.4"]
    assert entry["ip_notes"] == {}


def test_delete_domain_cleans_local_rules(client, fake):
    """回归：旧版按「规则 uuid 以域名 uuid 开头」清理，实际从未生效。"""
    client.post(f"/api/rules/{RULE_UUID}/adopt", headers=HDR)
    r = client.delete(f"/api/domains/{DOMAIN_UUID}", headers=HDR, json={"confirm": True})
    assert r.get_json()["removed_rules"] == 1
    assert RULE_UUID not in config_store.load_config()["rules"]


def test_destructive_actions_need_confirm(client, fake):
    assert client.delete(f"/api/rules/{RULE_UUID}", headers=HDR, json={}).status_code == 400
    assert RULE_UUID in fake.rules


def test_upstream_error_maps_to_502(client, fake):
    r = client.get("/api/rules/does-not-exist")
    assert r.status_code == 502 and r.get_json()["upstream"] == "axisnow"


def test_ip_labels(client, fake):
    assert client.put("/api/ip-labels", headers=HDR,
                      json={"ip": "192.0.2.1", "name": "东京"}).status_code == 200
    rule = client.get("/api/rules").get_json()["rules"][0]
    assert rule["ips"][0]["name"] == "东京"
    assert client.put("/api/ip-labels", headers=HDR,
                      json={"ip": "nope", "name": "x"}).status_code == 400


def test_dashboard(client, fake):
    data = client.get("/api/dashboard").get_json()
    assert data["counts"]["rules"] == 1
    assert len(data["nodes"]) == 3 and data["nodes"][0]["lines"] == ["境内"]


def test_token_from_env_is_read_only(client, monkeypatch):
    from axisnow_scheduler import settings as settings_mod
    s = settings_mod.settings()
    monkeypatch.setattr(settings_mod, "_settings", s.__class__(**{**s.__dict__,
                                                                  "api_token": "e" * 40}))
    meta = client.get("/api/meta").get_json()["token"]
    assert meta == {"configured": True, "length": 40, "source": "env", "editable": False}
    assert client.put("/api/settings/token", headers=HDR,
                      json={"token": "n" * 40}).status_code == 409


def test_spa_fallback_without_build(client):
    assert client.get("/rules/abc").status_code == 503
    r = client.get("/api/nope")
    assert r.status_code == 404 and r.get_json()["ok"] is False
