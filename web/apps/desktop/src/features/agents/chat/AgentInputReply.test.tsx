import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LocalProjectApi } from "../../../api/local-client";
import { AgentInputReply } from "./AgentInputReply";

afterEach(cleanup);

describe("Agent input reply", () => {
  it("shows the choices and sends a reply without approval", async () => {
    const onReply = vi.fn().mockResolvedValue(undefined);
    const onStop = vi.fn();
    render(<AgentInputReply question="Choose a design" context={{ options: ["A", "B", "C"] }} locale="en" busy={false} projectId="project" api={{} as LocalProjectApi} onReply={onReply} onStop={onStop} />);
    const user = userEvent.setup();
    expect(screen.getByText("Choose a design")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit and continue" })).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "Your reply" }), "B, use recycled paper");
    await user.click(screen.getByRole("button", { name: "Submit and continue" }));
    expect(onReply).toHaveBeenCalledWith("B, use recycled paper");
    expect(screen.getByRole("textbox")).toHaveValue("B, use recycled paper");
    await user.click(screen.getByRole("button", { name: "Cancel task" }));
    expect(onStop).toHaveBeenCalledOnce();
  });
});
