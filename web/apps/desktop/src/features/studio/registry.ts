import type { FlowNode } from "@veyra/api-contracts";

export type StudioComponent = {
  type: FlowNode["component_type"];
  label: string;
  labelZh: string;
  detail: string;
  detailZh: string;
  ports: string[];
};

export const studioComponents: StudioComponent[] = [
  { type: "Start", label: "Start", labelZh: "输入", detail: "Entry point", detailZh: "流程入口，接收声明的输入", ports: ["next"] },
  { type: "Agent", label: "Model (legacy)", labelZh: "模型（旧格式）", detail: "Model instruction", detailZh: "模型与提示词", ports: ["next"] },
  { type: "Model", label: "Model", labelZh: "模型", detail: "Model instruction", detailZh: "模型与提示词", ports: ["next"] },
  { type: "AgentCall", label: "AgentCall", labelZh: "AgentCall", detail: "Call a Project Agent", detailZh: "调用项目 Agent", ports: ["next"] },
  { type: "Tool", label: "Tool", labelZh: "工具", detail: "Governed tool", detailZh: "受治理工具调用", ports: ["next"] },
  { type: "Condition", label: "Condition", labelZh: "条件", detail: "Branch expression", detailZh: "条件分支", ports: ["true", "false"] },
  { type: "Transform", label: "Transform", labelZh: "转换", detail: "Map values", detailZh: "安全字段映射", ports: ["next"] },
  { type: "HumanApproval", label: "Human approval", labelZh: "人工审批", detail: "Human decision", detailZh: "等待人工决策", ports: ["approved", "rejected"] },
  { type: "Verifier", label: "Verifier", labelZh: "验证器", detail: "Independent checks", detailZh: "独立结果检查", ports: ["passed", "failed"] },
  { type: "Output", label: "Output", labelZh: "输出", detail: "Named result", detailZh: "声明最终结果", ports: [] },
];

export function componentFor(type: FlowNode["component_type"]) {
  return studioComponents.find((component) => component.type === type)!;
}

export function newNode(type: FlowNode["component_type"], id: string): FlowNode {
  const base: FlowNode = { id, component_type: type };
  if (type === "Agent" || type === "Model") return { ...base, model_ref: "model.primary", system_prompt: "" };
  if (type === "AgentCall") return { ...base, agent_ref: "", input_mapping: {}, output_mapping: {} };
  if (type === "Tool") return { ...base, uses: "" };
  if (type === "Condition") return { ...base, expression: "" };
  if (type === "Transform") return { ...base, mapping: {} };
  if (type === "HumanApproval") return { ...base, prompt: "" };
  if (type === "Verifier") return { ...base, checks: [] };
  if (type === "Output") return { ...base, output_name: "result" };
  return base;
}
