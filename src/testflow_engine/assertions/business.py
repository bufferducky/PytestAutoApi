"""确定性的业务比较规则；没有动态表达式eval。"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

TYPES = {
    "string": str,
    "object": dict,
    "array": list,
    "number": (int, float, Decimal),
    "integer": int,
    "boolean": bool,
    "null": type(None),
}


def type_matches(value, kind):
    if kind not in TYPES:
        raise ValueError("未知类型: " + kind)
    return isinstance(value, TYPES[kind]) and not (
        isinstance(value, bool) and kind in {"number", "integer"}
    )


def schema_matches(value, schema):
    if set(schema) - {"type", "required", "properties", "items", "enum"}:
        raise ValueError("不支持的结构规则字段")
    if "type" in schema and not type_matches(value, schema["type"]):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if "required" in schema:
        if not isinstance(value, dict) or any(k not in value for k in schema["required"]):
            return False
    if "properties" in schema:
        if not isinstance(value, dict):
            return False
        if any(
            k in value and not schema_matches(value[k], rule)
            for k, rule in schema["properties"].items()
        ):
            return False
    if "items" in schema:
        if not isinstance(value, list) or any(
            not schema_matches(item, schema["items"]) for item in value
        ):
            return False
    return True


def normalize(value, kind, options):
    if kind == "native":
        return value
    if kind == "decimal":
        if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
            raise ValueError("decimal类型不合法")
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("数值不能是NaN/Infinity")
        return result
    if kind == "datetime":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if options.get("unit") not in {"seconds", "milliseconds"}:
                raise ValueError("epoch时间必须声明单位")
            return datetime.fromtimestamp(
                value / (1000 if options["unit"] == "milliseconds" else 1), tz=timezone.utc
            )
        if not isinstance(value, str):
            raise ValueError("时间值必须是ISO文本或带单位epoch")
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            if not options.get("timezone"):
                raise ValueError("无时区日期必须声明timezone")
            result = result.replace(tzinfo=ZoneInfo(options["timezone"]))
        return result.astimezone(timezone.utc)
    raise ValueError("未知value_type: " + kind)


def keyed(values, key):
    if not isinstance(values, list):
        raise ValueError("keyed规则需要数组")
    result = {}
    for item in values:
        if not isinstance(item, dict) or key not in item:
            raise ValueError("集合元素缺key字段")
        identity = json.dumps(item[key], sort_keys=True)
        if identity in result:
            raise ValueError("集合存在重复key，关联不唯一")
        result[identity] = item
    return result


CUSTOM_RULES = {}
BUILTIN_RULES = {"count_delta@1", "unchanged@1", "relation@1"}


def register_rule(reference, callback, reads=()):
    """仅供受控Python插件注册；发布API不能上传或eval代码。"""
    if "@" not in reference or reference in BUILTIN_RULES or reference in CUSTOM_RULES:
        raise ValueError("规则必须使用未占用的版本ID")
    if not callable(callback):
        raise TypeError("规则必须是已加载代码函数")
    CUSTOM_RULES[reference] = (callback, tuple(reads))
