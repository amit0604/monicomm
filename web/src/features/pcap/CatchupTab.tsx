import { useEffect, useRef } from "react";
import { mountCatchup, type CatchupTabHandle } from "./legacy/index.js";
import "./legacy/catchup.css";

// Catchup (PCAP investigation) tab. Hosts the temporary plain-JS UI in legacy/
// until it is ported to React components (PROJECT.md 2.6).
export function CatchupTab({ theme }: { theme: string }) {
  const host = useRef<HTMLDivElement>(null);
  const tab = useRef<CatchupTabHandle | null>(null);

  useEffect(() => {
    tab.current = mountCatchup(host.current!, { apiBase: "/api/v1/pcap" });
    return () => {
      tab.current?.destroy();
      tab.current = null;
    };
  }, []);

  // Graph and chart colors are read from the tokens, so redraw when the theme changes.
  useEffect(() => {
    tab.current?.reload();
  }, [theme]);

  return <div ref={host} />;
}
