import { useCallback, useEffect, useState } from "react";
import { MODULES, type ModuleId } from "../modules";

function parse(hash: string): ModuleId {
  const id = hash.replace(/^#\/?/, "").split("/")[0];
  return MODULES.some((m) => m.id === id) ? (id as ModuleId) : "chat";
}

/** Tiny hash router: #/chat, #/mapper ... Enough until the shell needs nested routes. */
export function useHashRoute() {
  const [route, setRoute] = useState<ModuleId>(() => parse(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  // Update state right away (hashchange fires asynchronously) and keep the URL shareable.
  const navigate = useCallback((id: ModuleId) => {
    setRoute(id);
    if (window.location.hash !== `#/${id}`) window.location.hash = `/${id}`;
  }, []);

  return [route, navigate] as const;
}
