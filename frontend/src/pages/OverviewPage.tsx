import {
  Activity,
  ArrowRight,
  CircleAlert,
  CircleCheck,
  Clock3,
  FlaskConical,
  Play,
  Radio,
} from "lucide-react";
import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { Link } from "react-router-dom";
import { EmptyState, ErrorPanel, PageHeading, SkeletonRows } from "../components/Primitives";
import { RunTable, type RunSortKey } from "../components/RunTable";
import { useWorkbenchData } from "../hooks/useWorkbenchData";
import { displayStatus, runStatus } from "../utils/runs";
import { useMemo, useState, type ReactNode } from "react";

const chartColors = ["#29d6b2", "#8f78ff", "#ff667d", "#f4b85c", "#62708a"];

export function OverviewPage() {
  const { runs, runsLoading, runsError, health, healthError, refresh } = useWorkbenchData();
  const [sortKey, setSortKey] = useState<RunSortKey>("created_at");
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc");
  const statistics = useMemo(() => {
    const statuses = runs.map((run) => runStatus(run).toLowerCase());
    return {
      total: runs.length,
      completed: statuses.filter((status) => status === "succeeded" || status === "completed").length,
      running: statuses.filter((status) => status === "running").length,
      failed: statuses.filter((status) => status === "failed" || status === "error").length,
    };
  }, [runs]);
  const distribution = useMemo(() => {
    const counts = new Map<string, number>();
    runs.forEach((run) => {
      const status = displayStatus(runStatus(run));
      counts.set(status, (counts.get(status) ?? 0) + 1);
    });
    return Array.from(counts, ([name, value]) => ({ name, value }));
  }, [runs]);
  const latestRuns = useMemo(() => {
    const sorted = [...runs].sort((a, b) => {
      const valueA =
        sortKey === "run_id"
          ? a.run_id
          : sortKey === "scenario"
            ? a.scenario_id ?? a.problem_id ?? ""
            : sortKey === "status"
              ? runStatus(a)
              : a.created_at ?? "";
      const valueB =
        sortKey === "run_id"
          ? b.run_id
          : sortKey === "scenario"
            ? b.scenario_id ?? b.problem_id ?? ""
            : sortKey === "status"
              ? runStatus(b)
              : b.created_at ?? "";
      return valueA.localeCompare(valueB) * (sortDirection === "asc" ? 1 : -1);
    });
    return sorted.slice(0, 5);
  }, [runs, sortDirection, sortKey]);

  const onSort = (key: RunSortKey) => {
    if (key === sortKey) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDirection(key === "created_at" ? "desc" : "asc");
    }
  };

  return (
    <>
      <PageHeading
        eyebrow="TEMPORAL RELIABILITY WORKSPACE"
        title="Overview"
        description="A clear view of investigation records and system connectivity."
        actions={
          <Link className="button button-primary" to="/investigations/new">
            <Play size={15} fill="currentColor" />
            New investigation
          </Link>
        }
      />

      {runsError && <ErrorPanel message={runsError} onRetry={() => void refresh()} />}

      <section aria-label="Investigation summary" className="metric-grid">
        <MetricCard
          accent="violet"
          icon={<FlaskConical size={18} />}
          label="Total investigations"
          value={runsLoading || runsError ? "—" : statistics.total}
          note={runsError ? "Unable to load run records" : "Run records returned by the API"}
        />
        <MetricCard
          accent="green"
          icon={<CircleCheck size={18} />}
          label="Completed"
          value={runsLoading || runsError ? "—" : statistics.completed}
          note="Explicitly marked completed"
        />
        <MetricCard
          accent="cyan"
          icon={<Radio size={18} />}
          label="Running"
          value={runsLoading || runsError ? "—" : statistics.running}
          note="Currently marked running"
        />
        <MetricCard
          accent="rose"
          icon={<CircleAlert size={18} />}
          label="Failed"
          value={runsLoading || runsError ? "—" : statistics.failed}
          note="Explicitly marked failed"
        />
      </section>

      <div className="overview-grid">
        <section className="panel recent-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">RUN LEDGER</p>
              <h2>Recent investigations</h2>
              <p className="panel-subtitle">Latest records returned by the backend.</p>
            </div>
            <Link className="text-link" to="/investigations">
              View all <ArrowRight size={14} />
            </Link>
          </div>
          {runsLoading ? (
            <SkeletonRows />
          ) : runsError ? (
            <EmptyState icon={<CircleAlert />} title="Run history unavailable" description="The API could not provide run records." action={<button className="button button-secondary" onClick={() => void refresh()} type="button">Try again</button>} />
          ) : latestRuns.length ? (
            <RunTable
              onSort={onSort}
              runs={latestRuns}
              sortDirection={sortDirection}
              sortKey={sortKey}
            />
          ) : (
            <EmptyState
              icon={<Activity />}
              title="No investigation records yet"
              description="When the API returns run records, they will appear here. Creating a record does not execute an investigation."
              action={<Link className="button button-secondary" to="/investigations/new">Create a run record</Link>}
            />
          )}
        </section>

        <section className="panel distribution-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">LIVE API DATA</p>
              <h2>Status distribution</h2>
              <p className="panel-subtitle">Run states as reported by the API.</p>
            </div>
            <span className="panel-icon"><Activity size={17} /></span>
          </div>
          {runsLoading ? (
            <div className="chart-skeleton" />
          ) : runsError ? (
            <div className="chart-empty">Status distribution unavailable.</div>
          ) : distribution.length ? (
            <>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={distribution}
                      dataKey="value"
                      innerRadius={54}
                      outerRadius={76}
                      paddingAngle={4}
                      stroke="none"
                    >
                      {distribution.map((item, index) => (
                        <Cell key={item.name} fill={chartColors[index % chartColors.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{
                        background: "#171d2a",
                        border: "1px solid #30394a",
                        borderRadius: 10,
                        color: "#f1f4fb",
                        fontSize: 12,
                      }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="chart-center">
                  <strong>{runs.length}</strong>
                  <span>records</span>
                </div>
              </div>
              <div className="legend-list">
                {distribution.map((item, index) => (
                  <div className="legend-item" key={item.name}>
                    <span className="legend-dot" style={{ background: chartColors[index % chartColors.length] }} />
                    <span>{item.name}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="chart-empty">
              <Clock3 size={24} />
              <span>Distribution appears after run records are available.</span>
            </div>
          )}
        </section>
      </div>

      <div className="overview-lower-grid">
        <section className="panel activity-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">RECENT ACTIVITY</p>
              <h2>Latest run records</h2>
            </div>
            <span className="panel-icon"><Clock3 size={17} /></span>
          </div>
          {runsLoading ? (
            <SkeletonRows count={3} />
          ) : runsError ? (
            <p className="muted-copy">Activity unavailable while run history cannot be loaded.</p>
          ) : runs.length ? (
            <div className="activity-list">
              {runs.slice(0, 4).map((run) => (
                <div className="activity-item" key={run.run_id}>
                  <span className={`activity-marker ${runStatus(run).toLowerCase()}`} />
                  <div className="activity-copy">
                    <strong>{run.run_id}</strong>
                    <span>{run.problem_id ?? run.scenario_id ?? "Scenario unavailable"} · {displayStatus(runStatus(run))}</span>
                  </div>
                  <span className="activity-time">{run.created_at ? new Date(run.created_at).toLocaleDateString() : "Time not provided"}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted-copy">No run activity is available yet.</p>
          )}
        </section>

        <section className="panel health-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">CONNECTIVITY</p>
              <h2>System status</h2>
            </div>
            <span className="panel-icon"><Radio size={17} /></span>
          </div>
          <HealthRow
            label="TimeFault API"
            value={health?.status ?? (healthError ? "Unreachable" : "Checking")}
            state={healthError ? "offline" : health?.status === "ok" ? "online" : "checking"}
          />
          <HealthRow
            label="Database"
            value={health?.database ?? "Not reported by API"}
            state={health?.database ? "online" : "unknown"}
          />
          <p className="health-footnote">
            Health values reflect <code>GET /health</code>. A database connection is not inferred when the endpoint omits it.
          </p>
        </section>
      </div>
    </>
  );
}

function MetricCard({
  accent,
  icon,
  label,
  value,
  note,
}: {
  accent: string;
  icon: ReactNode;
  label: string;
  value: string | number;
  note: string;
}) {
  return (
    <article className={`metric-card accent-${accent}`}>
      <div className="metric-topline">
        <span className="metric-icon">{icon}</span>
        <span className="metric-label">{label}</span>
      </div>
      <strong className="metric-value">{value}</strong>
      <span className="metric-note">{note}</span>
    </article>
  );
}

function HealthRow({
  label,
  value,
  state,
}: {
  label: string;
  value: string;
  state: string;
}) {
  return (
    <div className="health-row">
      <div className="health-row-label">
        <span className={`health-dot ${state}`} />
        <strong>{label}</strong>
      </div>
      <span className="health-row-value">{value}</span>
    </div>
  );
}
