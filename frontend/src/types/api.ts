export interface RunRecord {
  run_id: string;
  scenario_id?: string;
  problem_id?: string;
  status?: string;
  state?: string;
  created_at?: string;
  verdict?: string;
  tested_dates?: string[];
  tested_results?: Array<{
    date: string;
    outcome: "pass" | "fail" | "inconclusive" | "error";
  }>;
  first_failure_date?: string;
  last_failure_date?: string;
  recovery_date?: string;
  explanation?: string;
  logs?: string[];
  replay_command?: string;
  evidence?: Record<string, unknown>;
}

export interface CreateRunPayload {
  scenario_id: string;
}

export interface HealthResponse {
  status: string;
  database?: string;
}

export interface Scenario {
  id: string;
  category: string;
  inputDate: string;
  source: "manifest";
  executionReady: false;
  fixtureOracleAvailableInCheckout: false;
  runRecordCreationAvailable: true;
}
