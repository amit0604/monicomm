import { useEffect, useRef } from "react";
import { mountChatchup, type ChatchupTabHandle } from "./legacy/index.js";
import "./legacy/chatchup.css";

// Chatchup (PCAP investigation) tab. Hosts the temporary plain-JS UI in legacy/
// until it is ported to React components (PROJECT.md 2.6).
export function ChatchupTab({ theme }: { theme: string }) {
  const host = useRef<HTMLDivElement>(null);
  const tab = useRef<ChatchupTabHandle | null>(null);

  useEffect(() => {
    tab.current = mountChatchup(host.current!, { apiBase: "/api/v1/pcap" });
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
