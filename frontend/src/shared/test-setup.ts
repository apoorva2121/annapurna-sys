// Loaded by vitest for every test file (see vite.config.ts). Adds the DOM matchers that let a test
// assert what a user can actually see, e.g. toBeInTheDocument.
import '@testing-library/jest-dom/vitest';

// jsdom implements neither of the browser APIs Radix reaches for when it measures or positions a
// floating element. Without them, any test rendering a Switch, a Select or a Dialog dies with
// "ResizeObserver is not defined" before it can assert anything — a failure about the environment
// that reads like a failure about the component.
//
// Stubs rather than implementations, deliberately: jsdom has no layout, so a faithful
// ResizeObserver would report zero for everything and be no more truthful than this. Anything that
// genuinely depends on measured size cannot be tested here and belongs in a browser test.
class StubResizeObserver implements ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

// Assigned unconditionally rather than guarded. TypeScript's DOM library says both of these always
// exist, so a `??=` guard reads to the linter as dead code — but jsdom genuinely does not implement
// them, which is the entire reason this file exists. Overwriting in a test setup file is harmless;
// nothing here runs in a browser.
globalThis.ResizeObserver = StubResizeObserver;

// Radix's Select calls this to scroll the highlighted item into view.
Element.prototype.scrollIntoView = (): void => {};
