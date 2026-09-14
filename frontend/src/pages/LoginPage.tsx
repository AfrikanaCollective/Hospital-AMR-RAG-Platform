import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../useAuth";
import { ApiError } from "../api/client";

// Dev-JWT login (ARCH-011): email only, no password — mints a token for a
// seeded demo user (`make seed`). Unavailable (404) when AUTH_PROVIDER != devjwt,
// so this screen structurally cannot exist against a real deployment.
export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("clinician@example.dev");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <section style={{ maxWidth: 360, margin: "48px auto" }}>
      <h2 style={{ fontSize: 16 }}>Sign in (dev)</h2>
      <p style={{ fontSize: 13, color: "#666" }}>
        Seeded demo users only — no password. Try{" "}
        <code>clinician@example.dev</code>, <code>reviewer1@example.dev</code>, or{" "}
        <code>admin@example.dev</code>.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setError(null);
          setBusy(true);
          try {
            await login(email);
            navigate("/");
          } catch (e) {
            setError(e instanceof ApiError ? e.message : String(e));
          } finally {
            setBusy(false);
          }
        }}
        style={{ display: "grid", gap: 8 }}
      >
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ width: "100%" }}
            required
          />
        </label>
        <button type="submit" disabled={busy || !email.trim()}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        {error && <p style={{ color: "#c0392b", fontSize: 13 }}>{error}</p>}
      </form>
    </section>
  );
}
