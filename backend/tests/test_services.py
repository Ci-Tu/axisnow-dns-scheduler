from datetime import datetime

import pytest

from axisnow_scheduler.clients.axisnow import set_ip_order
from axisnow_scheduler.features.probe_failover import split_by_health
from axisnow_scheduler.features.tide import make_slot, normalize_order, pick_slot, slot_matches
from axisnow_scheduler.services import rules as svc
from axisnow_scheduler.settings import get_tz

from .conftest import make_rule

TZ = get_tz("Asia/Shanghai")


def at(day: int, hh: int, mm: int = 0) -> datetime:
    # 2026-09-21 是周一
    return datetime(2026, 9, 21 + day, hh, mm, tzinfo=TZ)


class TestNormalizeIps:
    def test_dedupes_and_keeps_order(self):
        assert svc.normalize_ips(["192.0.2.2", " 192.0.2.1 ", "192.0.2.2", ""]) == \
            ["192.0.2.2", "192.0.2.1"]

    def test_canonicalizes_ipv6(self):
        assert svc.normalize_ips(["2001:DB8::0:1"]) == ["2001:db8::1"]

    @pytest.mark.parametrize("raw", [["not-an-ip"], "192.0.2.1", []])
    def test_rejects_bad_input(self, raw):
        with pytest.raises(svc.ValidationError):
            svc.normalize_ips(raw)

    def test_limit(self):
        with pytest.raises(svc.ValidationError):
            svc.normalize_ips([f"10.0.0.{i}" for i in range(51)])


class TestBuildAction:
    def test_priority_order_rejects_all_eips(self):
        with pytest.raises(svc.ValidationError):
            svc.build_action(strategy="priority_order", ip_quantity=1,
                             pool=svc.build_address_pool("all_eips"))

    def test_quality_optimized_sets_interval(self):
        action = svc.build_action(strategy="quality_optimized", ip_quantity=2,
                                  pool=svc.build_address_pool("custom_ips", ips=["192.0.2.1"]),
                                  trigger_interval=10)
        assert action["conf"]["response_strategy"] == {
            "ip_quantity": 2, "election_strategy": "quality_optimized", "trigger_interval": 10}

    def test_quantity_bounds(self):
        with pytest.raises(svc.ValidationError):
            svc.build_action(strategy="random", ip_quantity=11,
                             pool=svc.build_address_pool("custom_ips", ips=["192.0.2.1"]))

    def test_extra_groups_are_kept_but_not_duplicated(self):
        extra = [{"type": "eip_tag", "tags": ["x"]}, {"type": "eip", "eip_uuids": ["old"]}]
        pool = svc.build_address_pool("custom_eips", eip_uuids=["new"], extra_groups=extra)
        assert pool["groups"] == [{"type": "eip", "eip_uuids": ["new"]},
                                  {"type": "eip_tag", "tags": ["x"]}]


class TestBuildUpdatedRule:
    def test_keeps_remote_values_when_body_is_empty(self):
        remote = make_rule()
        payload = svc.build_updated_rule(remote, {})
        assert payload["geo_isp"] == "internal"
        assert payload["name"] == "境内"
        assert payload["action"]["conf"]["address_pool"] == remote["action"]["conf"]["address_pool"]

    def test_clearing_probe_template(self):
        remote = make_rule()
        remote["action"]["conf"]["edge_probe_template_uuid"] = ["tpl"]
        payload = svc.build_updated_rule(remote, {"edge_probe_template_uuid": ""})
        assert payload["action"]["conf"]["edge_probe_template_uuid"] == []

    def test_empty_name_is_respected(self):
        payload = svc.build_updated_rule(make_rule(), {"name": ""})
        assert payload["name"] == ""


class TestReconcilePool:
    def test_drops_removed_and_appends_new(self):
        entry = {"ip_notes": {"192.0.2.1": "a", "192.0.2.9": "gone"},
                 "features": {"tide": {"default_ips": ["192.0.2.9", "192.0.2.2", "192.0.2.1"],
                                       "slots": [{"ips": ["192.0.2.1"]}]}}}
        svc.reconcile_pool(entry, ["192.0.2.1", "192.0.2.2", "192.0.2.3"])
        tide = entry["features"]["tide"]
        assert tide["default_ips"] == ["192.0.2.2", "192.0.2.1", "192.0.2.3"]
        assert tide["slots"][0]["ips"] == ["192.0.2.1", "192.0.2.2", "192.0.2.3"]
        assert entry["ip_notes"] == {"192.0.2.1": "a"}

    def test_non_ip_pool_leaves_config_untouched(self):
        entry = {"ip_notes": {"192.0.2.1": "a"},
                 "features": {"tide": {"default_ips": ["192.0.2.1"]}}}
        svc.reconcile_pool(entry, [])
        assert entry["ip_notes"] == {"192.0.2.1": "a"}
        assert entry["features"]["tide"]["default_ips"] == ["192.0.2.1"]


class TestTide:
    def test_simple_window(self):
        slot = {"start": "09:00", "end": "12:00", "days": [0]}
        assert slot_matches(slot, at(0, 9))
        assert not slot_matches(slot, at(0, 12))
        assert not slot_matches(slot, at(1, 10))

    def test_cross_midnight_uses_start_day(self):
        slot = {"start": "22:00", "end": "02:00", "days": [0]}  # 周一晚上
        assert slot_matches(slot, at(0, 23))
        assert slot_matches(slot, at(1, 1))       # 周二凌晨仍算周一的时段
        assert not slot_matches(slot, at(1, 23))

    def test_equal_start_end_is_all_day(self):
        assert slot_matches({"start": "00:00", "end": "00:00", "days": [2]}, at(2, 15))

    def test_first_matching_slot_wins(self):
        a = {"id": "a", "start": "08:00", "end": "20:00"}
        b = {"id": "b", "start": "09:00", "end": "10:00"}
        assert pick_slot([a, b], at(0, 9, 30))["id"] == "a"

    def test_make_slot_marks_cross_midnight(self):
        assert make_slot({"start": "23:00", "end": "01:00", "days": [0]}, ["x"])["cross_midnight"]

    def test_normalize_order(self):
        assert normalize_order(["c", "x", "a"], ["a", "b", "c"]) == ["c", "a", "b"]


def test_split_by_health_is_stable():
    probe = {"b": {"status": "unavailable"}, "c": {"status": "available"}}
    assert split_by_health(["a", "b", "c"], probe) == (["c"], ["b"], ["a"])


def test_set_ip_order_keeps_unlisted_ips():
    rule = set_ip_order(make_rule(), ["192.0.2.3"])
    assert rule["action"]["conf"]["address_pool"]["groups"][0]["ips"] == \
        ["192.0.2.3", "192.0.2.1", "192.0.2.2"]
