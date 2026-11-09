import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ShowcaseDemo } from "./showcase-demo";

let reduced = false;
let hidden = false;
let intersections: IntersectionObserverCallback[];
let mediaListeners: Set<() => void>;

beforeEach(() => {
  reduced = false;
  hidden = false;
  intersections = [];
  mediaListeners = new Set();
  document.documentElement.removeAttribute("data-motion");
  vi.spyOn(document, "hidden", "get").mockImplementation(() => hidden);
  vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue(undefined);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.stubGlobal("fetch", vi.fn());
  vi.stubGlobal("matchMedia", vi.fn((media: string) => ({
    media, get matches() { return reduced; }, onchange: null,
    addEventListener: (_: string, cb: () => void) => mediaListeners.add(cb),
    removeEventListener: (_: string, cb: () => void) => mediaListeners.delete(cb),
    addListener() {}, removeListener() {}, dispatchEvent: () => true,
  })));
  vi.stubGlobal("IntersectionObserver", class {
    constructor(cb: IntersectionObserverCallback) { intersections.push(cb); }
    observe = vi.fn();
    disconnect = vi.fn();
  });
});

afterEach(() => {
  expect(fetch).not.toHaveBeenCalled();
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-motion");
});

function video() { return screen.getByLabelText("Veyra gift packaging walkthrough") as HTMLVideoElement; }
function metadata(duration = 40) {
  Object.defineProperties(video(), {
    readyState: { configurable: true, value: HTMLMediaElement.HAVE_METADATA },
    duration: { configurable: true, value: duration },
  });
  fireEvent.loadedMetadata(video());
}

describe("gift packaging film", () => {
  it("autoplays the real gift film muted and inline, loops, and uses no player frame controls", () => {
    render(<ShowcaseDemo locale="en" />);
    expect(video()).toHaveAttribute("autoplay");
    expect(video()).toHaveAttribute("loop");
    expect(video()).toHaveAttribute("playsinline");
    expect(video().muted).toBe(true);
    expect(video()).not.toHaveAttribute("controls");
    expect(video().querySelector("source")).toHaveAttribute("src", "/showcase/veyra-gift-tour.mp4");
    expect(video()).toHaveAttribute("poster", "/showcase/gift-poster.jpg");
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
  });

  it("temporarily suspends hidden/offscreen playback and preserves an explicit user pause", () => {
    render(<ShowcaseDemo locale="en" />);
    fireEvent.play(video());
    hidden = true;
    fireEvent(document, new Event("visibilitychange"));
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
    const playCount = vi.mocked(HTMLMediaElement.prototype.play).mock.calls.length;
    hidden = false;
    fireEvent(document, new Event("visibilitychange"));
    expect(vi.mocked(HTMLMediaElement.prototype.play).mock.calls.length).toBeGreaterThan(playCount);
    fireEvent.play(video());
    fireEvent.click(screen.getByRole("button", { name: "Pause case" }));
    fireEvent.pause(video());
    const pausedCount = vi.mocked(HTMLMediaElement.prototype.play).mock.calls.length;
    act(() => intersections[0]([{ isIntersecting: false } as IntersectionObserverEntry], {} as IntersectionObserver));
    act(() => intersections[0]([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver));
    hidden = true; fireEvent(document, new Event("visibilitychange"));
    hidden = false; fireEvent(document, new Event("visibilitychange"));
    expect(vi.mocked(HTMLMediaElement.prototype.play).mock.calls.length).toBe(pausedCount);
    fireEvent.click(screen.getByRole("button", { name: "Play case" }));
    expect(vi.mocked(HTMLMediaElement.prototype.play).mock.calls.length).toBeGreaterThan(pausedCount);
  });

  it("queues chapters until metadata, clamps to real duration, and keeps playback intent", () => {
    render(<ShowcaseDemo locale="en" />);
    fireEvent.click(screen.getByRole("button", { name: /Visual/ }));
    expect(video().currentTime).toBe(0);
    metadata();
    expect(video().currentTime).toBe(32);
    expect(screen.getByRole("button", { name: /Visual/ })).toHaveAttribute("aria-current", "step");
    const pauses = vi.mocked(HTMLMediaElement.prototype.pause).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /Flow/ }));
    expect(video().currentTime).toBe(8);
    expect(vi.mocked(HTMLMediaElement.prototype.pause).mock.calls.length).toBe(pauses);
    metadata(20);
    fireEvent.click(screen.getByRole("button", { name: /Visual/ }));
    expect(video().currentTime).toBe(19.9);
  });

  it("starts paused for reduced motion and allows intentional manual playback", () => {
    reduced = true;
    render(<ShowcaseDemo locale="en" />);
    expect(video()).not.toHaveAttribute("autoplay");
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Play case" }));
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    fireEvent.play(video());
    act(() => mediaListeners.forEach(cb => cb()));
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled();
  });

  it("offers a manual start when the browser refuses autoplay", async () => {
    vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new Error("NotAllowedError"));
    render(<ShowcaseDemo locale="en" />);
    await waitFor(() => expect(document.querySelector(".showcase-video-start")).toBeInTheDocument());
    fireEvent.click(document.querySelector(".showcase-video-start")!);
    await waitFor(() => expect(document.querySelector(".showcase-video-start")).not.toBeInTheDocument());
  });

  it("shows captions only on request, follows language, and offers real candidate/error recovery", () => {
    const view = render(<ShowcaseDemo locale="en" />);
    const tracks = [{ language: "en", mode: "disabled" }, { language: "zh", mode: "disabled" }];
    Object.defineProperty(video(), "textTracks", { configurable: true, value: tracks });
    fireEvent.click(screen.getByRole("button", { name: "Toggle captions" }));
    expect(tracks.map(track => track.mode)).toEqual(["showing", "disabled"]);
    view.rerender(<ShowcaseDemo locale="zh" />);
    expect(tracks.map(track => track.mode)).toEqual(["disabled", "showing"]);
    fireEvent.error(document.querySelector("video")!);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看设计候选" })).toHaveAttribute("href", "/showcase/gift-output.jpg");
    fireEvent.click(screen.getByRole("button", { name: "重新加载视频" }));
    expect(HTMLMediaElement.prototype.load).toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("offers the actual file and handles a denied fullscreen request", async () => {
    render(<ShowcaseDemo locale="en" />);
    expect(screen.getByRole("link", { name: "Download gift packaging video" })).toHaveAttribute("href", "/showcase/veyra-gift-tour.mp4");
    Object.defineProperty(video(), "requestFullscreen", { value: vi.fn().mockRejectedValue(new Error("denied")) });
    fireEvent.click(screen.getByRole("button", { name: "Watch fullscreen" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Download the video");
  });
});
