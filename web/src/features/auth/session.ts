import { createContext, useContext } from "react";

export type AuthSource = "local" | "ldap" | "sso";

// Mirrors api/app/core/auth.py (User).
export interface User {
  name: string;
  role: "admin" | "technician" | "viewer";
  display_name?: string | null;
  email?: string | null;
  source?: AuthSource;
}

export interface Session {
  user: User;
  signOut: () => void;
}

export const SessionContext = createContext<Session | null>(null);

/** The signed-in user, or null when login is off. */
export const useSession = (): User | null => useContext(SessionContext)?.user ?? null;

/** Signs the user out, or null when login is off. */
export const useSignOut = (): (() => void) | null => useContext(SessionContext)?.signOut ?? null;
