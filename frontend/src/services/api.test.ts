import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createRun, getHealth, getRuns } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("API service", () => {
  it("reads the health response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok", database: "ok" }), { status: 200 }),
    ));
    await expect(getHealth()).resolves.toEqual({ status: "ok", database: "ok" });
  });

  it("normalizes the current API's problem_id and state fields", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify([{
        run_id: "demo-001",
        problem_id: "CF-01",
        state: "ready",
      }]), { status: 200 }),
    ));
    await expect(getRuns()).resolves.toEqual([{
      run_id: "demo-001",
      scenario_id: undefined,
      problem_id: "CF-01",
      status: undefined,
      state: "ready",
      created_at: undefined,
    }]);
  });

  it("reads run records from the paginated API envelope", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        runs: [{
          run_id: "run-envelope",
          scenario_id: "CF-17",
          status: "queued",
          created_at: "2026-10-23T12:00:00Z",
        }],
        count: 1,
      }), { status: 200 }),
    ));
    await expect(getRuns()).resolves.toMatchObject([{
      run_id: "run-envelope",
      scenario_id: "CF-17",
      status: "queued",
      created_at: "2026-10-23T12:00:00Z",
    }]);
  });

  it("sends the exact run-create contract and parses the response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        run_id: "run-123",
        scenario_id: "CF-17",
        status: "queued",
        created_at: "2026-10-23T12:00:00Z",
      }), { status: 201 }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const payload = { scenario_id: "CF-17" };
    await expect(createRun(payload)).resolves.toMatchObject({
      run_id: "run-123",
      scenario_id: "CF-17",
      status: "queued",
    });
    expect(fetchMock).toHaveBeenCalledWith(expect.stringMatching(/\/api\/runs$/), expect.objectContaining({
      method: "POST",
      body: '{"scenario_id":"CF-17"}',
    }));
  });

  it("reads backend error and legacy detail responses", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: "scenario_id is invalid" }), { status: 400 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "legacy bad request" }), { status: 400 })));
    await expect(createRun({ scenario_id: "" })).rejects.toMatchObject({
      name: "ApiError",
      message: "scenario_id is invalid",
      status: 400,
    });
    await expect(getHealth()).rejects.toThrow("legacy bad request");
  });

  it("provides a useful server error and connection message", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ error: "database unavailable" }), { status: 500 }))
      .mockResolvedValueOnce(new Response("{}", { status: 500 }))
      .mockRejectedValueOnce(new TypeError("Failed to fetch")));
    await expect(createRun({ scenario_id: "CF-17" })).rejects.toThrow("database unavailable");
    await expect(createRun({ scenario_id: "CF-17" })).rejects.toThrow(/internal error/);
    await expect(getHealth()).rejects.toThrow(/Could not reach the TimeFault API/);
  });

  it("reports invalid JSON responses explicitly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response("not json", { status: 200 }),
    ));
    await expect(getHealth()).rejects.toBeInstanceOf(ApiError);
  });
});
