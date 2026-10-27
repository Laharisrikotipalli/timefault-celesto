import base64
import secrets
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from api.scenarios import get_scenario  # noqa: E402
from agent import investigate  # noqa: E402
from agent import policy  # noqa: E402
from agent import run_one  # noqa: E402

INSTALL = policy.INSTALL
PROBE = policy.PROBE


def _require_success(result, operation):
    if result.get("env_error") or result.get("blocked") or result.get("exit_code") != 0:
        raise RuntimeError(f"Celesto {operation} failed")


def run_investigation(scenario_id):
    # Validate the scenario locally before creating a Celesto computer.
    scenario = get_scenario(scenario_id)

    name = "run-" + secrets.token_hex(8)
    created = False
    computer_id = None
    failure = None
    result = None

    try:
        created_result = run_one.cli(["create", "--boot-timeout", "90"])
        computer_id = (created_result.get("data") or {}).get("computer_id")

        if computer_id:
            created = True
            run_one.MAP[name] = computer_id

        if not created_result.get("ok") or not computer_id:
            raise RuntimeError("Celesto computer creation failed")

        # Install the required runtime and prepare the working directory.
        _require_success(investigate.gexec(name, INSTALL), "runtime setup")

        # Verify that the remote environment can control its date.
        probe = investigate.gexec(name, PROBE)
        _require_success(probe, "date-control probe")
        if (probe.get("stdout") or "").strip() != policy.PROBE_DATE:
            raise RuntimeError("Celesto date-control probe returned an unexpected date")

        # Upload the selected scenario's source code.
        source = investigate.strip_hints(scenario["source"])
        encoded_source = base64.b64encode(source.encode()).decode()
        _require_success(
            investigate.gexec(name, policy.upload_command(encoded_source), label="upload fixture"),
            "fixture upload",
        )

        # Investigate the scenario and score it against its oracle.
        investigation = investigate.investigate(name, source)
        result = {
            "investigation": investigation,
            "score": investigate.score(scenario["oracle"], investigation),
        }

    except Exception as exc:
        failure = exc

    finally:
        # Attempt cleanup whenever a computer ID was returned.
        if created and computer_id:
            try:
                deleted = run_one.cli(["delete", computer_id], input_text="y\n")
                if not deleted.get("ok") and failure is None:
                    failure = RuntimeError("Celesto computer cleanup failed")
            except Exception:
                if failure is None:
                    failure = RuntimeError("Celesto computer cleanup failed")
            finally:
                run_one.MAP.pop(name, None)

    if failure is not None:
        raise failure

    return result
