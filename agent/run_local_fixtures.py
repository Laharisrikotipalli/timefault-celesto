import argparse
import contextlib
import datetime as datetime_module
import io
import json
import os
import re
import runpy
import time as time_module
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
REPORTS_ROOT = (ROOT / "reports").resolve()
DATE_BUG_SCENARIOS = ("L01", "L02", "L03", "M01", "M02", "M03", "M04", "E01", "E02")


def run_fixture(scenario_id, simulated_date):
    fixture = ROOT / "fixtures" / scenario_id / "app.py"
    target = datetime_module.date.fromisoformat(simulated_date)
    epoch = datetime_module.datetime.combine(
        target, datetime_module.time(12), tzinfo=datetime_module.timezone.utc
    ).timestamp()

    class FrozenDate(datetime_module.date):
        @classmethod
        def today(cls):
            return cls(target.year, target.month, target.day)

    class FrozenDateTime(datetime_module.datetime):
        @classmethod
        def now(cls, tz=None):
            value = cls(target.year, target.month, target.day, 12)
            return value.replace(tzinfo=tz) if tz is not None else value

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = 0
    error_type = None
    with (
        patch.object(datetime_module, "date", FrozenDate),
        patch.object(datetime_module, "datetime", FrozenDateTime),
        patch.object(time_module, "time", return_value=epoch),
        patch.dict(os.environ, {"REQUIRED_API_URL": "https://dummy.invalid"}),
        contextlib.redirect_stdout(stdout),
        contextlib.redirect_stderr(stderr),
    ):
        try:
            runpy.run_path(str(fixture), run_name="__main__")
        except SystemExit as exc:
            exit_code = exc.code if isinstance(exc.code, int) else int(exc.code is not None)
            error_type = "SystemExit" if exit_code else None
        except Exception as exc:
            exit_code = 1
            error_type = type(exc).__name__

    return {
        "simulated_date": simulated_date,
        "exit_code": exit_code,
        "error_type": error_type,
        "stdout": stdout.getvalue(),
        "stderr": stderr.getvalue(),
    }


def _sample_dates(scenario_id, oracle_record):
    if scenario_id == "C01":
        return ["2028-02-28", "2028-02-29", "2028-03-01"]

    window = oracle_record.get("window")
    if not window:
        return ["2027-06-15", "2028-02-29"]

    first = datetime_module.date.fromisoformat(window[0])
    last = datetime_module.date.fromisoformat(window[1])
    samples = {(first - datetime_module.timedelta(days=1)).isoformat(), first.isoformat(), last.isoformat()}
    if window[1] != "2200-12-31":
        samples.add((last + datetime_module.timedelta(days=1)).isoformat())
    return sorted(samples)


def evaluate_scenario(scenario_id, oracle_record):
    dates = _sample_dates(scenario_id, oracle_record)
    observations = [run_fixture(scenario_id, day) for day in dates]
    expected_label = oracle_record["expected_label"]
    if expected_label == "clean":
        matches = all(item["exit_code"] == 0 for item in observations)
    elif expected_label == "date_bug":
        window = oracle_record["window"]
        by_date = {item["simulated_date"]: item["exit_code"] for item in observations}
        matches = (
            by_date[window[0]] != 0
            and by_date[window[1]] != 0
            and by_date[dates[0]] == 0
            and (
                window[1] == "2200-12-31"
                or by_date[dates[-1]] == 0
            )
        )
    else:
        matches = None

    return {
        "run_id": f"local-{uuid.uuid4().hex}",
        "scenario_id": scenario_id,
        "execution_mode": "local_python_clock_patch",
        "expected_label": expected_label,
        "boundary_checks_match": matches,
        "classification": "not_assessed_locally" if matches is None else "boundary_checks",
        "observations": observations,
    }


def load_oracle(path):
    records = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            scenario_id = record["scenario_id"]
            label = record["expected_label"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError(f"invalid oracle record on line {line_number}") from exc
        if (
            not isinstance(scenario_id, str)
            or not re.fullmatch(r"[A-Z][A-Z0-9]{1,7}", scenario_id)
            or scenario_id in records
            or not isinstance(label, str)
            or label not in {"clean", "date_bug", "not_date_bug"}
        ):
            raise ValueError(f"duplicate scenario or unsupported label on line {line_number}")
        window = record.get("window")
        if label == "date_bug":
            if not isinstance(window, list) or len(window) != 2:
                raise ValueError(f"invalid date window on line {line_number}")
            try:
                bounds = [datetime_module.date.fromisoformat(item) for item in window]
            except (TypeError, ValueError) as exc:
                raise ValueError(f"invalid date window on line {line_number}") from exc
            if any(bound.isoformat() != item for bound, item in zip(bounds, window)) or bounds[0] > bounds[1]:
                raise ValueError(f"invalid date window on line {line_number}")
        elif window is not None:
            raise ValueError(f"unexpected date window on line {line_number}")
        bug_line = record.get("bug_line")
        bug_file = record.get("bug_file")
        if (bug_line is None) != (bug_file is None):
            raise ValueError(f"invalid source attribution on line {line_number}")
        if bug_line is not None and (
            not isinstance(bug_line, int)
            or isinstance(bug_line, bool)
            or bug_line < 1
            or bug_file != "app.py"
        ):
            raise ValueError(f"invalid source attribution on line {line_number}")
        records[scenario_id] = record
    if not records:
        raise ValueError("oracle contains no scenario records")
    return records


def resolve_report_path(output):
    candidate = output if output.is_absolute() else ROOT / output
    resolved = candidate.resolve()
    try:
        resolved.relative_to(REPORTS_ROOT)
    except ValueError as exc:
        raise ValueError("evidence output must remain inside the reports directory") from exc
    return resolved


def main():
    parser = argparse.ArgumentParser(description="Run fixtures locally with an injected Python clock.")
    parser.add_argument("--only", default=",".join(DATE_BUG_SCENARIOS + ("C01",)))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        oracle = load_oracle(ROOT / "oracle" / "labels.jsonl")
    except (OSError, ValueError) as exc:
        print(f"local fixture preflight failed: {exc}")
        return 2

    scenario_ids = [item for item in args.only.split(",") if item]
    missing = [
        sid for sid in scenario_ids
        if sid not in oracle or not (ROOT / "fixtures" / sid / "app.py").is_file()
    ]
    if missing:
        print("local fixture preflight failed: missing scenario source/oracle for " + ", ".join(missing))
        return 2

    results = [evaluate_scenario(sid, oracle[sid]) for sid in scenario_ids]
    for result in results:
        print(
            result["scenario_id"],
            "UNASSESSED"
            if result["boundary_checks_match"] is None
            else "PASS"
            if result["boundary_checks_match"]
            else "FAIL",
            f"({len(result['observations'])} local simulated dates)",
        )
    if args.output:
        try:
            output_path = resolve_report_path(args.output)
        except ValueError as exc:
            print(f"local fixture output rejected: {exc}")
            return 2
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8") as handle:
            for result in results:
                handle.write(json.dumps(result, sort_keys=True) + "\n")
    if any(result["boundary_checks_match"] is None for result in results):
        return 2
    return 0 if all(result["boundary_checks_match"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
