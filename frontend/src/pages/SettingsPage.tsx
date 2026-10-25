import { Check, CircleAlert, Globe2, Server, Shield } from "lucide-react";
import { type ReactNode } from "react";
import { Notice, PageHeading } from "../components/Primitives";
import { useWorkbenchData } from "../hooks/useWorkbenchData";

export function SettingsPage() {
  const { health, healthError, healthLoading } = useWorkbenchData();
  const apiBase = import.meta.env.VITE_API_BASE_URL?.trim() || "Vite development proxy";
  return (
    <>
      <PageHeading
        eyebrow="WORKSPACE PREFERENCES"
        title="Settings"
        description="Connection details for this frontend workspace."
      />
      <Notice>
        <Shield size={16} />
        <span>Frontend settings contain no authentication or secret management. Do not put database passwords, API keys, or Celesto credentials in <code>VITE_*</code> variables.</span>
      </Notice>
      <section className="panel settings-panel">
        <div className="panel-heading"><div><p className="eyebrow">API CONNECTION</p><h2>Backend configuration</h2></div><span className="panel-icon"><Server size={17} /></span></div>
        <SettingRow icon={<Globe2 size={17} />} label="API base URL" value={apiBase} />
        <SettingRow icon={healthError ? <CircleAlert size={17} /> : <Check size={17} />} label="Health endpoint" value={healthLoading ? "Checking…" : healthError ? "Unreachable" : health?.status ?? "Unknown"} />
        <SettingRow icon={<Server size={17} />} label="Database status" value={health?.database ?? "Not reported by GET /health"} />
        <div className="settings-note">
          <strong>Local development</strong>
          <p>Set <code>TIMEFAULT_API_TARGET</code> in the frontend environment to change the Vite proxy target. To use a direct browser URL, set <code>VITE_API_BASE_URL</code> and configure the backend’s CORS policy accordingly.</p>
        </div>
      </section>
      <section className="panel settings-panel">
        <div className="panel-heading"><div><p className="eyebrow">INTEGRATION BOUNDARIES</p><h2>Current capabilities</h2></div></div>
        <div className="capability-list">
          <Capability label="API health check" state="Connected to GET /health" />
          <Capability label="Run record list" state="Connected to GET /api/runs" />
          <Capability label="Create run record" state="Connected to POST /api/runs" />
          <Capability label="Investigation execution" state="Not wired to frontend" muted />
          <Capability label="Evidence downloads" state="No API source available" muted />
        </div>
      </section>
    </>
  );
}

function SettingRow({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return <div className="setting-row"><span className="setting-icon">{icon}</span><span>{label}</span><strong>{value}</strong></div>;
}

function Capability({ label, state, muted = false }: { label: string; state: string; muted?: boolean }) {
  return <div className="capability-row"><span className={`health-dot ${muted ? "unknown" : "online"}`} /><strong>{label}</strong><span>{state}</span></div>;
}
