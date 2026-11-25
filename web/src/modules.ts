// The six Monicomm modules, in the fixed side-nav order from PROJECT.md section 6A.
export const MODULES = [
  { id: "dashboard", name: "Dashboard" },
  { id: "chat", name: "Chat AI" },
  { id: "analyzer", name: "Analyzer" },
  { id: "investigator", name: "Incident Investigator" },
  { id: "mapper", name: "Mapper" },
  { id: "pcap", name: "Catchup" },
] as const;

export type ModuleId = (typeof MODULES)[number]["id"];
