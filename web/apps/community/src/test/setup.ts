import "@testing-library/jest-dom/vitest";

// jsdom has no media-query implementation. Individual interaction tests can override it.
if (!window.matchMedia) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    writable: true,
    value: (media: string): MediaQueryList => ({
      matches: false, media, onchange: null,
      addListener() {}, removeListener() {},
      addEventListener() {}, removeEventListener() {}, dispatchEvent: () => true,
    }),
  });
}

for (const method of ["scrollIntoView", "scrollTo"] as const) {
  if (!HTMLElement.prototype[method]) {
    Object.defineProperty(HTMLElement.prototype, method, { configurable: true, writable: true, value() {} });
  }
}

// jsdom has no video decoder; real playback is checked in the browser.
Object.defineProperties(HTMLMediaElement.prototype, {
  play: { configurable: true, writable: true, value: () => Promise.resolve() },
  pause: { configurable: true, writable: true, value() {} },
  load: { configurable: true, writable: true, value() {} },
});
