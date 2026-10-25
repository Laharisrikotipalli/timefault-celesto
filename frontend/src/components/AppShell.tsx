import { Suspense, useState } from "react";
import {
  Activity,
  BarChart3,
  ChevronLeft,
  Clock3,
  FileCheck2,
  FlaskConical,
  LayoutDashboard,
  Menu,
  RefreshCw,
  Settings2,
} from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useWorkbenchData } from "../hooks/useWorkbenchData";

const navigation = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/investigations", label: "Investigations", icon: Activity },
  { to: "/scenarios", label: "Scenario Explorer", icon: FlaskConical },
  { to: "/analysis", label: "Failure Analysis", icon: BarChart3 },
  { to: "/evidence", label: "Evidence & Reports", icon: FileCheck2 },
  { to: "/settings", label: "Settings", icon: Settings2 },
];

function titleForPath(path: string): string {
  if (path === "/") return "Overview";
  if (path === "/investigations/new") return "New investigation";
  if (path.startsWith("/investigations/")) return "Investigation details";
  return navigation.find((item) => item.to === path)?.label ?? "TimeFault AI";
}

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const { health, healthError, healthLoading, refresh } = useWorkbenchData();
  const location = useLocation();
  const apiOnline = health?.status.toLowerCase() === "ok";

  const refreshData = async () => {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  };

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <aside className={`sidebar ${mobileOpen ? "mobile-open" : ""}`}>
        <NavLink className="brand" to="/" onClick={() => setMobileOpen(false)}>
          <span className="brand-mark"><Clock3 size={19} /></span>
          <span className="brand-copy">
            <strong>TimeFault<span> AI</span></strong>
            <small>Temporal investigation</small>
          </span>
        </NavLink>
        <div className="nav-label">WORKSPACE</div>
        <nav aria-label="Main navigation" className="primary-nav">
          {navigation.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}
              end={end}
              key={to}
              onClick={() => setMobileOpen(false)}
              title={collapsed ? label : undefined}
              to={to}
            >
              <Icon size={17} strokeWidth={1.8} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-health">
            <span className={`health-dot ${healthLoading ? "checking" : apiOnline ? "online" : "offline"}`} />
            <div>
              <strong>{healthLoading ? "Checking API" : apiOnline ? "API connected" : "API unavailable"}</strong>
              <small>
                {healthError
                  ? "Connection could not be verified"
                  : health?.database
                    ? `Database: ${health.database}`
                    : "Database status not reported"}
              </small>
            </div>
          </div>
          <button
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="collapse-button"
            onClick={() => setCollapsed((current) => !current)}
            type="button"
          >
            <ChevronLeft size={16} />
            {!collapsed && <span>Collapse sidebar</span>}
          </button>
        </div>
      </aside>

      {mobileOpen && (
        <button
          aria-label="Close navigation"
          className="mobile-scrim"
          onClick={() => setMobileOpen(false)}
          type="button"
        />
      )}

      <main className="main-column">
        <header className="topbar">
          <div className="topbar-left">
            <button
              aria-label="Open navigation"
              className="icon-button mobile-menu-button"
              onClick={() => setMobileOpen(true)}
              type="button"
            >
              <Menu size={19} />
            </button>
            <div className="breadcrumbs">
              <span>Workspace</span>
              <span className="breadcrumb-divider">/</span>
              <strong>{titleForPath(location.pathname)}</strong>
            </div>
          </div>
          <div className="topbar-actions">
            <div className={`connection-pill ${apiOnline ? "connected" : healthLoading ? "checking" : "disconnected"}`} role="status">
              <span className="health-dot" />
              <span>{healthLoading ? "Connecting" : apiOnline ? "API online" : "API offline"}</span>
            </div>
            <button
              aria-label="Refresh dashboard data"
              className={`icon-button refresh-button ${refreshing ? "is-refreshing" : ""}`}
              disabled={refreshing}
              onClick={() => void refreshData()}
              title="Refresh data"
              type="button"
            >
              <RefreshCw size={16} />
            </button>
            <div aria-label="TimeFault AI workspace" className="workspace-avatar">TF</div>
          </div>
        </header>
        <div className="page-content">
          <Suspense fallback={<div className="route-loading" role="status">Loading workspace…</div>}>
            <Outlet />
          </Suspense>
        </div>
      </main>
    </div>
  );
}
