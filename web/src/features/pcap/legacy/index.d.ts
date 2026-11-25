// Types for the plain-JS Chatchup tab (index.js). Remove with legacy/ after the React port.
export interface ChatchupTabHandle {
  open(id: string): Promise<void>;
  /** Re-read design tokens after a theme switch. */
  reload(): void;
  destroy(): void;
}

export function mountChatchup(root: HTMLElement, options?: { apiBase?: string }): ChatchupTabHandle;
