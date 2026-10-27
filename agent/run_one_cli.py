"""`celesto` CLI transport for the Celesto adapter.

This is the interface the project's first real cloud run used
(`celesto computer <op> --cloud --json`). Flags are unchanged from that code.
Hardening: no retries, redacted errors, and failures classified as setup or
transport, with `ambiguous` set when the guest may have acted on the request.
Error classification from CLI text is a heuristic.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from agent.sanitize import redact

_SETUP_HINTS = ("celesto_core", "no module named", "api key", "api_key", "unauthorized",
                "not logged in", "401", "403", "command not found")


def _error(message: object, category: str, ambiguous: bool, kind: str = "CelestoCliError") -> dict[str, Any]:
    return {"ok": False, "data": None,
            "error": {"type": kind, "message": redact(message, max_length=500),
                      "category": category, "ambiguous": ambiguous}}


def cli(args: list[str], input_text: str | None = None, timeout: int = 90) -> dict[str, Any]:
    if not args:
        raise ValueError("a Celesto operation is required")
    operation = args[0]
    # Only create/exec can leave the guest in an unknown state when they fail.
    may_be_ambiguous = operation in ("create", "exec")
    split = args.index("--") if "--" in args else len(args)
    prefix = ["celesto", "computer", *args[:split]]
    if "exec" in args[:split]:
        prefix.extend(["--timeout", str(timeout)])
    full = prefix + ["--cloud", "--json", *args[split:]]
    try:
        proc = subprocess.run(full, capture_output=True, text=True, input=input_text, timeout=timeout + 10)
    except FileNotFoundError:
        return _error("celesto CLI executable not found", "setup", False, "FileNotFoundError")
    except subprocess.TimeoutExpired:
        return _error(f"local CLI timed out after {timeout + 10}s", "transport", may_be_ambiguous,
                      "TimeoutExpired")
    try:
        result = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        result = None
    if isinstance(result, dict) and result.get("data") is not None and proc.returncode == 0:
        return result
    detail = ""
    if isinstance(result, dict):
        detail = str((result.get("error") or {}).get("message") or "")
    detail = detail or (proc.stderr or proc.stdout or "celesto CLI returned no usable output")[-500:]
    lowered = detail.lower()
    category = "setup" if any(hint in lowered for hint in _SETUP_HINTS) else "transport"
    return _error(detail, category, may_be_ambiguous and category == "transport")
