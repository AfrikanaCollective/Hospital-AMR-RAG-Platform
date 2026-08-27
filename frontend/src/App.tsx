import { Link, Route, Routes } from "react-router-dom";
import QueryPage from "./pages/QueryPage";
import ReviewPage from "./pages/ReviewPage";
import DisclaimerBanner from "./components/DisclaimerBanner";

// Phase 1 UI shell (PRD-107, ARCH-010). Screens are stubs; the structure shows
// the query interface, citation display, and all three HITL interaction modes.
export default function App() {
  return (
    <div style={{ fontFamily: "system-ui, sans-serif", maxWidth: 960, margin: "0 auto", padding: 16 }}>
      <header style={{ display: "flex", gap: 16, alignItems: "baseline" }}>
        <h1 style={{ fontSize: 20 }}>Hospital RAG Platform</h1>
        <nav style={{ display: "flex", gap: 12 }}>
          <Link to="/">Query</Link>
          <Link to="/review">Review queue</Link>
        </nav>
      </header>

      {/* Non-removable disclaimer, always mounted on answer-bearing views (ARCH-037). */}
      <DisclaimerBanner />

      <Routes>
        <Route path="/" element={<QueryPage />} />
        <Route path="/review" element={<ReviewPage />} />
      </Routes>

      <footer style={{ marginTop: 32, fontSize: 12, color: "#666" }}>
        Phase 1 scaffold — screens are stubs. This system reports and cites
        guideline content; it does not generate clinical recommendations.
      </footer>
    </div>
  );
}
