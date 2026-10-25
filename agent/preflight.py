"""Check cloud-runner prerequisites without allocating a Celesto computer."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMAGE = "timefault-ai:cloud-runner"
REQUIRED_CONFIGURATION = ("CELESTO_API_KEY", "LLM_MODEL")


def _configuration(docker_environment: bool = False) -> tuple[dict[str, str], dict[str, bool]]:
    values = {} if docker_environment else dict(os.environ)
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            name, value = stripped.split("=", 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            values.setdefault(name.strip(), value)

    keys = {
        "CELESTO_API_KEY": bool(values.get("CELESTO_API_KEY", "").strip()),
        "LLM_API_KEY": bool(
            values.get("LLM_API_KEY", "").strip()
            or values.get("OPENAI_API_KEY", "").strip()
        ),
    }
    keys["LLM_MODEL"] = bool(values.get("LLM_MODEL", "").strip())
    return values, keys


def _command_result(command: list[str], timeout: int = 30) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except OSError as exc:
        return False, type(exc).__name__
    if result.returncode:
        return False, f"exit code {result.returncode}"
    return True, (result.stdout or "").strip()


def _host_sdk_check() -> tuple[bool, str]:
    try:
        from celesto import CloudComputer
    except (ImportError, AttributeError) as exc:
        return False, f"{type(exc).__name__}: Celesto CloudComputer import failed"
    if not callable(CloudComputer):
        return False, "Celesto CloudComputer is not callable"
    try:
        importlib.metadata.version("celesto-core")
    except importlib.metadata.PackageNotFoundError:
        return False, "celesto-core is not installed in this Python environment"
    return True, "Celesto SDK and celesto-core are importable"


def _host_cli_check() -> tuple[bool, str]:
    executable = shutil.which("celesto")
    if executable is None:
        candidates = (
            Path(sys.prefix) / "Scripts" / "celesto.exe",
            Path(sys.prefix) / "bin" / "celesto",
        )
        executable = next((str(path) for path in candidates if path.is_file()), None)
    if executable is None:
        return False, "celesto CLI executable is not on PATH or in this Python environment"
    ok, detail = _command_result([executable, "--help"], timeout=15)
    return ok, "celesto --help succeeded" if ok else f"celesto --help failed ({detail})"


def _docker_check(image: str) -> dict[str, dict[str, Any]]:
    if shutil.which("docker") is None:
        failed = {"ok": False, "detail": "docker executable is not on PATH"}
        return {"docker_engine": failed, "docker_image": failed.copy(),
                "docker_sdk": failed.copy(), "docker_cli": failed.copy()}

    engine_ok, engine_type = _command_result(
        ["docker", "info", "--format", "{{.OSType}}"], timeout=20
    )
    engine = {
        "ok": engine_ok and engine_type == "linux",
        "detail": f"Linux engine available ({engine_type})"
        if engine_ok and engine_type == "linux"
        else f"Linux Docker engine unavailable ({engine_type})",
    }
    if not engine["ok"]:
        failed = {"ok": False, "detail": "not checked because Docker engine is unavailable"}
        return {"docker_engine": engine, "docker_image": failed.copy(),
                "docker_sdk": failed.copy(), "docker_cli": failed.copy()}

    image_ok, image_detail = _command_result(
        ["docker", "image", "inspect", image, "--format", "{{.Id}}"], timeout=20
    )
    image_check = {
        "ok": image_ok,
        "detail": "cloud-runner image is available"
        if image_ok
        else f"cloud-runner image is unavailable ({image_detail})",
    }
    if not image_ok:
        failed = {"ok": False, "detail": "not checked because the image is unavailable"}
        return {"docker_engine": engine, "docker_image": image_check,
                "docker_sdk": failed.copy(), "docker_cli": failed.copy()}

    sdk_ok, sdk_detail = _command_result(
        [
            "docker", "run", "--rm", "--network", "none",
            "--entrypoint", "python", image, "-c",
            "from celesto import CloudComputer; "
            "import importlib.metadata; "
            "importlib.metadata.version('celesto-core'); "
            "assert callable(CloudComputer)",
        ],
        timeout=45,
    )
    cli_ok, cli_detail = _command_result(
        ["docker", "run", "--rm", "--network", "none", image, "celesto", "--help"],
        timeout=90,
    )
    return {
        "docker_engine": engine,
        "docker_image": image_check,
        "docker_sdk": {
            "ok": sdk_ok,
            "detail": "Celesto SDK/core import succeeded in Linux image"
            if sdk_ok else f"Celesto SDK/core import failed in Linux image ({sdk_detail})",
        },
        "docker_cli": {
            "ok": cli_ok,
            "detail": "celesto --help succeeded in Linux image"
            if cli_ok else f"celesto --help failed in Linux image ({cli_detail})",
        },
    }


def _fixture_check() -> tuple[bool, str]:
    oracle_path = ROOT / "oracle" / "labels.jsonl"
    try:
        scenario_ids = [
            json.loads(line)["scenario_id"]
            for line in oracle_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError as exc:
        return False, f"oracle file unavailable ({type(exc).__name__})"
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        return False, f"oracle file is malformed ({type(exc).__name__})"
    if not scenario_ids:
        return False, "oracle has no scenarios"
    missing = [
        scenario_id for scenario_id in scenario_ids
        if not (ROOT / "fixtures" / scenario_id / "app.py").is_file()
    ]
    if missing:
        return False, "missing fixture app.py for " + ", ".join(missing)
    return True, f"{len(scenario_ids)} oracle scenarios have fixture files"


def _report_paths_check() -> tuple[bool, str]:
    reports = ROOT / "reports"
    evidence = reports / "evidence"
    if not reports.is_dir() or not evidence.is_dir():
        return False, "reports and reports/evidence directories must already exist"
    if not os.access(reports, os.W_OK) or not os.access(evidence, os.W_OK):
        return False, "reports or reports/evidence is not writable"
    ledger = reports / "benchmark_results.jsonl"
    if ledger.exists() and not os.access(ledger, os.W_OK):
        return False, "benchmark ledger exists but is not writable"
    return True, "existing report paths are writable; no files were changed"


def run_preflight(image: str = DEFAULT_IMAGE) -> dict[str, Any]:
    """Return prerequisite results; this function never calls the allocation API."""
    checks: dict[str, Any] = {
        "host_sdk": dict(zip(("ok", "detail"), _host_sdk_check())),
        "host_cli": dict(zip(("ok", "detail"), _host_cli_check())),
        "fixtures": dict(zip(("ok", "detail"), _fixture_check())),
        "report_paths": dict(zip(("ok", "detail"), _report_paths_check())),
    }
    checks.update(_docker_check(image))
    docker_ready = all(checks[name]["ok"] for name in (
        "docker_engine", "docker_image", "docker_sdk", "docker_cli"
    ))
    host_ready = checks["host_sdk"]["ok"] and checks["host_cli"]["ok"]
    _, configured = _configuration(docker_environment=docker_ready)
    config_ok = all(configured[name] for name in REQUIRED_CONFIGURATION) and configured["LLM_API_KEY"]
    config_detail = {
        "CELESTO_API_KEY": configured["CELESTO_API_KEY"],
        "LLM_API_KEY": configured["LLM_API_KEY"],
        "LLM_MODEL": configured["LLM_MODEL"],
        "source": ".env passed by Docker --env-file"
        if docker_ready else "process environment or .env",
        "detail": "presence only; values are never displayed",
    }
    checks["configuration"] = {"ok": config_ok, **config_detail}
    checks["sandbox_allocation"] = {
        "ok": True,
        "detail": "not attempted; preflight does not call Celesto create/start",
    }
    ready = config_ok and checks["fixtures"]["ok"] and checks["report_paths"]["ok"] and (
        docker_ready or host_ready
    )
    return {"ready": ready, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default=os.environ.get("TIMEFAULT_CLOUD_IMAGE", DEFAULT_IMAGE))
    args = parser.parse_args()
    result = run_preflight(args.image)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
