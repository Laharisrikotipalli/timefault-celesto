"""Scenario allowlist and guest-command allowlist.

Every command the runner sends to a Celesto guest is built by a function in this
module, and ``guest_command_decision`` accepts only commands that match those
builders exactly. Anything else (including LLM-influenced text) is blocked
before it reaches the SDK. This is a host-side control; it does not prove
isolation inside the guest.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")
ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_UPLOAD_BASE64_CHARS = 64 * 1024

INSTALL = (
    "set -eu; apt-get update -qq; "
    "apt-get install -y -qq faketime python3 >/dev/null; "
    "mkdir -p /work; command -v faketime; command -v python3"
)
PROBE_DATE = "2028-02-29"
PROBE = (
    f'faketime "{PROBE_DATE} 12:00:00" python3 -c '
    '"from datetime import date; print(date.today().isoformat())"'
)
VERIFY_RUNTIME = "command -v python3 >/dev/null && command -v faketime >/dev/null && mkdir -p /work"
RUN_FIXTURE = "python3 /work/app.py"

_UPLOAD = re.compile(r"^echo [A-Za-z0-9+/=]+ \| base64 -d > /work/app\.py$")
_REPLAY = re.compile(r'^faketime "(\d{4}-\d{2}-\d{2}) 12:00:00" python3 /work/app\.py$')
_PROBE = re.compile(r'^faketime "(\d{4}-\d{2}-\d{2}) 12:00:00" python3 -c "from datetime import date; print\(date\.today\(\)\.isoformat\(\)\)"$')
_RUN = re.compile(r'^cd /work && faketime "(\d{4}-\d{2}-\d{2}) 12:00:00" python3 app\.py$')


def normalize_iso_date(value: object) -> str | None:
    """Return a canonical YYYY-MM-DD string or None if ``value`` is not exactly that."""
    if not isinstance(value, str) or not ISO_DATE_PATTERN.fullmatch(value):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed.isoformat() if parsed.isoformat() == value else None


def upload_command(encoded: str) -> str:
    return f"echo {encoded} | base64 -d > /work/app.py"


def replay_command(failure_date: str) -> str:
    if normalize_iso_date(failure_date) is None:
        raise ValueError("replay date must be a valid YYYY-MM-DD date")
    return f'faketime "{failure_date} 12:00:00" python3 /work/app.py'


def date_probe_command(day: str) -> str:
    """Print the guest's date under faketime; the caller compares it to ``day``."""
    if normalize_iso_date(day) is None:
        raise ValueError("probe date must be a valid YYYY-MM-DD date")
    return (
        f'faketime "{day} 12:00:00" python3 -c '
        '"from datetime import date; print(date.today().isoformat())"'
    )


def date_run_command(day: str) -> str:
    if normalize_iso_date(day) is None:
        raise ValueError("run date must be a valid YYYY-MM-DD date")
    return f'cd /work && faketime "{day} 12:00:00" python3 app.py'


def guest_command_decision(command: object) -> tuple[bool, str]:
    """Return (allowed, reason). Only commands built by this module are allowed."""
    if not isinstance(command, str) or not command.strip():
        return False, "empty or non-string command"
    if "\x00" in command or "\n" in command or "\r" in command:
        return False, "control characters are not allowed"
    if command in (INSTALL, PROBE, RUN_FIXTURE, VERIFY_RUNTIME):
        return True, "fixed command"
    if _UPLOAD.fullmatch(command):
        encoded = command.split(" ", 2)[1]
        if len(encoded) > MAX_UPLOAD_BASE64_CHARS:
            return False, "fixture upload exceeds size limit"
        return True, "fixture upload"
    match = _REPLAY.fullmatch(command)
    if match and normalize_iso_date(match.group(1)):
        return True, "replay command"
    for pattern, label in ((_PROBE, "date probe"), (_RUN, "date run")):
        match = pattern.fullmatch(command)
        if match and normalize_iso_date(match.group(1)):
            return True, label
    return False, "command is not on the allowlist"


def load_allowed_scenarios(root: Path = ROOT) -> frozenset[str]:
    """Scenario IDs that have BOTH an oracle record and a fixture source file."""
    oracle = root / "oracle" / "labels.jsonl"
    allowed: set[str] = set()
    for line in oracle.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        scenario_id = json.loads(line)["scenario_id"]
        if SCENARIO_ID_PATTERN.fullmatch(scenario_id) and (
            root / "fixtures" / scenario_id / "app.py"
        ).is_file():
            allowed.add(scenario_id)
    return frozenset(allowed)
