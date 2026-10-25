import { useState, type FormEvent } from "react";
import { AlertTriangle, ArrowLeft, ArrowRight, Check, FlaskConical, LoaderCircle } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Notice, PageHeading } from "../components/Primitives";
import { scenarios } from "../data/scenarios";
import { useWorkbenchData } from "../hooks/useWorkbenchData";
import type { CreateRunPayload, RunRecord } from "../types/api";

export function NewInvestigationPage() {
  const navigate = useNavigate();
  const { submitRun } = useWorkbenchData();
  const [selectedScenario, setSelectedScenario] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [createdRun, setCreatedRun] = useState<RunRecord | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError(null);
    if (!scenarios.some((scenario) => scenario.id === selectedScenario)) {
      setError("Select one of the scenarios listed in the repository manifest.");
      return;
    }

    setSubmitting(true);
    const payload: CreateRunPayload = { scenario_id: selectedScenario };
    try {
      const run = await submitRun(payload);
      setCreatedRun(run);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not create the run record.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <PageHeading
        eyebrow="RUN CONFIGURATION"
        title="New investigation"
        description="Choose a scenario and review the record that will be sent to the API."
        actions={<Link className="button button-quiet" to="/investigations"><ArrowLeft size={15} /> Back to runs</Link>}
      />
      <div className="form-layout">
        <section className="panel form-panel">
          {createdRun ? (
            <div className="success-result" role="status">
              <div className="success-icon"><Check size={22} /></div>
              <p className="eyebrow">RECORD CREATED</p>
              <h2>Run record submitted</h2>
              <p>
                <span className="mono">{createdRun.run_id}</span> was accepted by the API. This only creates a run record; investigation execution has not started.
              </p>
              <dl className="scenario-preview">
                <div><dt>Run ID</dt><dd className="mono">{createdRun.run_id}</dd></div>
                <div><dt>Scenario ID</dt><dd>{createdRun.scenario_id ?? createdRun.problem_id ?? "Not returned"}</dd></div>
                <div><dt>Status</dt><dd>{createdRun.status ?? createdRun.state ?? "Not returned"}</dd></div>
                <div><dt>Created at</dt><dd>{createdRun.created_at ?? "Not returned"}</dd></div>
              </dl>
              <div className="form-actions">
                <button className="button button-primary" onClick={() => navigate(`/investigations/${encodeURIComponent(createdRun.run_id)}`)} type="button">View run record <ArrowRight size={15} /></button>
                <Link className="button button-secondary" to="/investigations">Run history</Link>
              </div>
            </div>
          ) : (
            <form onSubmit={(event) => void submit(event)}>
              <div className="form-section-title">
                <span className="section-icon"><FlaskConical size={17} /></span>
                <div>
                  <h2>Scenario</h2>
                  <p>Select a scenario ID present in the project manifest.</p>
                </div>
              </div>
              <label className="field-label" htmlFor="scenario">Scenario ID <span className="required">*</span></label>
              <select
                className="form-control"
                id="scenario"
                onChange={(event) => setSelectedScenario(event.target.value)}
                required
                value={selectedScenario}
              >
                <option disabled value="">Choose a scenario…</option>
                {scenarios.map((scenario) => (
                  <option key={scenario.id} value={scenario.id}>{scenario.id} · {scenario.category}</option>
                ))}
              </select>
              {selectedScenario && (
                <div className="scenario-preview">
                  <div><span>Manifest listing</span><strong>{selectedScenario}</strong></div>
                  <div><span>Reference date</span><strong>{scenarios.find((item) => item.id === selectedScenario)?.inputDate}</strong></div>
                  <div><span>Fixture/oracle files in this checkout</span><strong className="text-warning">Not available</strong></div>
                  <div><span>Celesto execution</span><strong className="text-warning">Not configured or verified</strong></div>
                  <div><span>Queued run-record creation</span><strong>Available through the API</strong></div>
                </div>
              )}
              <Notice tone="warning">
                <AlertTriangle size={16} />
                <span>This Windows checkout does not contain <code>fixtures/</code> or <code>oracle/</code> directories. A scenario being listed in the manifest does not confirm assets or Celesto execution readiness. Creating a queued run record is available independently.</span>
              </Notice>
              <div className="form-divider" />
              <div className="form-section-title">
                <span className="section-icon"><FlaskConical size={17} /></span>
                <div>
                  <h2>Submission behavior</h2>
                  <p>The API currently accepts run metadata; execution is a later integration phase.</p>
                </div>
              </div>
              <Notice>
                <AlertTriangle size={16} />
                <span>Submitting creates a queued run record. It does not launch Celesto, run date tests, or produce a verdict or report.</span>
              </Notice>
              {error && <div className="inline-alert error-alert" role="alert">{error}</div>}
              <div className="form-actions">
                <Link className="button button-secondary" to="/investigations">Cancel</Link>
                <button className="button button-primary" disabled={submitting || !selectedScenario} type="submit">
                  {submitting ? <LoaderCircle className="spin" size={16} /> : <FlaskConical size={16} />}
                  {submitting ? "Submitting…" : "Create run record"}
                </button>
              </div>
            </form>
          )}
        </section>

        <aside className="panel request-panel">
          <p className="eyebrow">REQUEST PREVIEW</p>
          <h2>What will be sent</h2>
          <p className="panel-subtitle">Sensitive credentials never belong in frontend configuration.</p>
          <pre className="code-block">{JSON.stringify({
            scenario_id: selectedScenario || "<select scenario>",
          }, null, 2)}</pre>
          <div className="request-note">
            <strong>Backend contract</strong>
            <span>The selected <code>scenario_id</code> is sent to the API, which creates a queued record. The investigation engine is not invoked by this request.</span>
          </div>
        </aside>
      </div>
    </>
  );
}
