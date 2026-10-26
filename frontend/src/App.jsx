import React, { useState } from "react";
import { AuthProvider, useAuth } from "./AuthContext.jsx";
import { CvProvider } from "./CvContext.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Header from "./components/Header.jsx";
import LoginScreen from "./components/LoginScreen.jsx";
import BackendError from "./components/BackendError.jsx";
import ErrorBoundary from "./components/ErrorBoundary.jsx";
import PipelineView from "./components/PipelineView.jsx";
import KnowledgeBase from "./components/KnowledgeBase.jsx";
import BuildProfile from "./components/BuildProfile.jsx";
import RunsView from "./components/RunsView.jsx";
import SettingsView from "./components/SettingsView.jsx";
import Account from "./components/Account.jsx";
import AdminPanel from "./components/AdminPanel.jsx";

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}

// Every view stays mounted (hidden with CSS) so a live run keeps streaming
// while you browse the knowledge base or settings. Each is wrapped in its own
// ErrorBoundary so one bad render takes down one panel, not the whole app.
function Shell() {
  const { identity, ready, bootError, retry } = useAuth();
  const [view, setView] = useState("pipeline");
  // Runs' Resume → Pipeline, which holds the stream. A new object per click.
  const [resumeRequest, setResumeRequest] = useState(null);
  const resume = (id, mode) => {
    setResumeRequest({ id, mode });
    setView("pipeline");
  };

  if (!ready) return <div className="h-screen bg-[#0b0c0e]" />;
  if (bootError) return <BackendError error={bootError} onRetry={retry} />;
  if (!identity) return <LoginScreen />;

  const isAdmin = identity.role === "admin";
  // A non-admin who somehow lands on the admin view falls back to Pipeline.
  const current = view === "admin" && !isAdmin ? "pipeline" : view;

  const panel = (id, node) => (
    <div className={current === id ? "" : "hidden"}>
      <ErrorBoundary name={id}>{node}</ErrorBoundary>
    </div>
  );

  // Keyed by who is signed in, so a different user never sees the last one's CV.
  return (
    <CvProvider key={identity.token_id || identity.identifier}>
      <div className="flex h-screen overflow-hidden">
        <Sidebar view={current} onNavigate={setView} isAdmin={isAdmin} />
        <div className="flex-1 flex flex-col min-w-0">
          <Header onNavigate={setView} />
          <main className="flex-1 overflow-y-auto">
            {panel("pipeline", <PipelineView resumeRequest={resumeRequest} />)}
            {panel("kb", <KnowledgeBase active={current === "kb"} />)}
            {panel("build", <BuildProfile active={current === "build"} />)}
            {panel("runs", <RunsView active={current === "runs"} onResume={resume} />)}
            {panel("account", <Account active={current === "account"} />)}
            {panel("settings", <SettingsView active={current === "settings"} />)}
            {isAdmin && panel("admin", <AdminPanel active={current === "admin"} />)}
          </main>
        </div>
      </div>
    </CvProvider>
  );
}
