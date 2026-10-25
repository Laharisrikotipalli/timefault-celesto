import type { RunRecord } from "../types/api";

export function scenarioId(run: RunRecord): string {
  return run.scenario_id ?? run.problem_id ?? "Unavailable";
}

export function runStatus(run: RunRecord): string {
  return run.status ?? run.state ?? "Unavailable";
}

export function displayStatus(status: string): string {
  const labels: Record<string, string> = {
    created: "Created",
    ready: "Ready",
    running: "Running",
    succeeded: "Completed",
    failed: "Failed",
    deleted: "Deleted",
    queued: "Queued",
  };
  return labels[status.toLowerCase()] ?? status.replaceAll("_", " ");
}

export function statusTone(status: string): string {
  switch (status.toLowerCase()) {
    case "succeeded":
    case "completed":
      return "success";
    case "running":
      return "running";
    case "failed":
    case "error":
      return "danger";
    case "created":
    case "queued":
    case "ready":
      return "pending";
    default:
      return "neutral";
  }
}

export function formatDate(value?: string): string {
  if (!value) return "Not provided";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Invalid timestamp";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}
