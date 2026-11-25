// The six Monicomm modules, in the fixed side-nav order from PROJECT.md section 6A.
export const MODULES = [
  { id: "dashboard", name: "Dashboard" },
  { id: "chat", name: "Chat AI" },
  { id: "analyzer", name: "Analyzer" },
  { id: "investigator", name: "Incident Investigator" },
  { id: "mapper", name: "Mapper" },
  { id: "pcap", name: "Chatchup" },
] as const;

export type ModuleId = (typeof MODULES)[number]["id"];

/** A page of the app: a module, or the admin page (not a module). */
export type PageId = ModuleId | "admin";

/** The admin page needs login, which is dev-only for now. The api enforces this too. */
export const ADMIN_ENABLED =
  import.meta.env.DEV && import.meta.env.VITE_AUTH_PROVIDER === "firebase";
