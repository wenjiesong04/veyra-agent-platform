import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

export const COLLAPSIBLE_NAV_SECTIONS = ["pinned", "projects", "recent"] as const;
export type CollapsibleNavSection = (typeof COLLAPSIBLE_NAV_SECTIONS)[number];
export type NavScrollFoldState = Record<CollapsibleNavSection, boolean>;
export type NavScrollDirection = "down" | "up" | "none";

export const NAV_STICKY_HEADING = 22;
export const NAV_STICKY_PAD = 8;
export const NAV_STICKY_FIRST = NAV_STICKY_PAD * 2 + NAV_STICKY_HEADING;
export const NAV_STICKY_REST = NAV_STICKY_FIRST + 1;
export const NAV_SCROLL_COLLAPSE_THRESHOLD = 12;
export const NAV_SCROLL_EXPAND_THRESHOLD = 40;
export const NAV_SCROLL_EXPAND_ARM_SLACK = 24;
export const NAV_SCROLL_TOP_EPSILON = 2;
export const NAV_SCROLL_MANUAL_LOCK_MS = 480;
export const NAV_SCROLL_ANIMATION_MS = 180;

export function isCollapsibleNavSection(section?: string): section is CollapsibleNavSection {
  return section === "pinned" || section === "projects" || section === "recent";
}

export function emptyNavScrollFolds(): NavScrollFoldState {
  return { pinned: false, projects: false, recent: false };
}

export type NavStickyOffsets = Record<CollapsibleNavSection, number>;

/**
 * Compute sticky slots from the section groups that are actually rendered.
 *
 * The old implementation assumed that all three groups were present. That
 * left an empty pinned slot when a user had no pinned Project and also put
 * Recent behind an invisible header stack.
 */
export function stickyOffsetsForSections(sections: readonly CollapsibleNavSection[]): NavStickyOffsets {
  const offsets: NavStickyOffsets = { pinned: 0, projects: 0, recent: 0 };
  const seen = new Set<CollapsibleNavSection>();
  let top = 0;
  for (const section of sections) {
    if (seen.has(section)) continue;
    seen.add(section);
    offsets[section] = top;
    top += section === "pinned" ? NAV_STICKY_FIRST : NAV_STICKY_REST;
  }
  return offsets;
}

export type NavScrollSectionSnapshot = {
  section: CollapsibleNavSection;
  header: HTMLElement;
  body: HTMLElement;
  stickyTop: number;
  headerHeight: number;
  bodyBottom: number;
  bodyHeight: number;
};

export type NavScrollFoldPlan = {
  autoCollapsed: NavScrollFoldState;
  action: "collapse" | "expand" | null;
  section: CollapsibleNavSection | null;
};

export type NavScrollFoldInput = {
  scrollTop: number;
  direction: NavScrollDirection;
  sections: Array<Pick<NavScrollSectionSnapshot, "section" | "stickyTop" | "headerHeight" | "bodyBottom" | "bodyHeight">>;
  manualCollapsed: NavScrollFoldState;
  autoCollapsed: NavScrollFoldState;
  allowExpand: boolean;
  atTopWheelUp?: boolean;
  collapseThreshold?: number;
  expandThreshold?: number;
};

function cloneFolds(state: NavScrollFoldState): NavScrollFoldState {
  return { pinned: state.pinned, projects: state.projects, recent: state.recent };
}

function renderedNavSections(scroller: HTMLElement): CollapsibleNavSection[] {
  const sections: CollapsibleNavSection[] = [];
  for (const group of scroller.querySelectorAll<HTMLElement>("[data-nav-section]")) {
    const section = group.dataset.navSection;
    if (isCollapsibleNavSection(section)) sections.push(section);
  }
  return sections;
}

export function measureNavScrollSections(scroller: HTMLElement): NavScrollSectionSnapshot[] {
  const rootTop = scroller.getBoundingClientRect().top;
  const stickyOffsets = stickyOffsetsForSections(renderedNavSections(scroller));
  const snapshots: NavScrollSectionSnapshot[] = [];
  for (const group of scroller.querySelectorAll<HTMLElement>("[data-nav-section]")) {
    const section = group.dataset.navSection;
    if (!isCollapsibleNavSection(section)) continue;
    const header = group.querySelector<HTMLElement>(":scope > .nav-group-chrome");
    const body = group.querySelector<HTMLElement>(":scope > .nav-group-body");
    const inner = body?.querySelector<HTMLElement>(":scope > .nav-group-body-inner") ?? body;
    if (!header || !body || !inner) continue;
    const headerRect = header.getBoundingClientRect();
    const bodyRect = body.getBoundingClientRect();
    snapshots.push({
      section,
      header,
      body,
      stickyTop: stickyOffsets[section],
      headerHeight: headerRect.height,
      bodyBottom: bodyRect.bottom - rootTop,
      bodyHeight: inner.scrollHeight,
    });
  }
  return snapshots;
}

export function planNavScrollFold(input: NavScrollFoldInput): NavScrollFoldPlan {
  const collapseThreshold = input.collapseThreshold ?? NAV_SCROLL_COLLAPSE_THRESHOLD;
  const expandThreshold = input.expandThreshold ?? NAV_SCROLL_EXPAND_THRESHOLD;
  const next = cloneFolds(input.autoCollapsed);
  for (const section of COLLAPSIBLE_NAV_SECTIONS) {
    if (input.manualCollapsed[section]) next[section] = false;
  }

  const idle = { autoCollapsed: next, action: null, section: null } satisfies NavScrollFoldPlan;
  const live = input.sections.filter((section) => COLLAPSIBLE_NAV_SECTIONS.includes(section.section));
  if (live.length < 2) return idle;

  const commit = (section: CollapsibleNavSection, folded: boolean, action: "collapse" | "expand"): NavScrollFoldPlan => {
    if (next[section] === folded) return idle;
    next[section] = folded;
    return { autoCollapsed: next, action, section };
  };

  if (input.direction === "down") {
    for (let index = 0; index < live.length - 1; index += 1) {
      const current = live[index]!;
      if (input.manualCollapsed[current.section] || next[current.section]) continue;
      if (current.bodyHeight <= 0) continue;
      const cover = current.stickyTop + current.headerHeight + collapseThreshold;
      if (current.bodyBottom <= cover) return commit(current.section, true, "collapse");
    }
    return idle;
  }

  const wantsExpand = input.atTopWheelUp === true || (input.direction === "up" && input.allowExpand && input.scrollTop <= expandThreshold);
  if (!wantsExpand) return idle;

  for (let index = live.length - 2; index >= 0; index -= 1) {
    const current = live[index]!;
    if (input.manualCollapsed[current.section] || !next[current.section]) continue;
    return commit(current.section, false, "expand");
  }

  return idle;
}

function retainAnchor(scroller: HTMLElement, anchor: { node: HTMLElement; top: number }) {
  if (!anchor.node.isConnected) return;
  const delta = anchor.node.getBoundingClientRect().top - anchor.top;
  if (Math.abs(delta) > 0.5) scroller.scrollTop += delta;
}

type ScrollRuntime = {
  lastScrollTop: number;
  lockUntil: number;
  ignoreScroll: boolean;
  allowExpand: boolean;
  stopAnchor: (() => void) | null;
};

function createRuntime(): ScrollRuntime {
  return {
    lastScrollTop: 0,
    lockUntil: 0,
    ignoreScroll: false,
    allowExpand: false,
    stopAnchor: null,
  };
}

export function useNavScrollAccordion(
  scrollerRef: RefObject<HTMLElement | null>,
  manualCollapsed: NavScrollFoldState,
  bindKey = 0,
): {
  autoCollapsed: NavScrollFoldState;
  lockManualInteraction: (section?: CollapsibleNavSection) => void;
  scrollSectionIntoSlot: (section: CollapsibleNavSection) => void;
} {
  const [autoCollapsed, setAutoCollapsed] = useState(emptyNavScrollFolds);
  const autoRef = useRef(autoCollapsed);
  const manualRef = useRef(manualCollapsed);
  const runtimeRef = useRef<ScrollRuntime>(createRuntime());
  const pendingAnchorRef = useRef<{ node: HTMLElement; top: number } | null>(null);
  autoRef.current = autoCollapsed;
  manualRef.current = manualCollapsed;

  const lockManualInteraction = useCallback((section?: CollapsibleNavSection) => {
    runtimeRef.current.lockUntil = performance.now() + NAV_SCROLL_MANUAL_LOCK_MS;
    if (section && autoRef.current[section]) {
      const next = { ...autoRef.current, [section]: false };
      autoRef.current = next;
      setAutoCollapsed(next);
    }
  }, []);

  const scrollSectionIntoSlot = useCallback((section: CollapsibleNavSection) => {
    const scroller = scrollerRef.current;
    const header = scroller?.querySelector<HTMLElement>(`[data-nav-section="${section}"] > .nav-group-chrome`);
    if (!scroller || !header) return;
    const stickyTop = stickyOffsetsForSections(renderedNavSections(scroller))[section];
    runtimeRef.current.ignoreScroll = true;
    scroller.scrollTop += header.getBoundingClientRect().top - scroller.getBoundingClientRect().top - stickyTop;
    runtimeRef.current.lastScrollTop = scroller.scrollTop;
    window.requestAnimationFrame(() => {
      runtimeRef.current.ignoreScroll = false;
      runtimeRef.current.lastScrollTop = scroller.scrollTop;
    });
  }, [scrollerRef]);

  useEffect(() => {
    setAutoCollapsed((current) => {
      let changed = false;
      const next = cloneFolds(current);
      for (const section of COLLAPSIBLE_NAV_SECTIONS) {
        if (manualCollapsed[section] && next[section]) {
          next[section] = false;
          changed = true;
        }
      }
      if (!changed) return current;
      autoRef.current = next;
      return next;
    });
  }, [manualCollapsed]);

  useLayoutEffect(() => {
    const scroller = scrollerRef.current;
    const anchor = pendingAnchorRef.current;
    pendingAnchorRef.current = null;
    runtimeRef.current.stopAnchor?.();
    runtimeRef.current.stopAnchor = null;
    if (!scroller) {
      runtimeRef.current.ignoreScroll = false;
      return;
    }
    if (!anchor) {
      runtimeRef.current.ignoreScroll = false;
      runtimeRef.current.lastScrollTop = scroller.scrollTop;
      return;
    }
    retainAnchor(scroller, anchor);
    if (typeof ResizeObserver !== "function") {
      runtimeRef.current.ignoreScroll = false;
      runtimeRef.current.lastScrollTop = scroller.scrollTop;
      return;
    }
    const observer = new ResizeObserver(() => retainAnchor(scroller, anchor));
    for (const body of scroller.querySelectorAll(".nav-group-body")) observer.observe(body);
    const stop = () => {
      observer.disconnect();
      runtimeRef.current.ignoreScroll = false;
      runtimeRef.current.lastScrollTop = scroller.scrollTop;
      runtimeRef.current.stopAnchor = null;
    };
    const timeout = window.setTimeout(stop, NAV_SCROLL_ANIMATION_MS + 32);
    runtimeRef.current.stopAnchor = () => {
      window.clearTimeout(timeout);
      stop();
    };
    return () => runtimeRef.current.stopAnchor?.();
  }, [autoCollapsed, scrollerRef]);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const runtime = runtimeRef.current;
    runtime.lastScrollTop = scroller.scrollTop;

    const apply = (options: { atTopWheelUp?: boolean } = {}) => {
      if (runtime.ignoreScroll) return;
      if (scroller.clientHeight <= 0) return;
      const now = performance.now();
      if (now < runtime.lockUntil) return;

      const scrollTop = scroller.scrollTop;
      const delta = scrollTop - runtime.lastScrollTop;
      const direction: NavScrollDirection = options.atTopWheelUp
        ? "up"
        : delta > 1
          ? "down"
          : delta < -1
            ? "up"
            : "none";
      if (direction === "down" && scrollTop > NAV_SCROLL_EXPAND_THRESHOLD + NAV_SCROLL_EXPAND_ARM_SLACK) {
        runtime.allowExpand = true;
      }

      const sections = measureNavScrollSections(scroller);
      const plan = planNavScrollFold({
        scrollTop,
        direction,
        sections,
        manualCollapsed: manualRef.current,
        autoCollapsed: autoRef.current,
        allowExpand: runtime.allowExpand,
        atTopWheelUp: options.atTopWheelUp,
      });
      runtime.lastScrollTop = scrollTop;
      if (!plan.section || !plan.action) return;

      runtime.allowExpand = false;
      runtime.lockUntil = now + NAV_SCROLL_ANIMATION_MS;
      runtime.ignoreScroll = true;

      if (plan.action === "collapse") {
        const index = sections.findIndex((section) => section.section === plan.section);
        const following = index >= 0 ? sections[index + 1] : undefined;
        pendingAnchorRef.current = following ? { node: following.header, top: following.header.getBoundingClientRect().top } : null;
      } else {
        pendingAnchorRef.current = null;
      }

      autoRef.current = plan.autoCollapsed;
      setAutoCollapsed(plan.autoCollapsed);
    };

    let frame = 0;
    const onScroll = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        apply();
      });
    };
    const onWheel = (event: WheelEvent) => {
      if (event.deltaY >= 0) return;
      if (scroller.scrollTop > NAV_SCROLL_TOP_EPSILON) return;
      apply({ atTopWheelUp: true });
    };

    scroller.addEventListener("scroll", onScroll, { passive: true });
    scroller.addEventListener("wheel", onWheel, { passive: true });
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      scroller.removeEventListener("scroll", onScroll);
      scroller.removeEventListener("wheel", onWheel);
      runtime.stopAnchor?.();
    };
  }, [bindKey, scrollerRef]);

  return { autoCollapsed, lockManualInteraction, scrollSectionIntoSlot };
}
