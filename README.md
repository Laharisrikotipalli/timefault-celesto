# TimeFault AI

TimeFault AI aims to inspect date-sensitive code, discover failure windows, check verdicts against an independent oracle, and produce portable reproduction packages. The checked-in code is not yet a verified end-to-end implementation; see [Known limitations and future improvements](#known-limitations-and-future-improvements).

## Problem statement

Date-sensitive software fails in a narrow and often surprising window: leap-day transitions, month-end rollover, expiry logic, and timezone boundaries can all produce incorrect behavior. This project targets users who need trustworthy, reproducible temporal bug discovery in cloud execution environments.

## How I used Celesto

The intended architecture steps through a repository, inspects code for temporal logic, and executes candidate experiments in disposable Celesto sandboxes. `agent/run_one.py` now adapts the runner to Celesto's supported `CloudComputer` Python API. The checked-in `CelestoClient` and `TimeController` in `timefault.py` remain placeholders: they return canned responses and do not contact Celesto or verify the guest clock. The current API also creates metadata records only; it does not start an investigation.

Architecture diagram:

Code Repository → AI Planner → Celesto Cloud Computer → Oracle Evaluation → Finding and Reproduction Package

The intended design retains evidence and a run ledger alongside experiment output for auditability.

## Eval report

The checked-in `reliability.json` is not sufficient evidence of completed benchmark investigations. The runner appends JSONL ledger records, creates the report directory, and backs up JSON reports before replacing them. The adapter targets Celesto's supported `CloudComputer` SDK. The Windows venv still cannot import Celesto because it lacks the native `celesto-core` module; the Linux Docker image now builds with the dependency required by Celesto's package metadata, and the no-allocation preflight verifies SDK/core imports and `celesto --help` inside that image. Cloud execution remains blocked because Celesto and LLM credentials/model are not configured in `.env`. The latest two-scenario benchmark attempt recorded C02/E01 as environment failures before allocation; the records and per-run evidence are in `reports/benchmark_results.jsonl` and `reports/evidence/`. No cloud benchmark accuracy or confusion-matrix metric is claimed. `cost_usd` is a rough runner estimate at $0.015/hour after allocation, not provider billing data; failed preflight attempts are recorded at zero.

## Containment test

`containment.json` records a containment claim, but the checkout does not include repeatable adversarial tests demonstrating that claim. Treat containment as unverified. No real secrets or unrelated host files should be used in future tests; tests must use disposable resources and dummy credentials.

## State and failure design

The project includes a policy selector that returns `resume` for step 7 and a checked-in trace, but there is no executable recovery experiment comparing resume, rollback, and restart. The selector and trace are not evidence that recovery was measured.

## Setup

1. Copy `.env.example` to `.env`, replace the local database password placeholder with a private development password, and set `DATABASE_URL` to use that same password. Do not commit `.env`.
2. Install API dependencies with `pip install -r requirements.txt` or `pip install -e .`. The cloud runner additionally needs `pip install -r requirements-cloud.txt` on Python 3.11 or newer. Celesto's native wheel is available for Linux/macOS, not Windows; use the Docker image for Windows-hosted cloud runs unless you have the required Rust/MSVC build toolchain.
3. For cloud investigations, set `CELESTO_API_KEY`, `LLM_API_KEY`, and `LLM_MODEL` in `.env` (set `LLM_BASE_URL` only for a compatible custom endpoint). Keep credentials private. The adapter reads `.env` without printing its values.
4. Launch the API with `uvicorn app:app --host 0.0.0.0 --port 8080`.
5. Run validation with `pytest -q`.

### Cloud preflight

Before any benchmark, build the local Linux image and run the preflight:

```powershell
docker build --tag timefault-ai:cloud-runner --file Dockerfile .
.\.venv\Scripts\python.exe agent\preflight.py
```

The preflight checks Celesto SDK/core imports and `celesto --help` in the host and, when the image exists, in a network-isolated local container. It also checks credential presence (never prints values), Docker Linux-engine connectivity, fixture/oracle coverage, and existing report-path writability. It does not call the Celesto allocation API or modify reports. A passing preflight is required before a cloud run; it is not evidence that a cloud sandbox was started.

### Reproduction example

```bash
python - <<'PY'
import datetime
print(datetime.date.fromisoformat('2024-02-29'))
PY
```

### Related work note

TimeFault AI is informed by the wider practice of temporal testing, Chronofuzz, and libfaketime. Its intended contribution is to combine autonomous discovery, independent evaluation, and portable reproduction; this checkout does not claim measured results for that combination.

## How the agent selects experiments

The planner inspects temporal APIs and risky comparisons and chooses candidate timestamps. The cloud runner has a Celesto SDK adapter, and its Linux Docker image has passed the SDK/core and CLI preflight checks. The current checkout cannot start a cloud investigation until credentials and an LLM model are configured in `.env`. Runtime time verification is not implemented; see the limitations below.

## Verified time-control mechanism

Time control is not verified in the current implementation. `TimeController.verify_observed_time()` returns `True` without observing a target process, and `run_with_time()` does not execute its command. A real experiment must confirm the guest's observed time before scoring its result.

## Benchmark design and private-oracle separation

`agent/investigate.py` passes source text, not oracle labels, to its planning prompt. The 20 fixture files and oracle records are generated by `tools/make_fixtures.py`. C01 and L01 are explicitly marked in the oracle as reconstructions from documented behavior; no checked-in source is claimed to be a restored original from an external corpus. The benchmark entry point uses the Celesto Python SDK. The Windows venv cannot load its native dependency, but the Linux Docker image includes Celesto's declared `celesto-core` dependency and has passed the no-allocation SDK/CLI checks. Cloud execution remains blocked by absent credentials and LLM model configuration.

The benchmark defaults to one fresh run for each of the 20 oracle scenarios and enforces a 20-run maximum per invocation. Use `--only C02,E01` for the clean/date-bug smoke pair or `--only C02 --repeat 5` for five fresh executions of the same clean case; each run receives a unique runner-local label. No cloud sandbox has been started in the current investigation. In a cloud-enabled Linux environment, run:

```powershell
docker build -t timefault-ai:cloud-runner .
docker run --rm --env-file .env `
  --mount "type=bind,source=$((Get-Location).Path)\reports,target=/app/reports" `
  --mount "type=bind,source=$((Get-Location).Path)\commands.jsonl,target=/app/commands.jsonl" `
  timefault-ai:cloud-runner python agent/run_benchmark.py --only C02,E01 `
  --summary reports/cloud-smoke-C02-E01.json
```

`--summary` must name a new JSON path inside `reports/`; the runner rejects an existing path before allocating a sandbox. Use a different new summary path for each run. Replace the final command with `python agent/run_benchmark.py --only C02 --repeat 5 --summary reports/cloud-repeat-C02-5.json` or `python agent/run_benchmark.py --summary reports/cloud-full-benchmark.json` only when you intend those bounded allocations. This cloud command sequence has not been run successfully in this environment.

## Failure-window search strategy and limitations

`agent/investigate.py` samples planned dates and tests immediate neighbors; it does not implement a monotonic interval search. Its reported bounds are only sampled failing dates, not a proven complete failure window. Exact first/last failure and recovery dates remain unverified.

## Step-7 recovery policy

`RecoveryPolicy.policy_for(7, 10)` selects `resume`. It does not perform a recovery or measure repeated/lost steps, elapsed time, resource use, or evidence equivalence.

## Local temporal fixture checks

The fixture generator refuses to overwrite existing files unless `--force` is supplied; forced replacement first creates timestamped backups. Run it only if fixture files are absent. The local runner injects a clock into the Python process and checks selected oracle boundaries. This is a local test harness, not Celesto execution or OS-wide time virtualization:

```powershell
.\.venv\Scripts\python.exe agent\run_local_fixtures.py --only L01,L02,L03,L04,M01,M02,M03,M04,E01,E02,E03,E04,C01,C02,C03,C04 --output reports\local_scenario_boundary_checks_final.jsonl
```

The local boundary run completed for all sixteen selected date-bug and clean scenarios; its output is `reports/local_scenario_boundary_checks_final.jsonl`. The four `not_date_bug` fixtures were observed separately, but deliberately reported as unassessed rather than counted as passing; see `reports/local_non_date_observations.jsonl`. Earlier exploratory JSONL files are retained; `reports/local_fixture_runs.jsonl` includes the first E02 check, which exposed and led to fixing a harness assumption about the oracle's open-ended evaluation horizon. Use the final output files above for the corrected check. A new local-only smoke run checked clean C02 and date-sensitive E01 and appended two clock-patch observations to `reports/local_clean_bug_smoke_20261025.jsonl`; this is not Celesto evidence. The runner appends local observations to its chosen JSONL output. The reconstructed C01/L01 sources are marked as such in the oracle records and are not claimed to be restored original source.

## API examples

```bash
curl http://localhost:8080/health
curl http://localhost:8080/api/runs
curl -X POST http://localhost:8080/api/runs -H 'Content-Type: application/json' -d '{"run_id":"demo-001","sandbox_name":"sbx-seeddemo1","problem_id":"CF-01","state":"ready","execution_target":"celesto_sandbox"}'
```

## Known limitations and future improvements

This checkout is scaffolding rather than a verified end-to-end cloud workflow. In particular:

- `agent/run_one.py` now wraps the supported Celesto `CloudComputer` create/run/delete API. Its behavior is covered with a local fake-SDK contract test only; no real Celesto allocation or execution has been verified.
- The benchmark creates collision-checked, runner-local sandbox labels for each run; Celesto itself assigns the remote computer name. Names are not evidence that any cloud computer was allocated.
- C01 and L01 fixture sources were reconstructed from the documented behavior; their original source was not available.
- The local fixture runner's clock injection is for tests only and is not evidence of Celesto time-control support.
- The Celesto and time-control classes in `timefault.py` are mocks, not provider integrations.
- The installed Celesto 0.1.6 SDK cannot import because the required `celesto-core~=2026.9.22` package is missing. PyPI provides native wheels for Linux and macOS, not Windows; building it locally on Windows requires a Rust/MSVC toolchain. The Docker image now targets Linux, installs the cloud dependencies with retry/timeout settings, and includes the agent, fixtures, and oracle so that the benchmark can be invoked there.
- `reliability.json`, `containment.json`, `failure_trace.jsonl`, and `concurrency.json` are not sufficient on their own to substantiate real evaluations, containment tests, recovery measurements, or five-sandbox concurrency.
- The root `app.py` is an in-memory FastAPI metadata API, not the PostgreSQL-backed API described in the dashboard setup. It does not execute queued investigations.
- Docker Compose now requires local `DATABASE_URL` and `POSTGRES_PASSWORD` values instead of embedding database credentials, and publishes PostgreSQL only on localhost. The current API still does not connect to PostgreSQL.
- The Docker image includes the cloud dependencies and benchmark sources, but its default command still starts only the metadata API. Build or run it with an explicit benchmark command to investigate fixtures. The image build could not be validated because Docker Desktop's Linux engine was not running.

The local Python tests validate checked-in JSON structure, API behavior, report writes, and selected fixture boundaries. No Celesto investigation, 20-run evaluation, security-containment experiment, recovery comparison, or five-sandbox concurrency run is claimed as completed.

## Frontend dashboard

A React, TypeScript, and Vite dashboard is available in `frontend/`. It reads health and run records from the existing API, supports creating a run record, and provides overview, run details, scenario, analysis, evidence, and settings pages. Creating a run record does not start investigation execution.

The dashboard is configured to use the PostgreSQL-backed API at `http://127.0.0.1:8001`. Set `VITE_API_BASE_URL` in `frontend/.env.local` to the API base URL. Restart the Vite server after changing this file so the environment setting is reloaded.

During development, Vite proxies `/health` and `/api` to that configured URL so the browser does not require backend CORS support.

Start the existing API separately, then start the dashboard:

```bash
cd frontend
npm install
npm run dev
```

The dashboard accepts both an array of legacy run records (`problem_id`/`state`) and the queued-run API envelope (`runs`, `scenario_id`, `status`, and `created_at`). New submissions send only `scenario_id` and create a queued metadata record; they do not execute an investigation. The checked-in `app.py` is a legacy in-memory API and is not the PostgreSQL-backed server configured for this dashboard. Production deployments using direct browser-to-API requests must configure CORS on their API or provide a same-origin reverse proxy. Verdicts, tested dates, and reports remain unavailable unless returned by the API.

Run `npm run typecheck`, `npm test`, `npm run build`, or `npm run validate` from `frontend/` to validate the dashboard. `npm run validate` runs all three checks.

---

## Architecture diagram

```text
Code Repository → AI Planner → Celesto Cloud Computer → Oracle Evaluation → Finding and Reproduction Package
                       │
                       └── Evidence Store / Run Ledger
```
