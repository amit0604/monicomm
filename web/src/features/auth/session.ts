import { createContext, useContext } from "react";

export interface User {
  name: string;
  role: "admin" | "technician" | "viewer";
}

export const SessionContext = createContext<User | null>(null);

/** The signed-in user, or null when login is off. */
export const useSession = () => useContext(SessionContext);
