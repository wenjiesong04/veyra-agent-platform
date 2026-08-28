import type { FlowNode } from "@veyra/api-contracts";

export type StudioComponent = {
  type: FlowNode["component_type"];
  label: string;
  labelZh: string;
  detail: string;
  ports: string[];
};

export const studioComponents: StudioComponent[] = [
  { type: "Start", label: "Start", labelZh: "开始", detail: "Entry point", ports: ["next"] },
  { type: "Agent", label: "Agent", labelZh: "Agent", detail: "Model instruction", ports: ["next"] },
  { type: "Tool", label: "Tool", labelZh: "工具", detail: "Governed tool", ports: ["next"] },
  { type: "Condition", label: "Condition", labelZh: "条件", detail: "Branch expression", ports: ["true", "false"] },
  { type: "Transform", label: "Transform", labelZh: "转换", detail: "Map values", ports: ["next"] },
  { type: "HumanApproval", label: "Human approval", labelZh: "人工审批", detail: "Human decision", ports: ["approved", "rejected"] },
  { type: "Verifier", label: "Verifier", labelZh: "验证器", detail: "Independent checks", ports: ["passed", "failed"] },
  { type: "Output", label: "Output", labelZh: "输出", detail: "Named result", ports: [] },
];

export function componentFor(type: FlowNode["component_type"]) {
  return studioComponents.find((component) => component.type === type)!;
}

export function newNode(type: FlowNode["component_type"], id: string): FlowNode {
  const base: FlowNode = { id, component_type: type };
  if (type === "Agent") return { ...base, model_ref: "model.primary", system_prompt: "" };
  if (type === "Tool") return { ...base, uses: "" };
  if (type === "Condition") return { ...base, expression: "" };
  if (type === "Transform") return { ...base, mapping: {} };
  if (type === "HumanApproval") return { ...base, prompt: "" };
  if (type === "Verifier") return { ...base, checks: [] };
  if (type === "Output") return { ...base, output_name: "result" };
  return base;
}
