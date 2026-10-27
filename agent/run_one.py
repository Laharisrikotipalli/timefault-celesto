"""Thin adapter for the supported Celesto Python cloud-computer API."""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from agent.sanitize import redact  # noqa: E402

COMMAND_LOG = ROOT / "logs" / "commands.jsonl"
TRANSPORT_ENV = "TIMEFAULT_CELESTO_TRANSPORT"  # "cli" (default, used by the first real cloud run) or "sdk"
EXEC_TIMEOUT_S = 300  # SDK transport
CLI_EXEC_TIMEOUT_S = 90  # CLI transport (the value used by the first real cloud run)
MAP: dict[str, str] = {}
COMPUTERS: dict[str, Any] = {}
_AUDIT_LOCK = threading.Lock()
# Exceptions raised before a command is sent: the guest cannot have run it.
_NOT_SENT = {"ValueError", "ValidationError", "CommandExecutionUnavailableError"}
DENY = (
    r"\brm\s+-rf\s+/(?:\s|['\"]|$)",
    r"\bmkfs(?:\.\w+)?\b",
    r":\(\)\s*\{",
)


def audit(sandbox_name: str, command: str, decision: str) -> None:
    if decision not in {"allow", "block"}:
        raise ValueError("decision must be 'allow' or 'block'")
    COMMAND_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "sandbox_name": sandbox_name,
        "command": redact(command),
        "decision": decision,
        "execution_target": "celesto_sandbox",
    }
    with _AUDIT_LOCK, COMMAND_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _error(
    exc: Exception,
    *,
    category: str,
    ambiguous: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    """Return a sanitized error result.

    category: "setup" (SDK/credentials/config) or "transport" (cloud/API failure).
    ambiguous: True when the guest may have executed the request despite the error.
    Messages are redacted; raw exception text never leaves this function unredacted.
    """
    return {
        "ok": False,
        "error": {
            "type": type(exc).__name__,
            "message": redact(exc, max_length=500),
            "category": category,
            "ambiguous": ambiguous,
            **extra,
        },
    }


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(name.strip(), value)


def _load_sdk() -> tuple[type[Any], type[Exception]]:
    _load_dotenv()
    try:
        from celesto import CloudComputer
        from celesto.exceptions import CelestoError
    except ModuleNotFoundError as exc:
        if exc.name == "celesto_core":
            raise RuntimeError(
                "The Celesto SDK is incomplete: install celesto-core on a supported "
                "Linux/macOS environment, or run the cloud investigation in the "
                "project's Linux Docker image."
            ) from exc
        raise RuntimeError(
            f"The Celesto SDK could not be imported because module {exc.name!r} is missing."
        ) from exc
    except ImportError as exc:
        raise RuntimeError("The Celesto SDK could not be imported.") from exc
    return CloudComputer, CelestoError


def _create(arguments: list[str]) -> dict[str, Any]:
    if len(arguments) != 3 or arguments[1] != "--boot-timeout":
        raise ValueError("create accepts only --boot-timeout <seconds>")
    try:
        startup_timeout = float(arguments[2])
    except ValueError as exc:
        raise ValueError("--boot-timeout must be a positive number of seconds") from exc
    if startup_timeout <= 0:
        raise ValueError("--boot-timeout must be a positive number of seconds")

    try:
        CloudComputer, _ = _load_sdk()
    except RuntimeError as exc:
        return _error(exc, category="setup")

    computer = None
    try:
        computer = CloudComputer(lifetime="ephemeral", startup_timeout=startup_timeout)
        computer.start()
    except Exception as exc:  # noqa: BLE001 - classified and sanitized below
        # The SDK already tries to delete a computer that failed to start. If a
        # handle with an ID exists, retry once so a failed start never leaks.
        orphan_id = getattr(computer, "id", None) if computer is not None else None
        cleanup_ok = None
        if orphan_id and computer is not None:
            try:
                computer.delete()
                cleanup_ok = True
            except Exception:  # noqa: BLE001
                cleanup_ok = False
        category = "setup" if type(exc).__name__ in _NOT_SENT else "transport"
        return _error(
            exc,
            category=category,
            ambiguous=orphan_id is not None and cleanup_ok is not True,
            orphan_computer_id=orphan_id if cleanup_ok is False else None,
            cleanup_attempted=orphan_id is not None,
            cleanup_ok=cleanup_ok,
        )

    computer_id = computer.id
    if not computer_id:
        try:
            computer.delete()
        except Exception:  # noqa: BLE001
            pass
        return {
            "ok": False,
            "error": {
                "type": "CelestoError",
                "message": "Cloud computer has no ID.",
                "category": "transport",
                "ambiguous": False,
            },
        }
    COMPUTERS[computer_id] = computer
    return {"ok": True, "data": {"computer_id": computer_id}}


def _exec(arguments: list[str]) -> dict[str, Any]:
    if len(arguments) < 5 or arguments[2] != "--":
        raise ValueError("exec expects <computer_id> -- <command>")
    computer_id = arguments[1]
    command = shlex.join(arguments[3:])
    if any(re.search(pattern, command) for pattern in DENY):
        return {
            "ok": False,
            "blocked": True,
            "error": {
                "type": "CommandBlockedError",
                "message": "Command blocked by policy.",
                "category": "policy",
                "ambiguous": False,
            },
        }

    try:
        CloudComputer, _ = _load_sdk()
    except RuntimeError as exc:
        return _error(exc, category="setup")
    # A single attempt only. After a transport failure the guest may or may not
    # have run the command, so the adapter never retries and flags the result.
    try:
        computer = COMPUTERS.get(computer_id)
        if computer is None:
            computer = CloudComputer.get(computer_id)
        result = computer.run(command, timeout=EXEC_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 - classified and sanitized below
        not_sent = type(exc).__name__ in _NOT_SENT
        return _error(exc, category="setup" if not_sent else "transport", ambiguous=not not_sent)
    return {
        "ok": True,
        "data": {
            "exit_code": result.exit_code,
            "stdout": redact(result.stdout),
            "stderr": redact(result.stderr),
        },
    }


def _delete(arguments: list[str]) -> dict[str, Any]:
    if len(arguments) != 2:
        raise ValueError("delete expects one computer ID")

    try:
        CloudComputer, _ = _load_sdk()
    except RuntimeError as exc:
        return _error(exc, category="setup")
    computer_id = arguments[1]
    try:
        computer = COMPUTERS.get(computer_id)
        if computer is None:
            computer = CloudComputer.get(computer_id)
        computer.delete()
    except Exception as exc:  # noqa: BLE001 - classified and sanitized below
        return _error(exc, category="transport", computer_id=computer_id)
    COMPUTERS.pop(computer_id, None)
    return {"ok": True, "data": {"computer_id": computer_id}}


def cli(arguments: list[str], input_text: str | None = None, timeout: int | None = None) -> dict[str, Any]:
    if not arguments:
        raise ValueError("a Celesto operation is required")
    _load_dotenv()
    transport = os.environ.get(TRANSPORT_ENV, "cli")
    if transport not in ("cli", "sdk"):
        raise ValueError(f"{TRANSPORT_ENV} must be 'cli' or 'sdk'")
    operation = arguments[0]
    if operation == "list":
        if len(arguments) != 1:
            raise ValueError("list does not accept arguments")
        return {"ok": True, "data": {"computers": list(COMPUTERS)}}
    if operation == "exec":
        if len(arguments) < 5 or arguments[2] != "--":
            raise ValueError("exec expects <computer_id> -- <command>")
        if any(re.search(pattern, shlex.join(arguments[3:])) for pattern in DENY):
            return {"ok": False, "blocked": True, "error": {
                "type": "CommandBlockedError", "message": "Command blocked by policy.",
                "category": "policy", "ambiguous": False}}
    if operation not in ("create", "exec", "delete"):
        raise ValueError(f"unsupported Celesto operation: {operation}")
    if transport == "cli":
        from agent import run_one_cli
        return run_one_cli.cli(arguments, input_text, timeout or CLI_EXEC_TIMEOUT_S)
    if operation == "create":
        return _create(arguments)
    if operation == "exec":
        return _exec(arguments)
    return _delete(arguments)
