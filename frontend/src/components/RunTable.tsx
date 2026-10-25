import { ArrowDown, ArrowUp, ArrowUpDown, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import type { RunRecord } from "../types/api";
import { displayStatus, formatDate, scenarioId, runStatus } from "../utils/runs";
import { StatusBadge } from "./Primitives";

export type RunSortKey = "run_id" | "scenario" | "status" | "created_at";

export function RunTable({
  runs,
  sortKey,
  sortDirection,
  onSort,
}: {
  runs: RunRecord[];
  sortKey: RunSortKey;
  sortDirection: "asc" | "desc";
  onSort: (key: RunSortKey) => void;
}) {
  const sortIcon = (key: RunSortKey) => {
    if (sortKey !== key) return <ArrowUpDown size={13} />;
    return sortDirection === "asc" ? (
      <ArrowUp size={13} />
    ) : (
      <ArrowDown size={13} />
    );
  };

  return (
    <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            {(
              [
                ["run_id", "Run ID"],
                ["scenario", "Scenario"],
                ["status", "Status"],
                ["created_at", "Created"],
              ] as const
            ).map(([key, label]) => (
              <th
                aria-sort={
                  sortKey !== key
                    ? "none"
                    : sortDirection === "asc"
                      ? "ascending"
                      : "descending"
                }
                key={key}
              >
                <button
                  className="sort-button"
                  onClick={() => onSort(key)}
                  type="button"
                >
                  {label}
                  {sortIcon(key)}
                </button>
              </th>
            ))}
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.run_id}>
              <td>
                <Link className="run-link mono" to={`/investigations/${encodeURIComponent(run.run_id)}`}>
                  {run.run_id}
                </Link>
              </td>
              <td>
                <span className="scenario-cell">{scenarioId(run)}</span>
              </td>
              <td>
                <StatusBadge status={displayStatus(runStatus(run))} />
              </td>
              <td className="muted-cell">
                {run.created_at ? formatDate(run.created_at) : "Not provided"}
              </td>
              <td>
                <Link
                  aria-label={`View investigation ${run.run_id}`}
                  className="icon-button table-action"
                  to={`/investigations/${encodeURIComponent(run.run_id)}`}
                >
                  <ExternalLink size={15} aria-hidden="true" />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
