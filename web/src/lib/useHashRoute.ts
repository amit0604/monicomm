import { useCallback, useEffect, useState } from "react";
import { ADMIN_ENABLED, MODULES, type PageId } from "../modules";

function parse(hash: string): PageId {
  const id = hash.replace(/^#\/?/, "").split("/")[0];
  if (id === "admin" && ADMIN_ENABLED) return id;
  return MODULES.some((m) => m.id === id) ? (id as PageId) : "chat";
}

/** Tiny hash router: #/chat, #/mapper ... Enough until the shell needs nested routes. */
export function useHashRoute() {
  const [route, setRoute] = useState<PageId>(() => parse(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  // Update state right away (hashchange fires asynchronously) and keep the URL shareable.
  const navigate = useCallback((id: PageId) => {
    setRoute(id);
    if (window.location.hash !== `#/${id}`) window.location.hash = `/${id}`;
  }, []);

  return [route, navigate] as const;
}
