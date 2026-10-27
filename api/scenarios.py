import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCENARIO_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,7}$")


def get_scenario(scenario_id):
    # Validate the type and shape BEFORE building any filesystem path.
    if not isinstance(scenario_id, str) or not SCENARIO_ID_PATTERN.fullmatch(scenario_id):
        raise ValueError("unknown scenario_id")

    oracle_path = ROOT / "oracle" / "labels.jsonl"
    fixture_path = ROOT / "fixtures" / scenario_id / "app.py"

    expected = None
    for line in oracle_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            if item.get("scenario_id") == scenario_id:
                expected = item
                break

    if expected is None or not fixture_path.is_file():
        raise ValueError("unknown scenario_id")
    return {"oracle": expected, "source": fixture_path.read_text(encoding="utf-8")}
