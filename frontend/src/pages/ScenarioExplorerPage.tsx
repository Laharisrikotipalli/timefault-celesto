import { ArrowRight, CalendarDays, CircleAlert, FlaskConical } from "lucide-react";
import { Link } from "react-router-dom";
import { EmptyState, Notice, PageHeading } from "../components/Primitives";
import { scenarios } from "../data/scenarios";
import { useWorkbenchData } from "../hooks/useWorkbenchData";

export function ScenarioExplorerPage() {
  const { runs } = useWorkbenchData();
  return (
    <>
      <PageHeading
        eyebrow="SCENARIO CATALOG"
        title="Scenario Explorer"
        description="Manifest-listed scenario metadata available in this repository checkout."
      />
      <Notice tone="warning">
        <CircleAlert size={16} />
        <span>This Windows checkout does not contain <code>fixtures/</code> or <code>oracle/</code> directories. Entries below are listed in the manifest only; this does not establish Celesto execution readiness. Queued run-record creation is available through the API.</span>
      </Notice>
      {scenarios.length ? (
        <div className="scenario-grid">
          {scenarios.map((scenario) => {
            const relatedRuns = runs.filter((run) => (run.scenario_id ?? run.problem_id) === scenario.id).length;
            return (
              <article className="panel scenario-card" key={scenario.id}>
                <div className="scenario-card-top">
                  <span className="scenario-card-icon"><FlaskConical size={18} /></span>
                  <span className="scenario-id mono">{scenario.id}</span>
                </div>
                <h2>{scenario.category}</h2>
                <div className="scenario-detail"><CalendarDays size={15} /><span>Manifest reference date</span><strong>{scenario.inputDate}</strong></div>
                <div className="scenario-detail"><FlaskConical size={15} /><span>Run records</span><strong>{relatedRuns}</strong></div>
                <div className="scenario-readiness"><span className="status-dot muted-dot" />Manifest listed · assets unavailable in this checkout · execution not verified</div>
                <Link className="scenario-open" to="/investigations/new">Create run record <ArrowRight size={14} /></Link>
              </article>
            );
          })}
        </div>
      ) : (
        <section className="panel"><EmptyState icon={<FlaskConical />} title="No manifest scenarios" description="No scenario definitions are available in this checkout." /></section>
      )}
    </>
  );
}
