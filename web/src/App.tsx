import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Dashboard } from "./pages/Dashboard";
import { Queue } from "./pages/Queue";
import { Works } from "./pages/Works";
import { WorkDetail } from "./pages/WorkDetail";
import { SimilarWorks } from "./pages/SimilarWorks";
import { Stakeholders } from "./pages/Stakeholders";
import { Trends } from "./pages/Trends";
import { EarlyWarning } from "./pages/EarlyWarning";
import { Pipeline } from "./pages/Pipeline";
import { DataQuality } from "./pages/DataQuality";
import { Detectors } from "./pages/Detectors";
import { Methodology } from "./pages/Methodology";
import { EmptyState } from "./components/EmptyState";
import { useScoredState } from "./data/loadScored";

const NAV = [
  { to: "/", label: "Overview", end: true },
  { to: "/queue", label: "Priority queue", end: false },
  { to: "/early-warning", label: "Early warning", end: false },
  { to: "/pipeline", label: "Recommendation pipeline", end: false },
  { to: "/stakeholders", label: "Stakeholder views", end: false },
  { to: "/trends", label: "Trends", end: false },
  { to: "/works", label: "Works", end: false },
  { to: "/similar", label: "Similar works", end: false },
  { to: "/detectors", label: "Detectors", end: false },
  { to: "/quality", label: "Data quality", end: false },
  { to: "/methodology", label: "Methodology", end: false },
];

function Sidebar() {
  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar__brand">
        <div className="sidebar__title">MPLAD-SHIELD</div>
        <div className="sidebar__subtitle">Risk Intelligence &amp; Review Prioritisation</div>
      </div>
      <div className="sidebar__nav">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `sidebar__link${isActive ? " sidebar__link--active" : ""}`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </div>
      <div className="sidebar__footer">
        Indicators flag unusual patterns for human review. They do not establish
        irregularity or fraud.
      </div>
    </nav>
  );
}

export default function App() {
  const state = useScoredState();
  return (
    <div className="shell">
      <Sidebar />
      <main className="main">
        {state.status === "loading" && <EmptyState title="Loading scored works…" />}
        {state.status === "error" && (
          <EmptyState title="Could not load scored.json" body={state.message} />
        )}
        {state.status === "ready" && (
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/queue" element={<Queue />} />
            <Route path="/works" element={<Works />} />
            <Route path="/works/:workId" element={<WorkDetail />} />
            <Route path="/similar" element={<SimilarWorks />} />
            <Route path="/stakeholders" element={<Stakeholders />} />
            <Route path="/trends" element={<Trends />} />
            <Route path="/early-warning" element={<EarlyWarning />} />
            <Route path="/pipeline" element={<Pipeline />} />
            <Route path="/detectors" element={<Detectors />} />
            <Route path="/quality" element={<DataQuality />} />
            <Route path="/methodology" element={<Methodology />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        )}
      </main>
    </div>
  );
}
