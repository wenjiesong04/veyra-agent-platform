import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Inbox } from "lucide-react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { BrandLoading, EmptyState, ListSkeleton, LoadingMask, LoadingState, Skeleton, ThemeProvider, toast } from "@veyra/ui";

afterEach(() => {
  cleanup();
});

function mount(ui: ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

describe("feedback primitives", () => {
  it("shows a success toast after an action and lets errors be dismissed", async () => {
    const user = userEvent.setup();
    mount(<button type="button" onClick={() => toast.success("Project created.")}>Save</button>);
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Project created.")).toBeInTheDocument();
    const host = document.querySelector(".ui-toast-host") as HTMLElement;
    expect(getComputedStyle(host).width).not.toBe("420px");
    expect(host.getBoundingClientRect().width).toBeLessThan(280);
    toast.error("Could not save.");
    expect(await screen.findByText("Could not save.")).toBeInTheDocument();
    await user.click(document.querySelector(".ui-toast-close") as HTMLButtonElement);
    expect(screen.queryByText("Could not save.")).not.toBeInTheDocument();
  });

  it("renders empty, skeleton, overlay, and brand fill loading states", () => {
    mount(
      <>
        <EmptyState icon={Inbox} title="Trash is empty" detail="Deleted chats appear here." />
        <ListSkeleton label="Loading trash…" />
        <Skeleton rows={2} />
        <LoadingMask active label="Updating…"><p>Bound resources</p></LoadingMask>
        <LoadingState label="Opening Project…" />
        <BrandLoading fullscreen label="Checking sign-in…" />
      </>,
    );
    expect(screen.getByText("Trash is empty")).toBeInTheDocument();
    expect(screen.getByText("Deleted chats appear here.")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Loading trash…" })).toBeInTheDocument();
    expect(screen.getByText("Bound resources")).toBeInTheDocument();
    expect(screen.getByText("Updating…")).toBeInTheDocument();
    expect(screen.getByText("Opening Project…")).toBeInTheDocument();
    expect(screen.getByText("Checking sign-in…")).toBeInTheDocument();
    expect(document.querySelectorAll(".ui-brand-mark-color").length).toBeGreaterThan(0);
  });

  it("keeps compact loading as an inline spinner", () => {
    mount(<LoadingState compact label="Loading conversation…" />);
    expect(screen.getByText("Loading conversation…")).toBeInTheDocument();
    expect(document.querySelector(".ui-spinner")).toBeInTheDocument();
    expect(document.querySelector(".ui-brand-mark")).not.toBeInTheDocument();
  });
});
