"""Redaction helpers so credentials never reach logs, ledgers, or error messages."""

from __future__ import annotations

import os
import re
from typing import Mapping

_SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)", re.IGNORECASE)
_MIN_SECRET_LENGTH = 6
_PATTERNS = (
    (re.compile(r"sk-[A-Za-z0-9_\-]{16,}"), "<redacted-key>"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=\-]{16,}", re.IGNORECASE), "Bearer <redacted>"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "<redacted-key>"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), "<redacted-key>"),
    (re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"), "<redacted>"),
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def secret_values(env: Mapping[str, str] | None = None) -> list[str]:
    """Return values of secret-looking environment variables, longest first."""
    source = os.environ if env is None else env
    values = {
        value.strip()
        for name, value in source.items()
        if _SECRET_NAME.search(name) and isinstance(value, str)
        and len(value.strip()) >= _MIN_SECRET_LENGTH
    }
    return sorted(values, key=len, reverse=True)


def redact(text: object, env: Mapping[str, str] | None = None, max_length: int | None = None) -> str:
    """Replace known secret values and common credential shapes in ``text``."""
    result = "" if text is None else str(text)
    for value in secret_values(env):
        result = result.replace(value, "<redacted>")
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    result = _CONTROL.sub("", result)
    if max_length is not None and len(result) > max_length:
        result = result[:max_length] + "...<truncated>"
    return result
