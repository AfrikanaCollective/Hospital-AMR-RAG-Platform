import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../useAuth";
import { ApiError } from "../api/client";
import Button from "../components/ui/Button";

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
    <section className="mx-auto mt-12 max-w-[360px]">
      <h2 className="text-base font-semibold text-ink">Sign in (dev)</h2>
      <p className="text-[13px] text-ink-muted">
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
        className="grid gap-2"
      >
        <label className="grid gap-1 text-[13px] text-ink-muted">
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full rounded-lg border border-border bg-surface p-2 text-[15px] text-ink"
            required
          />
        </label>
        <Button type="submit" variant="primary" disabled={busy || !email.trim()}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
        {error && <p className="text-[13px] text-danger">{error}</p>}
      </form>
    </section>
  );
}
