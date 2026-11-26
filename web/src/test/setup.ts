import "@testing-library/jest-dom/vitest";

// jsdom has no layout; the chat message list calls scrollTo.
Element.prototype.scrollTo = function scrollTo() {};

// jsdom has no ResizeObserver; the Mapper's TopologyGraph observes its size. Without this stand-in a test
// that renders the graph throws "ResizeObserver is not defined" (seen as a flaky MapperPage test).
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
