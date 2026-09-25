from datetime import datetime

from axisnow_scheduler import scheduler
from axisnow_scheduler.settings import get_tz
from axisnow_scheduler.storage import config_store, history

from .conftest import RULE_UUID

TZ = get_tz("Asia/Shanghai")
MONDAY_10 = datetime(2026, 9, 21, 10, 0, tzinfo=TZ)


def manage(slots=None, failover=True):
    def mutate(cfg):
        cfg["rules"][RULE_UUID] = {
            "enabled": True,
            "ip_notes": {},
            "features": {
                "tide": {"enabled": True, "default_ips": ["192.0.2.1", "192.0.2.2", "192.0.2.3"],
                         "slots": slots or []},
                "probe_failover": {"enabled": failover, "demote_unavailable": True,
                                   "min_healthy": 1},
            },
        }
    config_store.mutate(mutate)


def current_order(fake):
    return fake.rules[RULE_UUID]["action"]["conf"]["address_pool"]["groups"][0]["ips"]


def test_no_write_when_remote_already_matches(fake):
    manage()
    result = scheduler.tick(client=fake, at=MONDAY_10)
    assert result["applied"] == 0
    assert fake.updates == []


def test_active_slot_is_applied_once(fake):
    manage(slots=[{"id": "s", "name": "上午", "start": "09:00", "end": "12:00",
                   "days": [0], "ips": ["192.0.2.3", "192.0.2.1", "192.0.2.2"]}])
    assert scheduler.tick(client=fake, at=MONDAY_10)["applied"] == 1
    assert current_order(fake) == ["192.0.2.3", "192.0.2.1", "192.0.2.2"]
    # 第二轮：与上次下发一致，不再写
    assert scheduler.tick(client=fake, at=MONDAY_10)["applied"] == 0
    events = history.recent_events()
    assert events[0]["slot"] == "上午" and events[0]["ok"]


def test_failover_demotes_unavailable_on_top_of_tide(fake):
    manage()
    fake.probe[RULE_UUID] = {"192.0.2.1": {"status": "unavailable"},
                             "192.0.2.2": {"status": "available"},
                             "192.0.2.3": {"status": "available"}}
    scheduler.tick(client=fake, at=MONDAY_10)
    assert current_order(fake) == ["192.0.2.2", "192.0.2.3", "192.0.2.1"]


def test_disabled_scheduler_skips(fake):
    manage()
    config_store.mutate(lambda c: c.__setitem__("scheduler", {"enabled": False}))
    assert scheduler.tick(client=fake)["skipped"]


def test_missing_rule_is_reported(fake):
    manage()
    fake.rules.clear()
    assert "规则已不存在" in scheduler.tick(client=fake)["errors"][0]
