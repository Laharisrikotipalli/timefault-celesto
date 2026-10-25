import type {
  CreateRunPayload,
  HealthResponse,
  RunRecord,
} from "../types/api";

type TestOutcome = NonNullable<RunRecord["tested_results"]>[number]["outcome"];

function isTestOutcome(value: unknown): value is TestOutcome {
  return (
    value === "pass" ||
    value === "fail" ||
    value === "inconclusive" ||
    value === "error"
  );
}

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const baseUrl = (
  import.meta.env.DEV ? "" : configuredBaseUrl || ""
).replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("Could not reach the TimeFault API. Check the connection and try again.");
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new ApiError(
      response.ok
        ? "The API returned an invalid JSON response."
        : `The API request failed (${response.status}) and returned an unreadable response.`,
      response.status,
    );
  }

  if (!response.ok) {
    const message =
      isObject(body) && typeof body.error === "string"
        ? body.error
        : isObject(body) && typeof body.detail === "string"
          ? body.detail
          : response.status === 500
            ? "The TimeFault API encountered an internal error while processing the request. Please try again later."
            : `Request failed (${response.status}).`;
    throw new ApiError(message, response.status);
  }

  return body;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseRun(value: unknown): RunRecord {
  if (!isObject(value) || typeof value.run_id !== "string") {
    throw new ApiError("The API returned a run record with an unexpected shape.");
  }

  const scenarioId =
    typeof value.scenario_id === "string" ? value.scenario_id : undefined;
  const problemId =
    typeof value.problem_id === "string" ? value.problem_id : undefined;
  const status = typeof value.status === "string" ? value.status : undefined;
  const state = typeof value.state === "string" ? value.state : undefined;
  const createdAt =
    typeof value.created_at === "string" ? value.created_at : undefined;
  const testedResults = Array.isArray(value.tested_results)
    ? value.tested_results.flatMap((result) =>
        isObject(result) &&
        typeof result.date === "string" &&
        isTestOutcome(result.outcome)
          ? [{ date: result.date, outcome: result.outcome }]
          : [],
      )
    : undefined;
  const stringArray = (candidate: unknown) =>
    Array.isArray(candidate) && candidate.every((item) => typeof item === "string")
      ? candidate
      : undefined;

  if ((!scenarioId && !problemId) || (!status && !state)) {
    throw new ApiError("The API returned a run record missing its scenario or status.");
  }

  return {
    run_id: value.run_id,
    scenario_id: scenarioId,
    problem_id: problemId,
    status,
    state,
    created_at: createdAt,
    verdict: typeof value.verdict === "string" ? value.verdict : undefined,
    tested_dates: stringArray(value.tested_dates),
    tested_results: testedResults,
    first_failure_date:
      typeof value.first_failure_date === "string"
        ? value.first_failure_date
        : undefined,
    last_failure_date:
      typeof value.last_failure_date === "string"
        ? value.last_failure_date
        : undefined,
    recovery_date:
      typeof value.recovery_date === "string" ? value.recovery_date : undefined,
    explanation:
      typeof value.explanation === "string" ? value.explanation : undefined,
    logs: stringArray(value.logs),
    replay_command:
      typeof value.replay_command === "string"
        ? value.replay_command
        : undefined,
    evidence: isObject(value.evidence) ? value.evidence : undefined,
  };
}

export async function getHealth(): Promise<HealthResponse> {
  const body = await requestJson("/health");
  if (!isObject(body) || typeof body.status !== "string") {
    throw new ApiError("The API returned an unexpected health response.");
  }
  return {
    status: body.status,
    database: typeof body.database === "string" ? body.database : undefined,
  };
}

export async function getRuns(): Promise<RunRecord[]> {
  const body = await requestJson("/api/runs");
  if (Array.isArray(body)) {
    return body.map(parseRun);
  }
  if (isObject(body) && Array.isArray(body.runs)) {
    return body.runs.map(parseRun);
  }
  throw new ApiError("The API returned an unexpected run-list response.");
}

export async function createRun(
  payload: CreateRunPayload,
): Promise<RunRecord> {
  return parseRun(
    await requestJson("/api/runs", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  );
}
