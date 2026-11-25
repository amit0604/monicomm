// Types for the plain-JS Catchup tab (index.js). Remove with legacy/ after the React port.
export interface CatchupTabHandle {
  open(id: string): Promise<void>;
  /** Re-read design tokens after a theme switch. */
  reload(): void;
  destroy(): void;
}

export function mountCatchup(root: HTMLElement, options?: { apiBase?: string }): CatchupTabHandle;
