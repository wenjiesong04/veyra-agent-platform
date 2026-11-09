import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AgentSource } from "@veyra/api-contracts";
import { FinalizationInspector } from "./FinalizationInspector";

type Policy = AgentSource["extensions"]["veyra"]["finalization"];
const policy: Policy = { version: "1", checks: ["output.not_empty"], criteria: ["Match user facts"], review_images: true };
afterEach(cleanup);

describe("Finalization inspector", () => {
  it("does not silently enable review on old sources", () => {
    const changed = vi.fn();
    render(<FinalizationInspector hasImages={false} locale="zh" onChange={changed} />);
    expect(screen.getByRole("checkbox", { name: "交付检查" })).not.toBeChecked();
    expect(changed).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("checkbox", { name: "交付检查" }));
    expect(changed).toHaveBeenLastCalledWith({ version: "1", checks: ["output.not_empty"], criteria: [], review_images: false });
  });

  it("preserves multiline editing and immediately updates the source policy", () => {
    function Form() {
      const [value, setValue] = useState<Policy>(policy);
      return <><FinalizationInspector policy={value} hasImages locale="zh" onChange={setValue} /><output>{value?.criteria.join("|")}</output></>;
    }
    render(<Form />);
    const field = screen.getByRole("textbox", { name: "检查标准" });
    fireEvent.change(field, { target: { value: "Match user facts\n" } });
    expect(field).toHaveValue("Match user facts\n");
    fireEvent.change(field, { target: { value: "Match user facts\nInspect actual views" } });
    expect(screen.getByRole("status")).toHaveTextContent("Match user facts|Inspect actual views");
    fireEvent.change(field, { target: { value: "" } });
    expect(screen.getByRole("checkbox", { name: "审查生成图片" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "审查生成图片" })).toBeDisabled();
  });

  it("can remove the optional contract without rewriting legacy fields", () => {
    const changed = vi.fn();
    render(<FinalizationInspector policy={policy} hasImages locale="zh" onChange={changed} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "交付检查" }));
    expect(changed).toHaveBeenLastCalledWith(undefined);
  });

  it("requires an explicit original input selection and does not guess it on load", () => {
    const changed = vi.fn();
    render(<FinalizationInspector policy={policy} hasImages inputNames={["analysis", "original"]} locale="en" onChange={changed} />);
    const mode = screen.getByRole("combobox", { name: "Original source review" });
    expect(mode).toHaveValue("direct");
    expect(changed).not.toHaveBeenCalled();
    expect(screen.queryByRole("checkbox", { name: "original" })).toBeNull();
    fireEvent.change(mode, { target: { value: "input:original" } });
    expect(changed).toHaveBeenLastCalledWith({ ...policy, review_strategy: "evidence_first", evidence_inputs: ["original"] });
  });

  it("preserves existing multiple inputs while editing checks or adding another input", () => {
    const initial: Policy = { ...policy!, review_strategy: "evidence_first", evidence_inputs: ["original", "records"] };
    const changed = vi.fn();
    render(<FinalizationInspector policy={initial} hasImages inputNames={["original", "records", "notes"]} locale="en" onChange={changed} />);
    expect(screen.getByRole("checkbox", { name: "original" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "records" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "notes" })).not.toBeChecked();
    fireEvent.change(screen.getByRole("textbox", { name: "Rule checks" }), { target: { value: "output.not_empty\nrequired_fields:result" } });
    expect(changed).toHaveBeenLastCalledWith({ ...initial, checks: ["output.not_empty", "required_fields:result"] });
    fireEvent.change(screen.getByRole("combobox", { name: "Original source review" }), { target: { value: "input:notes" } });
    expect(changed).toHaveBeenLastCalledWith({ ...initial, evidence_inputs: ["original", "records", "notes"] });
  });

  it("returns to direct review only after explicit selection or removal of the final input", () => {
    function Form() {
      const [value, setValue] = useState<Policy>({ ...policy!, review_strategy: "evidence_first", evidence_inputs: ["original", "records"] });
      return <><FinalizationInspector policy={value} hasImages inputNames={["original", "records"]} locale="en" onChange={setValue} /><output>{JSON.stringify(value)}</output></>;
    }
    render(<Form />);
    fireEvent.click(screen.getByRole("checkbox", { name: "original" }));
    expect(screen.getByRole("status")).toHaveTextContent('"review_strategy":"evidence_first"');
    expect(screen.getByRole("status")).toHaveTextContent('"evidence_inputs":["records"]');
    fireEvent.click(screen.getByRole("checkbox", { name: "records" }));
    expect(screen.getByRole("combobox", { name: "Original source review" })).toHaveValue("direct");
    expect(screen.getByRole("status")).toHaveTextContent('"review_strategy":"direct"');
    expect(screen.getByRole("status")).toHaveTextContent('"evidence_inputs":[]');
    fireEvent.change(screen.getByRole("combobox", { name: "Original source review" }), { target: { value: "input:original" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Original source review" }), { target: { value: "direct" } });
    expect(screen.getByRole("status")).toHaveTextContent('"evidence_inputs":[]');
  });

  it("clears the opt-in strategy when required criteria are removed", () => {
    const changed = vi.fn();
    const initial: Policy = { ...policy!, advisory_criteria: ["Optional advice"], review_strategy: "evidence_first", evidence_inputs: ["original", "records"] };
    render(<FinalizationInspector policy={initial} hasImages inputNames={["original", "records"]} locale="zh" onChange={changed} />);
    fireEvent.change(screen.getByRole("textbox", { name: "检查标准" }), { target: { value: "" } });
    expect(changed).toHaveBeenLastCalledWith({ ...initial, criteria: [], pre_render_review: false, review_strategy: "direct", evidence_inputs: [] });
  });

  it.each([
    [[], ["Match facts"]],
    [["original"], []],
  ])("does not enable original source review without inputs and required criteria", (inputNames, criteria) => {
    const changed = vi.fn();
    render(<FinalizationInspector policy={{ ...policy!, criteria }} hasImages={false} inputNames={inputNames} locale="en" onChange={changed} />);
    expect(screen.getByRole("combobox", { name: "Original source review" })).toBeDisabled();
    expect(changed).not.toHaveBeenCalled();
  });
});
