import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { createRun as postRun, getHealth, getRuns } from "../services/api";
import type {
  CreateRunPayload,
  HealthResponse,
  RunRecord,
} from "../types/api";

interface WorkbenchData {
  runs: RunRecord[];
  runsLoading: boolean;
  runsError: string | null;
  health: HealthResponse | null;
  healthLoading: boolean;
  healthError: string | null;
  refresh: () => Promise<void>;
  submitRun: (payload: CreateRunPayload) => Promise<RunRecord>;
}

const WorkbenchContext = createContext<WorkbenchData | null>(null);

export function WorkbenchDataProvider({ children }: { children: ReactNode }) {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setRunsLoading(true);
    setHealthLoading(true);
    setRunsError(null);
    setHealthError(null);

    const [runResult, healthResult] = await Promise.allSettled([
      getRuns(),
      getHealth(),
    ]);

    if (runResult.status === "fulfilled") {
      setRuns(runResult.value);
    } else {
      setRunsError(
        runResult.reason instanceof Error
          ? runResult.reason.message
          : "Could not load investigations.",
      );
    }
    if (healthResult.status === "fulfilled") {
      setHealth(healthResult.value);
    } else {
      setHealthError(
        healthResult.reason instanceof Error
          ? healthResult.reason.message
          : "Could not check API health.",
      );
    }
    setRunsLoading(false);
    setHealthLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const submitRun = useCallback(
    async (payload: CreateRunPayload) => {
      const run = await postRun(payload);
      setRuns((current) => [
        run,
        ...current.filter((item) => item.run_id !== run.run_id),
      ]);
      await refresh();
      return run;
    },
    [refresh],
  );

  const value = useMemo(
    () => ({
      runs,
      runsLoading,
      runsError,
      health,
      healthLoading,
      healthError,
      refresh,
      submitRun,
    }),
    [
      runs,
      runsLoading,
      runsError,
      health,
      healthLoading,
      healthError,
      refresh,
      submitRun,
    ],
  );

  return (
    <WorkbenchContext.Provider value={value}>
      {children}
    </WorkbenchContext.Provider>
  );
}

export function useWorkbenchData(): WorkbenchData {
  const value = useContext(WorkbenchContext);
  if (!value) {
    throw new Error("useWorkbenchData must be used inside WorkbenchDataProvider.");
  }
  return value;
}
