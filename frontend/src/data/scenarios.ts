import type { Scenario } from "../types/api";

// These IDs are manifest entries only. Fixture/oracle assets and Celesto
// execution are unavailable in this checkout; queued record creation is separate.
export const scenarios: Scenario[] = [
  {
    id: "CF-01",
    category: "Leap-year and leap-day logic",
    inputDate: "2024-02-29",
    source: "manifest",
    executionReady: false,
    fixtureOracleAvailableInCheckout: false,
    runRecordCreationAvailable: true,
  },
  {
    id: "CF-17",
    category: "Correct date handling and clean controls",
    inputDate: "2024-03-01",
    source: "manifest",
    executionReady: false,
    fixtureOracleAvailableInCheckout: false,
    runRecordCreationAvailable: true,
  },
];
