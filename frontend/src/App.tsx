import type { ReactNode } from "react";
import { Link, Navigate, Route, Routes } from "react-router-dom";
import QueryPage from "./pages/QueryPage";
import ReviewPage from "./pages/ReviewPage";
import EscalationsPage from "./pages/EscalationsPage";
import LoginPage from "./pages/LoginPage";
import DisclaimerBanner from "./components/DisclaimerBanner";
import { AuthProvider } from "./AuthContext";
import { useAuth } from "./useAuth";
import { hasRole } from "./auth";

function RequireAuth({ children }: { children: ReactNode }) {
  const { auth } = useAuth();
  if (!auth) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function Shell() {
  const { auth, logout } = useAuth();
  const canReview = hasRole(auth, "reviewer") || hasRole(auth, "admin");

  return (
    <div
      style={{ fontFamily: "system-ui, sans-serif", maxWidth: 960, margin: "0 auto", padding: 16 }}
    >
      <header style={{ display: "flex", gap: 16, alignItems: "baseline" }}>
        <h1 style={{ fontSize: 20 }}>Hospital RAG Platform</h1>
        {auth && (
          <nav style={{ display: "flex", gap: 12 }}>
            <Link to="/">Query</Link>
            {canReview && <Link to="/review">Review queue</Link>}
            {canReview && <Link to="/escalations">Escalations</Link>}
          </nav>
        )}
        <span style={{ marginLeft: "auto", fontSize: 13, color: "#666" }}>
          {auth ? (
            <>
              {auth.roles.join(", ")}{" "}
              <button type="button" onClick={logout} style={{ marginLeft: 8 }}>
                Sign out
              </button>
            </>
          ) : (
            <Link to="/login">Sign in</Link>
          )}
        </span>
      </header>

      {/* Non-removable disclaimer, always mounted on answer-bearing views (ARCH-037). */}
      {auth && <DisclaimerBanner />}

      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <QueryPage />
            </RequireAuth>
          }
        />
        <Route
          path="/review"
          element={
            <RequireAuth>
              <ReviewPage />
            </RequireAuth>
          }
        />
        <Route
          path="/escalations"
          element={
            <RequireAuth>
              <EscalationsPage />
            </RequireAuth>
          }
        />
      </Routes>

      <footer style={{ marginTop: 32, fontSize: 12, color: "#666" }}>
        This system reports and cites guideline content; it does not generate
        independent clinical recommendations.
      </footer>
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Shell />
    </AuthProvider>
  );
}
