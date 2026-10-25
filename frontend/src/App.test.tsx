import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import App from "./App";
import * as api from "./services/api";

vi.mock("./services/api", () => ({
  getHealth: vi.fn(),
  getRuns: vi.fn(),
  createRun: vi.fn(),
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => children,
  PieChart: ({ children }: { children: ReactNode }) => children,
  Pie: () => null,
  Cell: () => null,
  Tooltip: () => null,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("application routes and data states", () => {
  it("renders the overview from real-shaped API data", async () => {
    vi.mocked(api.getHealth).mockResolvedValue({ status: "ok", database: "ok" });
    vi.mocked(api.getRuns).mockResolvedValue([{
      run_id: "demo-001",
      problem_id: "CF-01",
      state: "ready",
    }]);
    render(<App />);
    expect(await screen.findByRole("link", { name: "demo-001" })).toBeInTheDocument();
    expect(screen.getByText("API connected")).toBeInTheDocument();
    expect(screen.getAllByText("Ready").length).toBeGreaterThan(0);
  });

  it("shows a useful empty state when the API returns no runs", async () => {
    vi.mocked(api.getHealth).mockResolvedValue({ status: "ok", database: "ok" });
    vi.mocked(api.getRuns).mockResolvedValue([]);
    render(<App />);
    expect(await screen.findByText("No investigation records yet")).toBeInTheDocument();
  });

  it("surfaces run-list failures without fake metrics", async () => {
    vi.mocked(api.getHealth).mockResolvedValue({ status: "ok", database: "ok" });
    vi.mocked(api.getRuns).mockRejectedValue(new Error("API unavailable"));
    render(<App />);
    await waitFor(() => expect(screen.getByText("API unavailable")).toBeInTheDocument());
    expect(screen.getByText("Unable to load run records")).toBeInTheDocument();
  });

  it("submits only a run record and makes the non-execution behavior explicit", async () => {
    vi.mocked(api.getHealth).mockResolvedValue({ status: "ok", database: "ok" });
    vi.mocked(api.getRuns).mockResolvedValue([]);
    vi.mocked(api.createRun).mockResolvedValue({
      run_id: "run-test",
      scenario_id: "CF-17",
      status: "queued",
      created_at: "2026-10-23T12:00:00Z",
    });
    render(<App />);
    fireEvent.click(await screen.findByRole("link", { name: /New investigation/i }));
    expect(await screen.findByRole("heading", { name: "New investigation" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "CF-17" } });
    expect(screen.getByText("Not available")).toBeInTheDocument();
    expect(screen.getByText("Not configured or verified")).toBeInTheDocument();
    expect(screen.getByText("Available through the API")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Create run record/i }));
    expect(await screen.findByText("Run record submitted")).toBeInTheDocument();
    expect(screen.getByText(/has not started/)).toBeInTheDocument();
    expect(screen.getByText("queued")).toBeInTheDocument();
    expect(screen.getByText("2026-10-23T12:00:00Z")).toBeInTheDocument();
    expect(api.createRun).toHaveBeenCalledWith({ scenario_id: "CF-17" });
    expect(api.getRuns).toHaveBeenCalledTimes(2);
  });

  it("renders every primary navigation route", async () => {
    vi.mocked(api.getHealth).mockResolvedValue({ status: "ok", database: "ok" });
    vi.mocked(api.getRuns).mockResolvedValue([]);
    render(<App />);
    const routes = [
      ["Investigations", "Investigations"],
      ["Scenario Explorer", "Scenario Explorer"],
      ["Failure Analysis", "Failure Analysis"],
      ["Evidence & Reports", "Evidence & Reports"],
      ["Settings", "Settings"],
    ];
    for (const [linkName, heading] of routes) {
      fireEvent.click(await screen.findByRole("link", { name: linkName }));
      expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    }
  });
});
