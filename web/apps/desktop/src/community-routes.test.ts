import { describe, expect, it } from "vitest";
import { communityRoutePaths, parseDesktopRoute } from "@veyra/api-contracts";
import { desktopHeader } from "./desktop-header";

describe("Community section routes", () => {
  it("keeps the four page intents in the existing Community route family", () => {
    expect(parseDesktopRoute(communityRoutePaths.catalog).kind).toBe("community");
    expect(parseDesktopRoute(communityRoutePaths.published).kind).toBe("community-published");
    expect(parseDesktopRoute(communityRoutePaths.starred).kind).toBe("community-starred");
    expect(parseDesktopRoute(communityRoutePaths.mine).kind).toBe("community-mine");
    expect(parseDesktopRoute(communityRoutePaths.following).kind).toBe("community-mine");
  });

  it("shows a Community breadcrumb for section and release routes", () => {
    expect(desktopHeader(parseDesktopRoute(communityRoutePaths.published), [], "zh").breadcrumbs?.map((crumb) => crumb.label)).toEqual(["社区", "已发布"]);
    expect(desktopHeader(parseDesktopRoute(communityRoutePaths.starred), [], "en").breadcrumbs?.map((crumb) => crumb.label)).toEqual(["Community", "Starred"]);
    expect(desktopHeader(parseDesktopRoute(communityRoutePaths.mine), [], "zh").breadcrumbs?.map((crumb) => crumb.label)).toEqual(["社区", "我的"]);
    expect(desktopHeader(parseDesktopRoute(communityRoutePaths.version("maker", "brief", "1.0.0")), [], "zh").breadcrumbs?.map((crumb) => crumb.label)).toEqual(["社区", "发现", "brief", "v1.0.0"]);
    expect(desktopHeader(parseDesktopRoute(communityRoutePaths.catalog), [], "zh").breadcrumbs?.map((crumb) => crumb.label)).toEqual(["社区", "发现"]);
  });

  it("does not collide section names with owner/slug release routes", () => {
    expect(parseDesktopRoute(communityRoutePaths.entry("maker", "published"))).toMatchObject({ kind: "community-entry", owner: "maker", slug: "published" });
  });
});
