import { useMemo, useState, type ReactNode } from "react";
import { clearStoredAuth, getStoredAuth, setStoredAuth, type StoredAuth } from "./auth";
import { api } from "./api/client";
import { AuthContext, type AuthContextValue } from "./useAuth";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuth] = useState<StoredAuth | null>(getStoredAuth());

  const value = useMemo<AuthContextValue>(
    () => ({
      auth,
      login: async (email: string) => {
        const resp = await api.devLogin(email);
        const next: StoredAuth = {
          token: resp.access_token,
          userId: resp.user_id,
          roles: resp.roles,
        };
        setStoredAuth(next);
        setAuth(next);
      },
      logout: () => {
        clearStoredAuth();
        setAuth(null);
      },
    }),
    [auth],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
