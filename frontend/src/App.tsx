import { lazy } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { WorkbenchDataProvider } from "./hooks/useWorkbenchData";

const EvidencePage = lazy(() =>
  import("./pages/EvidencePage").then((module) => ({
    default: module.EvidencePage,
  })),
);
const FailureAnalysisPage = lazy(() =>
  import("./pages/FailureAnalysisPage").then((module) => ({
    default: module.FailureAnalysisPage,
  })),
);
const InvestigationDetailPage = lazy(() =>
  import("./pages/InvestigationDetailPage").then((module) => ({
    default: module.InvestigationDetailPage,
  })),
);
const InvestigationsPage = lazy(() =>
  import("./pages/InvestigationsPage").then((module) => ({
    default: module.InvestigationsPage,
  })),
);
const NewInvestigationPage = lazy(() =>
  import("./pages/NewInvestigationPage").then((module) => ({
    default: module.NewInvestigationPage,
  })),
);
const OverviewPage = lazy(() =>
  import("./pages/OverviewPage").then((module) => ({
    default: module.OverviewPage,
  })),
);
const ScenarioExplorerPage = lazy(() =>
  import("./pages/ScenarioExplorerPage").then((module) => ({
    default: module.ScenarioExplorerPage,
  })),
);
const SettingsPage = lazy(() =>
  import("./pages/SettingsPage").then((module) => ({
    default: module.SettingsPage,
  })),
);

export default function App() {
  return (
    <BrowserRouter>
      <WorkbenchDataProvider>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<OverviewPage />} />
            <Route path="investigations" element={<InvestigationsPage />} />
            <Route path="investigations/new" element={<NewInvestigationPage />} />
            <Route path="investigations/:runId" element={<InvestigationDetailPage />} />
            <Route path="scenarios" element={<ScenarioExplorerPage />} />
            <Route path="analysis" element={<FailureAnalysisPage />} />
            <Route path="evidence" element={<EvidencePage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate replace to="/" />} />
          </Route>
        </Routes>
      </WorkbenchDataProvider>
    </BrowserRouter>
  );
}
