import "@testing-library/jest-dom/vitest";

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = TestResizeObserver;
}

if (typeof URL.createObjectURL !== "function") {
  URL.createObjectURL = (_value: Blob | MediaSource) => `blob:veyra-test/${Math.random().toString(16).slice(2)}`;
  URL.revokeObjectURL = () => undefined;
}
