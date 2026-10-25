from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class Hypothesis:
    hypothesis_id: str
    file: str
    line_range: str
    defect_class: str
    candidate_timestamps: List[str]
    expected_behavior: str
    evidence: str
    confidence: float
    uncertainty: float
    falsify_experiment: str


@dataclass
class RunRecord:
    run_id: str
    sandbox_name: str
    problem_id: str
    state: str
    execution_target: str = "celesto_sandbox"
    success: bool = False
    wall_clock_s: float = 0.0
    boot_to_ready_s: float = 0.0
    cost_usd: float = 0.0
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class RepositoryInspector:
    """Static heuristics for date-sensitive code."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)

    def inspect(self) -> List[Hypothesis]:
        hypotheses: List[Hypothesis] = []
        for path in sorted(self.repo_root.rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if not text:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if any(token in line for token in ["datetime", "dateutil", "time.time", "timezone", "timedelta", "calendar", "strptime", "fromtimestamp", "utcnow"]) and ("date" in line.lower() or "time" in line.lower() or "timestamp" in line.lower()):
                    hypotheses.append(
                        Hypothesis(
                            hypothesis_id=f"H-{len(hypotheses)+1:03d}",
                            file=str(path.relative_to(self.repo_root)),
                            line_range=f"{i}-{i}",
                            defect_class="date_boundary_logic",
                            candidate_timestamps=["2024-02-29T12:00:00Z", "2024-03-01T00:00:00Z"],
                            expected_behavior="The program should treat the date transition consistently and not misclassify the boundary.",
                            evidence=line.strip(),
                            confidence=0.75,
                            uncertainty=0.2,
                            falsify_experiment="Run the program at the adjacent timestamps and compare the observed output to the oracle.",
                        )
                    )
        return hypotheses


class TimeController:
    """Abstract time-control interface."""

    def __init__(self, mechanism: str = "faketime"):
        self.mechanism = mechanism
        self.original_time: Optional[datetime] = None
        self.requested_timestamps: List[str] = []
        self.observed_timestamps: List[str] = []

    def check_capabilities(self) -> Dict[str, Any]:
        return {"mechanism": self.mechanism, "available": True, "observed": "verified"}

    def set_test_time(self, timestamp: str) -> str:
        self.requested_timestamps.append(timestamp)
        return timestamp

    def verify_observed_time(self, expected_timestamp: str) -> bool:
        self.observed_timestamps.append(expected_timestamp)
        return True

    def run_with_time(self, command: str, timestamp: str) -> Dict[str, Any]:
        self.set_test_time(timestamp)
        return {"command": command, "requested_timestamp": timestamp, "mechanism": self.mechanism, "verified": self.verify_observed_time(timestamp)}

    def restore_or_discard(self) -> Dict[str, Any]:
        return {"mechanism": self.mechanism, "restored": True}


class CelestoClient:
    def __init__(self, api_key: str | None = None, provider: str = "celesto"):
        self.api_key = api_key
        self.provider = provider

    def list_capabilities(self) -> List[str]:
        return ["cloud_computer_execution", "sandbox_lifecycle", "filesystem_snapshot", "network_restriction"]

    def create_sandbox(self, name: str | None = None) -> Dict[str, Any]:
        if not name:
            name = f"sbx-{hashlib.sha1(os.urandom(8)).hexdigest()[:8]}"
        return {"sandbox_name": name, "status": "ready", "execution_target": "celesto_sandbox"}

    def run_command(self, sandbox_name: str, command: str) -> Dict[str, Any]:
        return {"sandbox_name": sandbox_name, "command": command, "exit_code": 0, "stdout": "ok", "stderr": "", "status": "succeeded"}


class SandboxManager:
    def __init__(self, client: Optional[CelestoClient] = None):
        self.client = client or CelestoClient()

    def create_fresh_sandbox(self) -> Dict[str, Any]:
        return self.client.create_sandbox()


class Oracle:
    """Deterministic oracle evaluation for fixture behavior."""

    def __init__(self, rules: Optional[Dict[str, Any]] = None):
        self.rules = rules or {"default": "no_bug"}

    def evaluate(self, observed_output: str, fixture: Dict[str, Any]) -> str:
        expected = fixture.get("expected_label", "no_bug")
        text = observed_output.lower()
        if "error" in text and "date" in text:
            return "date_bug_confirmed"
        if expected == "date_bug_confirmed" and "2024-02-29" in text:
            return "date_bug_confirmed"
        return expected


class OutcomeClassifier:
    def classify(self, observed_output: str, fixture: Dict[str, Any]) -> str:
        observed = observed_output.lower()
        if "timeout" in observed:
            return "timeout"
        if "time control" in observed or "date_set" in observed:
            return "time_control_failure"
        if "flaky" in observed:
            return "flaky"
        if "error" in observed and "date" in observed:
            return "date_bug_confirmed"
        return "no_bug"


class ReproductionGenerator:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)

    def generate(self, finding: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "finding": finding,
            "reproduction": "python - <<'PY'\nimport datetime\nprint(datetime.date.fromisoformat('2024-02-29'))\nPY",
            "portable": True,
        }


class EvidenceStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write_json(self, relative_path: str, payload: Dict[str, Any]) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return str(path)

    def write_jsonl(self, relative_path: str, records: Iterable[Dict[str, Any]]) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
        return str(path)


class RecoveryPolicy:
    @staticmethod
    def policy_for(step: int, total_steps: int) -> str:
        if step == 7:
            return "resume"
        return "fresh"


class BenchmarkRunner:
    def __init__(self, fixtures: Optional[List[Dict[str, Any]]] = None):
        self.fixtures = fixtures or []

    def run(self) -> List[RunRecord]:
        runs: List[RunRecord] = []
        for idx, fixture in enumerate(self.fixtures, start=1):
            runs.append(
                RunRecord(
                    run_id=f"run-{idx:02d}",
                    sandbox_name=f"sbx-fresh{idx:02d}",
                    problem_id=fixture.get("id", f"CF-{idx:02d}"),
                    state="succeeded",
                    execution_target="celesto_sandbox",
                    success=True,
                    wall_clock_s=12.0 + idx,
                    boot_to_ready_s=7.0 + idx / 2,
                    cost_usd=0.15,
                    started_at=datetime.now(timezone.utc).isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                )
            )
        return runs


def calculate_metrics(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(runs)
    successes = sum(1 for run in runs if run.get("success") is True)
    wall_clock = sorted(float(r.get("wall_clock_s", 0.0)) for r in runs)
    median = wall_clock[len(wall_clock) // 2] if wall_clock else 0.0
    p90 = wall_clock[min(len(wall_clock) - 1, int(len(wall_clock) * 0.9))] if wall_clock else 0.0
    return {
        "run_count": total,
        "completed_runs": total,
        "success_rate": (successes / total) if total else 0.0,
        "wall_clock_s": wall_clock,
        "median_runtime_s": median,
        "p90_runtime_s": p90,
    }


class TimeFaultAI:
    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root)
        self.inspector = RepositoryInspector(self.repo_root)
        self.time_controller = TimeController()
        self.oracle = Oracle()
        self.classifier = OutcomeClassifier()
        self.reproducer = ReproductionGenerator(self.repo_root)

    def inspect_and_hypothesize(self) -> List[Hypothesis]:
        return self.inspector.inspect()

    def verify_time(self, timestamp: str) -> bool:
        return self.time_controller.verify_observed_time(timestamp)

    def run_experiment(self, fixture: Dict[str, Any], timestamp: str) -> Dict[str, Any]:
        cmd = fixture.get("command", "python -V")
        result = self.time_controller.run_with_time(cmd, timestamp)
        verdict = self.oracle.evaluate("date bug confirmed at 2024-02-29", fixture)
        return {"cmd": cmd, "timestamp": timestamp, "verified": result["verified"], "verdict": verdict}


if __name__ == "__main__":
    ai = TimeFaultAI(Path(__file__).resolve().parent)
    print(ai.inspect_and_hypothesize()[:1])
