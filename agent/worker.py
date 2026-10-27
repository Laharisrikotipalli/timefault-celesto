import os
import sys
import time
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api import run_store  # noqa: E402
from agent.run_service import run_investigation  # noqa: E402
from agent.sanitize import redact  # noqa: E402


POLL_INTERVAL_SECONDS = 2

SAFE_FAILURE_MESSAGE = (
    "Investigation failed; check worker configuration and logs."
)
ENVIRONMENT_FAILURE_MESSAGE = (
    "Investigation could not be completed because the execution environment "
    "could not be verified; no verdict was recorded."
)


class PersistenceError(RuntimeError):
    """A run's final state could not be stored. Never swallowed."""


def get_allowed_scenarios():
    """Read the explicitly configured scenario allowlist."""
    return [
        item.strip()
        for item in os.environ.get(
            "WORKER_SCENARIO_IDS", ""
        ).split(",")
        if item.strip()
    ]


def _log_error(prefix, exc):
    # Exception text and tracebacks can contain credentials: redact before printing.
    print(redact(f"{prefix}: {type(exc).__name__}: {exc}", max_length=500), flush=True)
    print(redact(traceback.format_exc(), max_length=4000), flush=True)


def _finalize(run_id, finish, *args):
    """Store a final state; if that fails, try to mark the run failed, else raise."""
    try:
        finish(run_id, *args)
    except Exception as exc:
        _log_error(f"Could not persist final state for run {run_id}", exc)
        try:
            run_store.fail_run(run_id, SAFE_FAILURE_MESSAGE)
        except Exception as second:
            _log_error(f"Run {run_id} may be stuck in 'running'", second)
            raise PersistenceError(f"run {run_id} could not be finalized") from second
        raise PersistenceError(f"run {run_id} result could not be stored") from exc


def process_one(executor=None, allowed_scenarios=None):
    """
    Process at most one queued run from the allowed scenarios.

    Returns:
        True  - a run was processed.
        False - no eligible run was available.
    """
    if allowed_scenarios is None:
        allowed_scenarios = get_allowed_scenarios()

    if not allowed_scenarios:
        raise ValueError(
            "An explicit allowed_scenarios list is required."
        )

    run = run_store.claim_next_run(
        allowed_scenarios=allowed_scenarios
    )

    if run is None:
        return False

    if executor is None:
        executor = run_investigation

    run_id = run["run_id"]
    scenario_id = run["scenario_id"]

    try:
        result = executor(scenario_id)

    except Exception as exc:
        _log_error(f"Investigation error for run {run_id}", exc)
        _finalize(run_id, run_store.fail_run, SAFE_FAILURE_MESSAGE)
        print(f"Run {run_id} marked failed.", flush=True)
        return True

    # An environment failure means no verdict exists; it must not be stored as completed.
    investigation = result.get("investigation") if isinstance(result, dict) else None
    if not isinstance(investigation, dict) or investigation.get("verdict") in (None, "env_failure"):
        _finalize(run_id, run_store.fail_run, ENVIRONMENT_FAILURE_MESSAGE)
        print(f"Run {run_id} marked failed (environment failure).", flush=True)
        return True

    _finalize(run_id, run_store.complete_run, result)

    print(
        f"Run {run_id} completed.",
        flush=True,
    )
    return True


def main():
    allowed = get_allowed_scenarios()

    # Production must never start without an explicit allowlist.
    if not allowed:
        raise SystemExit(
            "Refusing to start without WORKER_SCENARIO_IDS."
        )

    # Every investigation creates a billable Celesto computer.
    if os.environ.get("WORKER_CONFIRM_CLOUD") != "yes":
        raise SystemExit(
            "Refusing to start: set WORKER_CONFIRM_CLOUD=yes to allow billable "
            "Celesto computers."
        )

    max_runs_text = os.environ.get("WORKER_MAX_RUNS", "1")

    try:
        max_runs = int(max_runs_text)
    except ValueError:
        raise SystemExit(
            "WORKER_MAX_RUNS must be a positive integer."
        )

    if max_runs < 1:
        raise SystemExit(
            "WORKER_MAX_RUNS must be a positive integer."
        )

    run_store.apply_migrations()

    print(
        f"Worker started. Allowed scenarios: {allowed}; "
        f"maximum runs: {max_runs}",
        flush=True,
    )

    processed = 0

    while processed < max_runs:
        try:
            did_process = process_one(
                allowed_scenarios=allowed
            )

            if did_process:
                processed += 1
            else:
                time.sleep(POLL_INTERVAL_SECONDS)

        except PersistenceError as exc:
            # Do not keep allocating computers while results cannot be stored.
            _log_error("Stopping: persistence failure", exc)
            raise SystemExit(3)

        except Exception as exc:
            _log_error("Worker operation error", exc)
            time.sleep(POLL_INTERVAL_SECONDS)

    print(
        "Worker reached its run limit and is exiting.",
        flush=True,
    )


if __name__ == "__main__":
    main()
