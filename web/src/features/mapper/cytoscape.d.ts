// The part of the Cytoscape.js API the Mapper uses. cytoscape ships no types, and adding
// @types/cytoscape would need a new dependency; if one is added later, delete this file.
declare module "cytoscape" {
  export interface ElementDefinition {
    group: "nodes" | "edges";
    data: Record<string, unknown> & { id: string };
    classes?: string;
  }
  export interface Collection {
    length: number;
    remove(): Collection;
    select(): Collection;
    unselect(): Collection;
  }
  export interface EventObject {
    target: { id(): string } | Core;
  }
  export interface Core {
    add(elements: ElementDefinition[]): Collection;
    elements(selector?: string): Collection;
    getElementById(id: string): Collection;
    layout(options: Record<string, unknown>): { run(): void };
    style(stylesheet: Record<string, unknown>[]): unknown;
    on(events: string, selector: string, handler: (event: EventObject) => void): Core;
    on(events: string, handler: (event: EventObject) => void): Core;
    fit(elements?: Collection, padding?: number): void;
    resize(): void;
    destroy(): void;
  }
  export default function cytoscape(options: Record<string, unknown>): Core;
}
