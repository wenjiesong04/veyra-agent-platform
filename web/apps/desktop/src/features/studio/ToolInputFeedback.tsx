import type { JsonValue } from "@veyra/api-contracts";

function object(value: JsonValue | undefined): value is { [key: string]: JsonValue } {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const categories: Record<string, [string, string]> = {
  required: ["缺少必填参数", "Required parameter missing"],
  type: ["类型与声明不符", "Type does not match"],
  additionalProperties: ["存在未声明的参数", "Undeclared parameter"],
  enum: ["不在允许选项中", "Not an allowed option"],
  minimum: ["低于最小值", "Below minimum"],
  maximum: ["超过最大值", "Above maximum"],
  minLength: ["内容过短", "Too short"],
  maxLength: ["内容过长", "Too long"],
  minItems: ["项目数量不足", "Too few items"],
  maxItems: ["项目数量过多", "Too many items"],
  minProperties: ["字段数量不足", "Too few fields"],
  maxProperties: ["字段数量过多", "Too many fields"],
  arithmetic_expression: ["计算表达式无效", "Invalid calculation"],
  state_scope: ["不符合状态契约", "State contract mismatch"],
  json_serializable: ["不是有效 JSON 数据", "Invalid JSON data"],
};

export function ToolInputFeedback({ diagnostic, effectStarted, locale, subject = "tool" }: {
  diagnostic: JsonValue | undefined;
  effectStarted: JsonValue | undefined;
  locale: "zh" | "en";
  subject?: "tool" | "action";
}) {
  if (!object(diagnostic)) return null;
  const summary = typeof diagnostic.summary === "string" ? diagnostic.summary : typeof diagnostic.message === "string" ? diagnostic.message : undefined;
  const violations = Array.isArray(diagnostic.violations) ? diagnostic.violations.filter(object).filter((item) => typeof item.category === "string" && typeof item.location === "string") : [];
  if (!summary && !violations.length) return null;
  const zh = locale === "zh";
  return <div role="note" className="studio-input-diagnostic">
    {effectStarted === false ? <strong>{subject === "action" ? (zh ? "未执行该动作" : "Action was not executed") : (zh ? "未执行该工具" : "Tool was not executed")}</strong> : null}
    {summary ? <p>{summary}</p> : null}
    {violations.length ? <ul>{violations.map((item, index) => <li key={index}>
      <code>{String(item.location)}</code>{": "}{categories[String(item.category)]?.[zh ? 0 : 1] ?? String(item.category)}
      {typeof item.expected_type === "string" ? <span>{zh ? "，应为 " : "; expected "}<code>{item.expected_type}</code></span> : null}
      {typeof item.limit === "number" ? <span>{zh ? "，限制 " : "; limit "}{item.limit}</span> : null}
      {Array.isArray(item.allowed_parameters) ? <span>{zh ? "；允许参数：" : "; allowed parameters: "}{item.allowed_parameters.filter((value): value is string => typeof value === "string").join(", ")}</span> : null}
    </li>)}</ul> : null}
  </div>;
}
