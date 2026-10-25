import { ArrowLeft, CircleHelp, Download, FileText, Terminal } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { Notice, PageHeading, StatusBadge } from "../components/Primitives";
import { useWorkbenchData } from "../hooks/useWorkbenchData";
import { downloadEvidence } from "../utils/downloadEvidence";
import { displayStatus, formatDate, runStatus, scenarioId } from "../utils/runs";

const unavailable = "Not provided by the current API";

export function InvestigationDetailPage() {
  const { runId } = useParams();
  const { runs, runsLoading, runsError } = useWorkbenchData();
  const run = runs.find((item) => item.run_id === runId);

  return (
    <>
      <PageHeading
        eyebrow="INVESTIGATION RECORD"
        title={runId ?? "Run details"}
        description="Run metadata and evidence fields supplied by the backend."
        actions={<Link className="button button-quiet" to="/investigations"><ArrowLeft size={15} /> All runs</Link>}
      />
      {runsError && <Notice tone="warning">Run details may be incomplete because the run list could not be loaded.</Notice>}
      {runsLoading ? (
        <section className="panel detail-loading"><div className="skeleton-line" /><div className="skeleton-line short" /></section>
      ) : !run ? (
        <section className="panel detail-missing">
          <CircleHelp size={24} />
          <h2>Run record not found</h2>
          <p>This run ID was not present in the records returned by the API.</p>
          <Link className="button button-secondary" to="/investigations">Back to investigations</Link>
        </section>
      ) : (
        <>
          <Notice>
            <CircleHelp size={16} />
            <span>Details below reflect only fields returned by the API. Investigation verdicts, tested dates, and reports are not currently exposed.</span>
          </Notice>
          <div className="detail-grid">
            <section className="panel detail-main">
              <div className="detail-title-row">
                <div><p className="eyebrow">RUN METADATA</p><h2>Run overview</h2></div>
                <StatusBadge status={displayStatus(runStatus(run))} />
              </div>
              <div className="metadata-grid">
                <Metadata label="Run ID" value={run.run_id} mono />
                <Metadata label="Scenario ID" value={scenarioId(run)} />
                <Metadata label="Status" value={runStatus(run)} />
                <Metadata label="Created at" value={run.created_at ? formatDate(run.created_at) : unavailable} />
                <Metadata label="Verdict" value={run.verdict ?? unavailable} />
              </div>
            </section>
            <section className="panel verdict-panel">
              <p className="eyebrow">INVESTIGATION VERDICT</p>
              <div className="verdict-empty">
                <CircleHelp size={21} />
                <strong>Not available</strong>
                <span>The API does not return a verdict for this run.</span>
              </div>
            </section>
            <section className="panel detail-full">
              <div className="panel-heading">
                <div><p className="eyebrow">TEMPORAL WINDOW</p><h2>Failure analysis</h2></div>
              </div>
              <div className="analysis-facts">
                <Metadata label="Tested dates" value={run.tested_dates?.join(", ") ?? unavailable} />
                <Metadata label="First failure" value={run.first_failure_date ?? unavailable} />
                <Metadata label="Last failure" value={run.last_failure_date ?? unavailable} />
                <Metadata label="Recovery date" value={run.recovery_date ?? unavailable} />
              </div>
              {run.explanation && <p className="explanation-copy">{run.explanation}</p>}
            </section>
            <section className="panel detail-full evidence-card">
              <div className="panel-heading">
                <div><p className="eyebrow">EVIDENCE</p><h2>Reports & replay</h2></div>
              </div>
              <div className="evidence-placeholder">
                <div className="evidence-placeholder-row"><FileText size={18} /><span>JSON report</span><strong>{run.evidence ? "Available" : "Not available"}</strong><button className="icon-button" disabled={!run.evidence} onClick={() => run.evidence && downloadEvidence(run.run_id, run.evidence)} title={run.evidence ? "Download API-provided evidence" : "No report source is exposed by the API"}><Download size={15} /></button></div>
                <div className="evidence-placeholder-row"><Terminal size={18} /><span>Replay command</span><strong>{run.replay_command ? "Available" : "Not available"}</strong></div>
              </div>
              {run.replay_command && <pre className="code-block">{run.replay_command}</pre>}
              {run.logs && <pre className="code-block">{run.logs.join("\n")}</pre>}
            </section>
          </div>
        </>
      )}
    </>
  );
}

function Metadata({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="metadata-item">
      <span>{label}</span>
      <strong className={mono ? "mono" : ""}>{value}</strong>
    </div>
  );
}
