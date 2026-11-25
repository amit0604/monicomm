import { useEffect, useState } from 'react';

export const MODULES = ['dashboard', 'chat', 'analyzer', 'investigator', 'mapper', 'pcap'] as const;
export type ModuleId = (typeof MODULES)[number];

function parse(hash: string): ModuleId {
  const id = hash.replace(/^#\/?/, '').split('/')[0];
  return (MODULES as readonly string[]).includes(id) ? (id as ModuleId) : 'chat';
}

/** Tiny hash router: #/chat, #/mapper ... Enough until the shell needs nested routes. */
export function useHashRoute() {
  const [route, setRoute] = useState<ModuleId>(() => parse(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash));
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);

  return route;
}
