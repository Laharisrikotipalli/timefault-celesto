import { Activity, CalendarClock, CircleHelp, Clock3 } from "lucide-react";
import { EmptyState, Notice, PageHeading } from "../components/Primitives";
import { useWorkbenchData } from "../hooks/useWorkbenchData";

export function FailureAnalysisPage() {
  const { runs, runsLoading, runsError } = useWorkbenchData();
  const runWithResults = runs.find((run) => run.tested_results?.length);
  const runWithDates = runs.find((run) => run.tested_dates?.length);
  return (
    <>
      <PageHeading
        eyebrow="TEMPORAL DIAGNOSTICS"
        title="Failure Analysis"
        description="A workspace for date windows, recovery boundaries, and clock experiments."
      />
      {runsError && <Notice tone="warning">Run records could not be checked for analysis data.</Notice>}
      <Notice>
        <CircleHelp size={16} />
        <span>Temporal analysis is a placeholder until the backend provides tested dates and verdict evidence. No example failure windows are fabricated.</span>
      </Notice>
      <section className="panel analysis-panel">
        <div className="panel-heading">
          <div><p className="eyebrow">DATE OUTCOME TIMELINE</p><h2>Observed pass / fail window</h2><p className="panel-subtitle">The timeline will render only from real tested-date results.</p></div>
          <span className="panel-icon"><CalendarClock size={17} /></span>
        </div>
        {runsLoading ? (
          <div className="analysis-placeholder"><div className="skeleton-line" /><div className="skeleton-line short" /></div>
        ) : runWithResults ? (
          <div className="result-timeline">
            <div className="result-timeline-track">
              {runWithResults.tested_results?.map((result) => (
                <div className="result-point" key={`${runWithResults.run_id}-${result.date}`}>
                  <span className={`result-marker ${result.outcome}`} />
                  <strong>{result.date}</strong>
                  <small>{result.outcome}</small>
                </div>
              ))}
            </div>
            <p className="health-footnote">Observed results for run <code>{runWithResults.run_id}</code>.</p>
          </div>
        ) : runWithDates ? (
          <div className="analysis-placeholder">
            <EmptyState icon={<Activity />} title="Test dates available; outcomes are not" description="The API returned tested dates without pass/fail classifications." />
            <div className="tested-date-list">{runWithDates.tested_dates?.map((date) => <span className="date-chip" key={date}>{date}</span>)}</div>
          </div>
        ) : (
          <div className="timeline-empty">
            <div className="timeline-axis"><span /><span /><span /><span /><span /></div>
            <EmptyState icon={<Clock3 />} title="Analysis not available yet" description="First failure, last failure, recovery date, and tested regions will appear here when the API exposes investigation results." />
          </div>
        )}
      </section>
      <div className="analysis-card-grid">
        {["First failure", "Last failure", "Recovery boundary"].map((label) => (
          <article className="panel analysis-fact-card" key={label}>
            <span className="panel-icon"><CalendarClock size={17} /></span>
            <span>{label}</span>
            <strong>Not available</strong>
            <small>Not returned by current API</small>
          </article>
        ))}
      </div>
      <section className="panel experiment-panel">
        <p className="eyebrow">CLOCK EXPERIMENTS</p>
        <h2>Temporal controls</h2>
        <div className="experiment-chips">
          {["Frozen clock", "Backward jump", "Clock drift"].map((item) => <span className="experiment-chip" key={item}>{item}<small>Not reported</small></span>)}
        </div>
      </section>
    </>
  );
}
