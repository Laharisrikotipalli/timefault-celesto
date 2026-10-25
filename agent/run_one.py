"""Thin adapter for the supported Celesto Python cloud-computer API."""

from __future__ import annotations

import json
import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
COMMAND_LOG = ROOT / "commands.jsonl"
MAP: dict[str, str] = {}
COMPUTERS: dict[str, Any] = {}
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
        "command": command,
        "decision": decision,
        "execution_target": "celesto_sandbox",
    }
    with COMMAND_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _error(exc: Exception) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {"type": type(exc).__name__, "message": str(exc)},
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
        CloudComputer, CelestoError = _load_sdk()
    except RuntimeError as exc:
        return _error(exc)
    try:
        computer = CloudComputer(
            lifetime="ephemeral",
            startup_timeout=startup_timeout,
        )
        computer.start()
    except (CelestoError, ValueError) as exc:
        return _error(exc)

    computer_id = computer.id
    if not computer_id:
        computer.delete()
        return {
            "ok": False,
            "error": {"type": "CelestoError", "message": "Cloud computer has no ID."},
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
            "error": {"type": "CommandBlockedError", "message": "Command blocked by policy."},
        }

    try:
        CloudComputer, CelestoError = _load_sdk()
    except RuntimeError as exc:
        return _error(exc)
    computer = COMPUTERS.get(computer_id)
    try:
        if computer is None:
            computer = CloudComputer.get(computer_id)
        result = computer.run(command, timeout=300)
    except (CelestoError, ValueError) as exc:
        return _error(exc)
    return {
        "ok": True,
        "data": {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    }


def _delete(arguments: list[str]) -> dict[str, Any]:
    if len(arguments) != 2:
        raise ValueError("delete expects one computer ID")

    try:
        CloudComputer, CelestoError = _load_sdk()
    except RuntimeError as exc:
        return _error(exc)
    computer_id = arguments[1]
    computer = COMPUTERS.get(computer_id)
    try:
        if computer is None:
            computer = CloudComputer.get(computer_id)
        computer.delete()
    except (CelestoError, ValueError) as exc:
        return _error(exc)
    COMPUTERS.pop(computer_id, None)
    return {"ok": True, "data": {"computer_id": computer_id}}


def cli(arguments: list[str], input_text: str | None = None) -> dict[str, Any]:
    del input_text
    if not arguments:
        raise ValueError("a Celesto operation is required")
    operation = arguments[0]
    if operation == "create":
        return _create(arguments)
    if operation == "exec":
        return _exec(arguments)
    if operation == "delete":
        return _delete(arguments)
    if operation == "list":
        if len(arguments) != 1:
            raise ValueError("list does not accept arguments")
        return {"ok": True, "data": {"computers": list(COMPUTERS)}}
    raise ValueError(f"unsupported Celesto operation: {operation}")
