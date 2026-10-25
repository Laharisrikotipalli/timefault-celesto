import { useMemo, useState } from "react";
import { CircleAlert, Plus, Search, SlidersHorizontal } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState, ErrorPanel, PageHeading, SkeletonRows } from "../components/Primitives";
import { RunTable, type RunSortKey } from "../components/RunTable";
import { useWorkbenchData } from "../hooks/useWorkbenchData";
import { runStatus } from "../utils/runs";

export function InvestigationsPage() {
  const { runs, runsLoading, runsError, refresh } = useWorkbenchData();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sortKey, setSortKey] = useState<RunSortKey>("created_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const statuses = useMemo(
    () => Array.from(new Set(runs.map((run) => runStatus(run)))).sort(),
    [runs],
  );
  const visibleRuns = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return runs
      .filter((run) => {
        const matchesQuery =
          !normalizedQuery ||
          run.run_id.toLowerCase().includes(normalizedQuery) ||
          (run.scenario_id ?? run.problem_id ?? "").toLowerCase().includes(normalizedQuery);
        const matchesStatus =
          statusFilter === "all" || runStatus(run) === statusFilter;
        return matchesQuery && matchesStatus;
      })
      .sort((a, b) => {
        const valueFor = (run: typeof a) => {
          switch (sortKey) {
            case "run_id":
              return run.run_id;
            case "scenario":
              return run.scenario_id ?? run.problem_id ?? "";
            case "status":
              return runStatus(run);
            default:
              return run.created_at ?? "";
          }
        };
        return valueFor(a).localeCompare(valueFor(b)) * (sortDirection === "asc" ? 1 : -1);
      });
  }, [query, runs, sortDirection, sortKey, statusFilter]);
  const onSort = (key: RunSortKey) => {
    if (sortKey === key) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDirection(key === "created_at" ? "desc" : "asc");
    }
  };

  return (
    <>
      <PageHeading
        eyebrow="RUN LEDGER"
        title="Investigations"
        description="Search and inspect run records returned by the TimeFault API."
        actions={<Link className="button button-primary" to="/investigations/new"><Plus size={16} /> New run</Link>}
      />
      {runsError && <ErrorPanel message={runsError} onRetry={() => void refresh()} />}
      <section className="panel list-panel">
        <div className="list-toolbar">
          <label className="search-box">
            <Search size={16} aria-hidden="true" />
            <input
              aria-label="Search by run ID or scenario"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search run or scenario…"
              type="search"
              value={query}
            />
          </label>
          <label className="filter-select">
            <SlidersHorizontal size={15} aria-hidden="true" />
            <span className="sr-only">Filter by status</span>
            <select onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}>
              <option value="all">All statuses</option>
              {statuses.map((status) => <option key={status} value={status}>{status}</option>)}
            </select>
          </label>
          <span className="results-count">{runsLoading ? "Loading…" : `${visibleRuns.length} records`}</span>
        </div>
        {runsLoading ? (
          <SkeletonRows count={6} />
        ) : runsError ? (
          <EmptyState icon={<CircleAlert />} title="Could not load investigations" description="Check that the API is available, then retry." action={<button className="button button-secondary" onClick={() => void refresh()} type="button">Retry</button>} />
        ) : visibleRuns.length ? (
          <RunTable
            onSort={onSort}
            runs={visibleRuns}
            sortDirection={sortDirection}
            sortKey={sortKey}
          />
        ) : (
          <EmptyState
            icon={<Search />}
            title={runs.length ? "No matching records" : "No run records yet"}
            description={runs.length ? "Try a different search term or status filter." : "The table will populate when the backend returns run records."}
            action={runs.length ? <button className="button button-secondary" onClick={() => { setQuery(""); setStatusFilter("all"); }} type="button">Clear filters</button> : undefined}
          />
        )}
      </section>
      <p className="data-footnote">The current API response may not include creation timestamps. Missing values are shown as unavailable.</p>
    </>
  );
}
