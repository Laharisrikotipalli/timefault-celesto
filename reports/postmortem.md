# TimeFault AI — Validation Postmortem

## Summary

The API and PostgreSQL ledger were started with Docker Compose and verified
healthy. The HTTP API successfully created and retrieved a run persisted in
PostgreSQL. An empty `scenario_id` was rejected with HTTP 400.

The Python syntax check succeeded and all nine existing unit tests passed.

## What worked

- API health endpoint returned HTTP 200 and reported database health.
- POST `/api/runs` returned HTTP 201 for a valid scenario.
- GET `/api/runs` returned the created record.
- A direct SQL query confirmed the persisted row in PostgreSQL.
- Invalid empty `scenario_id` input returned HTTP 400.
- The mocked lifecycle test observed a cleanup invocation.
- Python compilation and nine unit tests completed successfully.

## Limitations

- Lifecycle cleanup was tested with mocked CLI operations. Real cloud deletion
  and Ctrl-C behavior have not been verified by that test.
- Local concurrency evidence is not evidence of concurrent API job scheduling.
- A successful health check does not establish the correctness of every
  investigation verdict.
- Existing reliability reports must be interpreted according to their recorded
  sample size, scenario coverage, and test conditions.
- A demo video must be recorded and checked separately before submission.

## Follow-up actions

1. Preserve existing reliability evidence and its original sample count.
2. Run the required benchmark only when the required resources and time are
   available; do not replace a 20-run report with a smaller sample.
3. Add tests for database failure handling and API input validation.
4. Verify cleanup behavior against a disposable guest before claiming real
   cloud cleanup is proven.
5. Record a short end-to-end demonstration and inspect the resulting video.
