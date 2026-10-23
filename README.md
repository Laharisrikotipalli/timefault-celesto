# TimeFault AI

TimeFault AI investigates date-sensitive software failures by executing test
scenarios under controlled dates, comparing observations with an oracle, and
producing evidence for its verdicts.

## Features

- **Temporal investigation:** test candidate dates and identify failure windows.
- **Oracle-based verdicts:** compare observed behavior with expected labels.
- **Repeated execution:** distinguish repeatable failures from inconclusive or flaky results.
- **Command containment:** block selected dangerous commands before guest execution.
- **Failure cleanup:** use finally blocks to invoke guest cleanup.
- **HTTP API and PostgreSQL ledger:** create and retrieve run records.

## Architecture

- `agent/`: investigation, execution, benchmark, and verdict logic.
- `fixtures/`: date-sensitive and control scenarios.
- `oracle/`: expected scenario labels.
- `tests/`: unit tests.
- `api/server.py`: HTTP API.
- `seeds/01_runs.sql`: PostgreSQL schema.
- `reports/`: benchmark, capability, and validation evidence.
- `logs/`: command audit and containment evidence.

## Run locally

Requirements: Python 3 and Docker Compose.

1. Create your local environment configuration from `.env.example` and provide
   valid credentials for any external service you intend to use.
2. Start the API and database:

   ```bash
   docker compose up -d --build
   ```

3. Check health:

   ```bash
   curl -i http://127.0.0.1:8000/health
   ```

4. Create a run:

   ```bash
   curl -i -X POST http://127.0.0.1:8000/api/runs \
     -H 'Content-Type: application/json' \
     -d '{"scenario_id":"E01"}'
   ```

5. List runs:

   ```bash
   curl -sS http://127.0.0.1:8000/api/runs
   ```

6. Inspect the database:

   ```bash
   docker compose exec -T ledger psql -U timefault -d timefault \
     -c 'SELECT run_id, scenario_id, status, created_at FROM runs;'
   ```

Stop the local services with `docker compose down`. Add `-v` only if you
intentionally want to delete the database volume and its persisted data.

## Tests

Run the unit tests:

```bash
python3 -m py_compile agent/*.py tests/*.py
python3 -m unittest discover -s tests -v
```

## Evidence and limitations

Validation reports are stored under `reports/`. The API has been tested against
PostgreSQL for health, run creation, run retrieval, and invalid input.

The lifecycle cleanup report uses mocked CLI operations. It does not prove
real cloud deletion or Ctrl-C cleanup. Local concurrency tests do not prove
concurrent scheduling through the HTTP API. Consult individual reports for
their scope and limitations.

Do not commit `.env`, API keys, or other secrets. Use `.env.example` as the
configuration template.
