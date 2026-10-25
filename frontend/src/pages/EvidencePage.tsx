import { Download, FileJson2, FileText, ShieldCheck, Terminal } from "lucide-react";
import { Link } from "react-router-dom";
import { type ReactNode } from "react";
import { EmptyState, Notice, PageHeading } from "../components/Primitives";
import { useWorkbenchData } from "../hooks/useWorkbenchData";
import { downloadEvidence } from "../utils/downloadEvidence";

export function EvidencePage() {
  const { runs, runsLoading, runsError } = useWorkbenchData();
  return (
    <>
      <PageHeading
        eyebrow="AUDIT MATERIAL"
        title="Evidence & Reports"
        description="Investigation evidence will be available here when exposed by the backend."
      />
      <Notice>
        <ShieldCheck size={16} />
        <span>Downloads are enabled only for evidence returned by an implemented API source. No local repository files are assumed to be downloadable.</span>
      </Notice>
      {runsError && <Notice tone="warning">The run list could not be loaded, so evidence availability could not be checked.</Notice>}
      {runsLoading ? (
        <section className="panel"><div className="skeleton-list"><div className="skeleton-row" /><div className="skeleton-row" /></div></section>
      ) : runs.length ? (
        <>
          <div className="evidence-summary-grid">
            <SummaryCard icon={<FileJson2 size={18} />} label="Run records" value={String(runs.length)} detail="Returned by API" />
            <SummaryCard icon={<FileText size={18} />} label="Investigation reports" value={String(runs.filter((run) => run.evidence).length)} detail="API-provided JSON evidence" />
            <SummaryCard icon={<Terminal size={18} />} label="Replay packages" value="Unavailable" detail="No replay source is configured" />
          </div>
          <section className="panel evidence-list-panel">
            <div className="panel-heading"><div><p className="eyebrow">AVAILABLE MATERIAL</p><h2>Evidence sources</h2></div></div>
            {runs.map((run) => (
              <div className="evidence-run-row" key={run.run_id}>
                <div className="evidence-file-icon"><FileJson2 size={17} /></div>
                <div className="evidence-run-name"><strong>{run.run_id}</strong><span>{run.evidence ? "Evidence returned by API" : "Run metadata only · no result evidence available"}</span></div>
                <Link className="button button-secondary button-small" to={`/investigations/${encodeURIComponent(run.run_id)}`}>View record</Link>
                <button className="icon-button" disabled={!run.evidence} onClick={() => run.evidence && downloadEvidence(run.run_id, run.evidence)} title={run.evidence ? "Download API-provided JSON evidence" : "The API does not expose a downloadable report"}><Download size={15} /></button>
              </div>
            ))}
          </section>
        </>
      ) : (
        <section className="panel">
          <EmptyState icon={<FileText />} title="No evidence sources available" description="Evidence download actions will be enabled when the API provides a real report source." />
        </section>
      )}
    </>
  );
}

function SummaryCard({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string; detail: string }) {
  return <article className="panel evidence-summary-card"><span className="metric-icon">{icon}</span><span>{label}</span><strong>{value}</strong><small>{detail}</small></article>;
}
