"""运行公开快照的存储边界：先脱敏，再截断；原始凭证仅留在执行内存。"""

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from urllib.parse import quote, unquote

REDACTED = "[REDACTED]"
SENSITIVE = re.compile(
    r"password|passwd|pwd|token|authorization|cookie|secret|signature|credential|"
    r"api[_-]?key|access[_-]?key|session[_-]?id|upload[_-]?url|phone|mobile|email|"
    r"customer[_-]?name|patient[_-]?name|transcript|id[_-]?card",
    re.I,
)


PUBLIC_CONFIGURATION_FIELDS = {
    "token_path",
    "token_cache_key",
    "password_field",
    "password_transform",
    "header_template",
    "header_name",
    "username_field",
}


def sensitive_key(key):
    return bool(
        SENSITIVE.search(str(key))
        and not str(key).endswith("_ref")
        and key not in PUBLIC_CONFIGURATION_FIELDS
    )


class Redactor:
    def __init__(self, value=None):
        self.secrets = set()
        self.secret_numbers = set()
        self.remember(value)

    def remember(self, value, parent=None):
        if isinstance(value, dict):
            for key, child in value.items():
                if (
                    sensitive_key(key)
                    or parent in {"customer", "patient"}
                    and key in {"name", "full_name", "contact"}
                ):
                    self._collect(child)
                self.remember(child, str(key).lower())
        elif isinstance(value, (list, tuple)):
            for child in value:
                self.remember(child)
        elif isinstance(value, str):
            for secret in re.findall(
                r"(?i)[?&](?:token|signature|x-amz-signature|secret|api_key)=([^&\s]+)", value
            ):
                self._collect(unquote(secret))

    @staticmethod
    def public_value(value):
        # Durable tasks retain exact templates, including the standard Bearer prefix.
        # Arbitrary sensitive literals around a template are still redacted.
        return (
            value is None
            or value == ""
            or (isinstance(value, str) and re.fullmatch(r"(?:Bearer )?{{\s*[^{}]+\s*}}", value))
            or (
                isinstance(value, dict)
                and "secret_ref" in value
                and set(value) <= {"secret_ref", "transform"}
            )
        )

    def _collect(self, value):
        if self.public_value(value):
            return
        if isinstance(value, str) and value and value != REDACTED:
            self.secrets.update((value, quote(value, safe=""), unquote(value)))
            if value.startswith("Bearer "):
                self.secrets.add(value[7:])
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            self.secret_numbers.add(value)
            self.secrets.add(str(value))
        elif isinstance(value, dict):
            for child in value.values():
                self._collect(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                self._collect(child)

    def clean(self, value):
        self.remember(value)
        return self._clean(value)

    def _clean(self, value, parent=None):
        if isinstance(value, dict):
            return {
                str(key): REDACTED
                if (
                    sensitive_key(key)
                    or parent in {"customer", "patient"}
                    and key in {"name", "full_name", "contact"}
                )
                and not self.public_value(child)
                else self._clean(child, str(key).lower())
                for key, child in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [self._clean(child) for child in value]
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, bytes):
            # 二进制不作为 JSON 正文外发。
            return {"bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()}
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value in self.secret_numbers
        ):
            return REDACTED
        if isinstance(value, str):
            value = re.sub(r"(?<![a-zA-Z0-9])1[3-9]\d{9}(?![a-zA-Z0-9])", "[REDACTED_PHONE]", value)
            value = re.sub(
                r"(?i)([\"\']?(?:authorization|password|passwd|token|secret|cookie)[\"\']?\s*[:=]\s*[\"\']?)(?:Bearer\s+)?[^\s,;\"\'}]+",
                r"\1[REDACTED]",
                value,
            )
            for secret in sorted(self.secrets, key=len, reverse=True):
                value = value.replace(secret, REDACTED)
            return re.sub(
                r"(?i)([?&](?:token|signature|x-amz-[^=&]+|secret|key)\s*=)[^&\s]+",
                r"\1[REDACTED]",
                value,
            )
        if value is None or isinstance(value, (int, float, bool)):
            return value
        return self._clean(str(value))

    def bounded(self, value, limit=65536):
        clean = self.clean(value)
        raw = json.dumps(clean, ensure_ascii=False).encode("utf-8")
        if len(raw) <= limit:
            return clean
        return {
            "truncated": True,
            "byte_size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "preview": raw[:limit].decode("utf-8", errors="ignore"),
        }
