import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_json(path):
    with (ROOT / path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def test_required_files_exist():
    required = [
        "README.md",
        ".dockerignore",
        "problem.json",
        "capabilities.json",
        "lifecycle.json",
        "reliability.json",
        "containment.json",
        "failure_policy.json",
        "failure_trace.jsonl",
        "commands.jsonl",
        "concurrency.json",
        "postmortem.md",
        "app.py",
        "timefault.py",
    ]
    for name in required:
        assert (ROOT / name).exists(), f"Missing required file: {name}"


def test_dockerignore_includes_cloud_build_inputs():
    ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    for pattern in (
        "!requirements-cloud.txt",
        "!agent/",
        "!agent/**",
        "!fixtures/",
        "!fixtures/**",
        "!oracle/",
        "!oracle/**",
    ):
        assert pattern in ignored, pattern


def test_problem_json_schema():
    data = read_json("problem.json")
    assert len(data["who"]) >= 40
    assert len(data["agent_work"]) >= 40
    assert len(data["proof_output"]) >= 20
    assert data["idea_source"] in {"idea_bank", "original"}


def test_capabilities_schema():
    caps = read_json("capabilities.json")
    assert len(caps) >= 2
    ids = {item["id"] for item in caps}
    assert len(ids) >= 2
    for item in caps:
        assert len(item["why"]) >= 80
        assert (ROOT / item["evidence_path"]).exists()


def test_lifecycle_schema():
    data = read_json("lifecycle.json")
    assert isinstance(data["sandbox_names"], list)
    assert data["sandbox_names"]


def test_reliability_schema():
    data = read_json("reliability.json")
    assert data["run_count"] == len(data["runs"])
    wall = sorted(data["wall_clock_s"])
    assert wall == data["wall_clock_s"]
    assert data["success_rate"] == round(sum(1 for r in data["runs"] if r["success"]) / data["run_count"], 2)
    assert len({r["sandbox_name"] for r in data["runs"]}) == data["run_count"]


def test_failure_policy_and_trace():
    policy = read_json("failure_policy.json")
    assert policy["failed_step"] == 7
    assert policy["total_steps"] == 10
    assert policy["policy"] in {"resume", "rollback", "fresh"}
    with (ROOT / "failure_trace.jsonl").open("r", encoding="utf-8") as fh:
        lines = [json.loads(line) for line in fh if line.strip()]
    assert any(item.get("event") == "policy_applied" and item.get("policy") == policy["policy"] for item in lines)


def test_commands_jsonl():
    with (ROOT / "commands.jsonl").open("r", encoding="utf-8") as fh:
        lines = [json.loads(line) for line in fh if line.strip()]
    assert all(item["decision"] in {"allow", "block"} for item in lines)
    assert all(item["execution_target"] == "celesto_sandbox" for item in lines)
    assert all(item["sandbox_name"].startswith("sbx-") for item in lines)


def test_api_endpoints(monkeypatch):
    import app
    from fastapi.testclient import TestClient

    monkeypatch.setattr(app, "RUNS", list(app.RUNS))
    client = TestClient(app.app)
    assert client.get("/health").status_code == 200
    j = client.get("/api/runs")
    assert j.status_code == 200
    body = j.json()
    assert any(run["sandbox_name"] == "sbx-seeddemo1" for run in body)
    resp = client.post("/api/runs", json={"run_id": "demo-002", "sandbox_name": "sbx-demo2", "problem_id": "CF-02", "state": "ready", "execution_target": "celesto_sandbox"})
    assert resp.status_code == 201
    bad = client.post("/api/runs", json={"run_id": "demo-bad", "sandbox_name": "bad-name", "problem_id": "CF-02", "state": "ready", "execution_target": "celesto_sandbox"})
    assert bad.status_code == 422


def test_benchmark_ledger_appends_and_creates_parent(tmp_path):
    from agent.run_benchmark import append_jsonl_record

    path = tmp_path / "reports" / "benchmark_results.jsonl"
    append_jsonl_record(path, {"run_id": "run-1"})
    append_jsonl_record(path, {"run_id": "run-2"})

    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [record["run_id"] for record in records] == ["run-1", "run-2"]


def test_json_report_backs_up_existing_file(tmp_path):
    from agent.run_benchmark import write_json_report

    path = tmp_path / "reports" / "summary.json"
    write_json_report(path, {"run_count": 1})
    write_json_report(path, {"run_count": 2})

    backups = list(path.parent.glob("summary.json.backup-*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == {"run_count": 1}
    assert json.loads(path.read_text(encoding="utf-8")) == {"run_count": 2}


def test_reconstructed_temporal_fixture_boundaries():
    from agent.run_local_fixtures import run_fixture

    clean = run_fixture("C01", "2028-02-29")
    assert clean["exit_code"] == 0

    expiry_before = run_fixture("E01", "2028-05-31")
    expiry_day = run_fixture("E01", "2028-06-01")
    expiry_after = run_fixture("E01", "2028-06-02")
    assert [expiry_before["exit_code"], expiry_day["exit_code"], expiry_after["exit_code"]] == [0, 1, 0]

    overflow_before = run_fixture("E02", "2038-01-18")
    overflow_at_boundary = run_fixture("E02", "2038-01-19")
    assert [overflow_before["exit_code"], overflow_at_boundary["exit_code"]] == [0, 1]

    leap_day = run_fixture("L01", "2028-02-29")
    assert leap_day["exit_code"] != 0


def test_reconstructed_fixture_oracle_line_and_boundary_evaluation():
    from agent.run_local_fixtures import evaluate_scenario, load_oracle

    oracle = load_oracle(ROOT / "oracle" / "labels.jsonl")
    assert oracle["L01"]["bug_line"] == 5
    assert oracle["C01"]["bug_line"] is None
    assert oracle["C01"]["window"] is None

    for scenario_id, record in oracle.items():
        source = ROOT / "fixtures" / scenario_id / record["bug_file"] if record["bug_file"] else None
        if source is not None:
            marked_lines = [
                number
                for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), start=1)
                if "# BUG:" in line
            ]
            assert record["bug_line"] in marked_lines, scenario_id

    for scenario_id in ("C01", "E01", "E02", "L01", "L02", "L03", "M01", "M02", "M03", "M04"):
        result = evaluate_scenario(scenario_id, oracle[scenario_id])
        assert result["boundary_checks_match"], scenario_id
        assert result["execution_mode"] == "local_python_clock_patch"

    unassessed = evaluate_scenario("F04", oracle["F04"])
    assert unassessed["boundary_checks_match"] is None
    assert unassessed["classification"] == "not_assessed_locally"


def test_local_oracle_rejects_malformed_windows(tmp_path):
    from agent.run_local_fixtures import load_oracle

    path = tmp_path / "labels.jsonl"
    path.write_text(
        json.dumps(
            {
                "scenario_id": "E99",
                "expected_label": "date_bug",
                "window": ["not-a-date", "2038-01-19"],
            }
        ),
        encoding="utf-8",
    )
    try:
        load_oracle(path)
    except ValueError as exc:
        assert "invalid date window" in str(exc)
    else:
        raise AssertionError("malformed oracle window was accepted")


def test_local_fixture_output_is_confined_to_reports(tmp_path):
    from agent.run_local_fixtures import resolve_report_path

    reports_path = resolve_report_path(Path("reports") / "safe.jsonl")
    assert reports_path.parent == (ROOT / "reports").resolve()

    try:
        resolve_report_path(tmp_path / "outside.jsonl")
    except ValueError as exc:
        assert "inside the reports directory" in str(exc)
    else:
        raise AssertionError("evidence path outside reports was accepted")


def test_readme_headings():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    required = [
        "Problem statement",
        "How I used Celesto",
        "Eval report",
        "Containment test",
        "State and failure design",
        "Setup",
    ]
    for heading in required:
        assert heading in text


def test_celesto_adapter_uses_cloud_computer_sdk_and_cleans_up(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMEFAULT_CELESTO_TRANSPORT", "sdk")
    import sys
    from types import ModuleType, SimpleNamespace

    from agent import run_one

    class FakeCelestoError(Exception):
        pass

    class FakeCloudComputer:
        def __init__(self, *, lifetime, startup_timeout):
            assert lifetime == "ephemeral"
            assert startup_timeout == 90
            self.id = "computer-1"
            self.deleted = False
            self.commands = []

        def start(self):
            return self

        def run(self, command, timeout):
            self.commands.append((command, timeout))
            return SimpleNamespace(exit_code=0, stdout="ok\n", stderr="")

        def delete(self):
            self.deleted = True

    sdk_module = ModuleType("celesto")
    sdk_module.__path__ = []
    sdk_module.CloudComputer = FakeCloudComputer
    exceptions_module = ModuleType("celesto.exceptions")
    exceptions_module.CelestoError = FakeCelestoError
    monkeypatch.setitem(sys.modules, "celesto", sdk_module)
    monkeypatch.setitem(sys.modules, "celesto.exceptions", exceptions_module)
    monkeypatch.setattr(run_one, "COMMAND_LOG", tmp_path / "commands.jsonl")
    monkeypatch.setattr(run_one, "COMPUTERS", {})

    created = run_one.cli(["create", "--boot-timeout", "90"])
    assert created == {"ok": True, "data": {"computer_id": "computer-1"}}

    executed = run_one.cli(["exec", "computer-1", "--", "sh", "-c", "echo ok"])
    assert executed["data"]["exit_code"] == 0
    assert executed["data"]["stdout"] == "ok\n"
    computer = run_one.COMPUTERS["computer-1"]
    assert computer.commands == [("sh -c 'echo ok'", 300)]

    deleted = run_one.cli(["delete", "computer-1"])
    assert deleted["ok"]
    assert computer.deleted
    assert run_one.COMPUTERS == {}


def test_celesto_adapter_blocks_dangerous_exec_without_loading_sdk():
    from agent import run_one

    for command in ("rm -rf /", "mkfs.ext4 /dev/sda", ":(){ :|:&;};:"):
        blocked = run_one.cli(["exec", "computer-1", "--", "sh", "-c", command])
        assert blocked["blocked"], command
        assert blocked["error"]["type"] == "CommandBlockedError"


def test_planner_reports_missing_llm_configuration_as_fallback(monkeypatch):
    from agent import investigate

    monkeypatch.setattr(investigate, "load_env", lambda: {})
    plan = investigate.llm_plan("from datetime import date\nprint(date.today())")
    assert plan["fallback"]
    assert plan["suspect_line"] is None
    assert "not configured" in plan["reason"]


def test_benchmark_assigns_five_distinct_sandbox_labels(monkeypatch):
    from agent import run_benchmark

    monkeypatch.setattr(run_benchmark, "USED_SANDBOX_NAMES", set())
    names = [run_benchmark.unique_sandbox_name() for _ in range(5)]
    assert len(set(names)) == 5
    assert all(name.startswith("sbx-") for name in names)


def test_benchmark_repeat_selection_is_bounded_and_validated():
    from agent.run_benchmark import select_scenarios

    assert select_scenarios(["C01", "C02"], "C02", 5) == ["C02"] * 5
    try:
        select_scenarios(["C01", "C02", "C03"], "", 7)
    except ValueError as exc:
        assert "maximum bounded run count" in str(exc)
    else:
        raise AssertionError("benchmark exceeded the 20-run cap")

    try:
        select_scenarios(["C01", "C02"], "C99", 1)
    except ValueError as exc:
        assert "unknown scenario IDs" in str(exc)
    else:
        raise AssertionError("unknown scenario was accepted")


def test_benchmark_summary_path_must_be_new_and_confined_to_reports(tmp_path):
    from agent.run_benchmark import resolve_summary_path

    destination = resolve_summary_path(Path("reports") / f"{tmp_path.name}.json")
    assert destination.parent == (ROOT / "reports").resolve()

    for output, message in (
        (tmp_path / "outside.json", "inside the reports directory"),
        (Path("reports") / "benchmark_results.jsonl", "already exists"),
    ):
        try:
            resolve_summary_path(output)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError(f"unsafe summary path was accepted: {output}")


def test_benchmark_guest_setup_is_fail_fast_and_replay_uses_uploaded_fixture():
    from agent import run_benchmark

    assert "set -eu" in run_benchmark.INSTALL
    assert "command -v faketime" in run_benchmark.INSTALL
    replay = run_benchmark.replay_command("2028-06-01")
    assert "/work/app.py" in replay
    assert "/fixtures/" not in replay


def test_guest_command_is_not_replayed_after_uncertain_error(monkeypatch):
    from agent import investigate

    calls = []
    audit_calls = []
    adapter = investigate.R
    monkeypatch.setattr(adapter, "MAP", {"sbx-test": "computer-1"})
    monkeypatch.setattr(adapter, "audit", lambda *args: audit_calls.append(args))
    monkeypatch.setattr(
        adapter,
        "cli",
        lambda args: calls.append(args) or {
            "ok": False,
            "error": {"type": "CelestoError", "message": "outcome may be unknown"},
        },
    )

    result = investigate.gexec("sbx-test", "python3 /work/app.py")
    assert result["env_error"]
    assert result["err"] == "outcome may be unknown"
    assert len(calls) == 1
    assert len(audit_calls) == 1


def test_preflight_docker_checks_use_only_network_isolated_local_commands(monkeypatch):
    from agent import preflight

    commands = []
    monkeypatch.setattr(preflight.shutil, "which", lambda name: "docker" if name == "docker" else None)

    def command_result(command, timeout=30):
        commands.append(command)
        if command[:3] == ["docker", "info", "--format"]:
            return True, "linux"
        if command[:3] == ["docker", "image", "inspect"]:
            return True, "sha256:local-image-id"
        if "--entrypoint" in command:
            return True, ""
        if command[0:2] == ["docker", "run"]:
            return True, ""
        raise AssertionError(command)

    monkeypatch.setattr(preflight, "_command_result", command_result)
    result = preflight._docker_check("timefault-ai:test")

    assert all(
        result[name]["ok"]
        for name in ("docker_engine", "docker_image", "docker_sdk", "docker_cli")
    )
    docker_runs = [command for command in commands if command[:2] == ["docker", "run"]]
    assert len(docker_runs) == 2
    assert all("--network" in command and "none" in command for command in docker_runs)
    assert not any(
        any(token in {"create", "start", "CELESTO_API_KEY"} for token in command)
        for command in commands
    )


def test_preflight_configuration_only_exposes_presence_flags(monkeypatch, tmp_path):
    from agent import preflight

    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    for name in ("CELESTO_API_KEY", "LLM_API_KEY", "OPENAI_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "CELESTO_API_KEY=secret-test-value\n"
        "LLM_API_KEY=llm-test-value\n"
        "LLM_MODEL=test-model\n",
        encoding="utf-8",
    )

    _, configured = preflight._configuration()

    assert configured == {
        "CELESTO_API_KEY": True,
        "LLM_API_KEY": True,
        "LLM_MODEL": True,
    }


def test_preflight_docker_configuration_matches_env_file_transport(monkeypatch, tmp_path):
    from agent import preflight

    monkeypatch.setattr(preflight, "ROOT", tmp_path)
    monkeypatch.setenv("CELESTO_API_KEY", "host-only-test-value")
    monkeypatch.setenv("LLM_API_KEY", "host-only-test-value")
    monkeypatch.setenv("LLM_MODEL", "host-only-test-model")
    (tmp_path / ".env").write_text("", encoding="utf-8")

    _, host_configuration = preflight._configuration()
    _, docker_configuration = preflight._configuration(docker_environment=True)

    assert all(host_configuration.values())
    assert not any(docker_configuration.values())
