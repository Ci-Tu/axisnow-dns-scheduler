"""AxisNow 领域常量：线路标签、选取策略、地址池模式。前后端叫法统一以这里为准。"""

from __future__ import annotations

from typing import Dict

# 线路（geo_isp）的中文标签。服务端返回的 value 与 displayName 的 i18n key 写法不一致
# （internal ↔ chinaRegion），两套都要认。
GEO_ISP_VALUE_LABELS: Dict[str, str] = {
    "default": "默认线路",
    "internal": "境内",
    "oversea": "境外",
    "other-isp": "其他运营商",
    "major-region": "主要地区",
    "global": "全球",
    "domestic": "国内",
    "10=0": "电信",
    "10=1": "联通",
    "10=3": "移动",
    "3=0": "国内",
    "80=0": "搜索引擎",
    "CN": "中国大陆",
    "hk-mo-tw": "港澳台",
    "Abroad": "境外",
    "AF": "非洲", "AN": "南极洲", "AS": "亚洲", "EU": "欧洲",
    "NA": "北美洲", "OC": "大洋洲", "SA": "南美洲",
    "AFR": "非洲", "ASI": "亚洲", "EUR": "欧洲",
    "NAM": "北美洲", "OCN": "大洋洲", "SAM": "南美洲",
}

GEO_ISP_KEY_LABELS: Dict[str, str] = {
    "default": "默认线路",
    "chinaRegion": "境内",
    "overseas": "境外",
    "isp": "运营商",
    "region": "大区",
    "searchEngine": "搜索引擎",
    "cloudProviders": "云厂商",
    "telecom": "电信",
    "unicom": "联通",
    "mobile": "移动",
    "otherIsp": "其他运营商",
    "domestic": "国内",
    "global": "全球",
    "majorRegion": "主要地区",
}

# 线路在控制台里是两级下拉：分组 + 具体线路；空串表示顶级
GEO_ISP_GROUP_OF: Dict[str, str] = {
    "default": "",
    "internal": "地域", "oversea": "地域", "region": "地域",
    "3=0": "地域", "global": "地域", "major-region": "地域", "domestic": "地域",
    "AF": "地域", "AN": "地域", "AS": "地域", "EU": "地域",
    "NA": "地域", "OC": "地域", "SA": "地域",
    "A1": "地域", "AFR": "地域", "ASI": "地域", "EUR": "地域",
    "NAM": "地域", "OCN": "地域", "SAM": "地域",
    "CN": "地域", "hk-mo-tw": "地域", "Abroad": "地域",
    "isp": "运营商", "telecom": "运营商", "unicom": "运营商", "mobile": "运营商",
    "other-isp": "运营商", "otherIsp": "运营商", "10=0": "运营商",
    "10=1": "运营商", "10=3": "运营商", "10=2": "运营商",
    "search": "搜索引擎", "searchEngine": "搜索引擎", "80=0": "搜索引擎",
    "cloud-providers": "云厂商", "cloudProviders": "云厂商",
}

# 线路对应的地区标识，前端据此显示国旗或地球图标。
#   ISO 3166 两位码 → 国旗；"world" → 地球；None → 不显示
GEO_ISP_REGION: Dict[str, str] = {
    "internal": "cn", "domestic": "cn", "3=0": "cn", "CN": "cn",
    "10=0": "cn", "10=1": "cn", "10=3": "cn", "10=2": "cn",
    "hk-mo-tw": "hk",
    "oversea": "world", "Abroad": "world", "global": "world", "default": "world",
    "major-region": "world",
    "AF": "world", "AN": "world", "AS": "world", "EU": "eu",
    "NA": "world", "OC": "world", "SA": "world",
    "AFR": "world", "ASI": "world", "EUR": "eu",
    "NAM": "world", "OCN": "world", "SAM": "world",
}

# 平台托管调度域常用的三条排前面
PLATFORM_LINE_ORDER = ["default", "internal", "oversea"]

# 选取策略：插入顺序即界面展示顺序（随机 / 顺序 / 优选，与官方控制台一致）
STRATEGY_LABELS: Dict[str, str] = {
    "random": "随机",
    "priority_order": "顺序",
    "quality_optimized": "优选",
}

STRATEGY_HELP: Dict[str, str] = {
    "random": "从地址池中随机选取最终解析地址",
    "priority_order": "严格按 IP 顺序返回，排在前面的优先级最高；适合自己控线路",
    "quality_optimized": "依据拨测数据动态优选最快最稳的地址，需要关联地址监控",
}

TRIGGER_INTERVAL_OPTIONS = [5, 10]

# 地址池模式。AxisNow schema 限制：priority_order 不接受 all_valid_eips
ADDRESS_POOL_MODES: Dict[str, str] = {
    "all_eips": "所有 EIP",
    "custom_eips": "指定 EIP",
    "custom_ips": "自定义 IP",
}
STRATEGIES_WITHOUT_ALL_EIPS = ("priority_order",)

# 地址池里除 IP 之外的分组类型，编辑时原样保留
NON_IP_GROUP_TYPES = ("eip", "eip_tag", "domain")

WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def label_for_geo_isp(value: str, display_name: str = "") -> str:
    """把线路值 / i18n key 翻成中文标签；识别不了就原样返回。"""
    if value in GEO_ISP_VALUE_LABELS:
        return GEO_ISP_VALUE_LABELS[value]
    key = (display_name or "").rsplit(".", 1)[-1]
    return GEO_ISP_KEY_LABELS.get(key) or value or "(未命名线路)"


def group_of_geo_isp(value: str, display_name: str = "") -> str:
    if value in GEO_ISP_GROUP_OF:
        return GEO_ISP_GROUP_OF[value]
    key = (display_name or "").rsplit(".", 1)[-1]
    return GEO_ISP_GROUP_OF.get(key, "其它")


def region_of_geo_isp(value: str) -> str:
    return GEO_ISP_REGION.get(value or "default", "world")
