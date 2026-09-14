// Dev-JWT auth (ARCH-011). Token lives in localStorage; `Authorization: Bearer`
// is attached to every API call by api/client.ts. `parseRoles` decodes the
// JWT payload client-side for UI purposes ONLY (which nav links to show) —
// it does not verify the signature, so it must never be treated as an
// authorization decision; the backend (`app.api.deps.require_role`) is the
// only real enforcement point.

const STORAGE_KEY = "hrag_token";

export interface StoredAuth {
  token: string;
  userId: string;
  roles: string[];
}

export function getStoredAuth(): StoredAuth | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredAuth;
  } catch {
    return null;
  }
}

export function setStoredAuth(auth: StoredAuth): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(auth));
}

export function clearStoredAuth(): void {
  localStorage.removeItem(STORAGE_KEY);
}

export function hasRole(auth: StoredAuth | null, role: string): boolean {
  return !!auth && auth.roles.includes(role);
}
