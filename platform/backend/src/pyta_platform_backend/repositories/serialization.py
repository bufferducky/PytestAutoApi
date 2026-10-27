"""历史导入与仓储共用的 JSON/时间序列化。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def dump_json(value: Any) -> str:
    """把 Python 对象序列化为 JSON 文本。"""

    return json.dumps(value, ensure_ascii=False)


def load_json(value: str | None, default: Any) -> Any:
    """把 JSON 文本还原为 Python 对象。"""

    if value is None or value == "":
        return default
    return json.loads(value) if isinstance(value, str) else value


def dump_datetime(value: datetime | None) -> str | None:
    """把 datetime 序列化成 ISO 文本。"""

    if value is None:
        return None
    return value.isoformat()


def load_datetime(value: str | None) -> datetime | None:
    """把 ISO 文本还原为 datetime。"""

    if not value:
        return None
    return datetime.fromisoformat(value)
