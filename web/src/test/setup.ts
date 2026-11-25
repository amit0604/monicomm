import "@testing-library/jest-dom/vitest";

// jsdom has no layout; the chat message list calls scrollTo.
Element.prototype.scrollTo = function scrollTo() {};
