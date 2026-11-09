import { useState } from "react";
import { isArtifactCollection, isArtifactRef, type JsonObject, type JsonValue } from "@veyra/api-contracts";
import type { LocalProjectApi } from "../../api/local-client";
import { ArtifactCard } from "./RuntimeInputForm";
import { RuntimeMarkdown } from "./RuntimeMarkdown";
import "./runtime-output-reading.css";

type Props = {
  value: JsonValue;
  locale: "zh" | "en";
  projectId?: string;
  api?: Pick<LocalProjectApi, "artifactContent">;
  depth?: number;
};

const labels: Record<string, string> = {
  title: "标题", name: "名称", description: "说明", summary: "摘要", status: "状态",
  notes: "备注", result: "结果", answer: "回答", items: "项目", data: "内容",
  entity_id: "记录 ID", entity_type: "记录类型", revision: "修订版本", updated_at: "更新时间",
  created_at: "创建时间", completed: "已完成", priority: "优先级",
  category: "类别", quantity: "数量", spec: "要求", type: "类型",
  budget: "预算", amount: "金额", cost: "费用", total: "合计", breakdown: "明细",
  budget_rmb: "预算（元）", cost_rmb: "金额（元）", total_rmb: "合计（元）",
  budget_summary: "费用概览", final_execution_list: "执行清单",
  implementation_notes: "执行说明", selected_plan: "已选方案",
};

function fieldLabel(name: string, locale: Props["locale"]): string {
  if (locale === "zh" && labels[name]) return labels[name];
  const readable = name.replace(/[_-]+/g, " ");
  return readable.charAt(0).toUpperCase() + readable.slice(1);
}

function object(value: JsonValue): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value) && !isArtifactRef(value) && !isArtifactCollection(value);
}

function plain(value: JsonValue): boolean {
  return value === null || typeof value === "number" || typeof value === "boolean"
    || (typeof value === "string" && value.length <= 180 && !value.includes("\n"));
}

export function ReadableRuntimeOutput(props: Props) {
  const entries = object(props.value) ? Object.entries(props.value) : [];
  const value = entries.length === 1 && ["result", "answer", "output"].includes(entries[0]![0])
    ? entries[0]![1] : props.value;
  return <div className="runtime-output-reading"><ReadableValue {...props} value={value} depth={0} /></div>;
}

function ReadableValue({ depth = 0, ...props }: Props) {
  const { value, locale } = props;
  if (isArtifactRef(value)) return <ArtifactCard item={value} locale={locale} projectId={props.projectId} api={props.api} />;
  if (isArtifactCollection(value)) return <ReadableArray {...props} value={value.items} depth={depth} />;
  if (typeof value === "string") return value
    ? <RuntimeMarkdown value={value} locale={locale} />
    : <p className="runtime-reading-empty">{locale === "zh" ? "空" : "Empty"}</p>;
  if (typeof value === "number") return <span className="runtime-reading-number">{new Intl.NumberFormat(locale === "zh" ? "zh-CN" : "en", { maximumSignificantDigits: 21 }).format(value)}</span>;
  if (typeof value === "boolean") return <span>{locale === "zh" ? (value ? "是" : "否") : (value ? "Yes" : "No")}</span>;
  if (value === null) return <span className="runtime-reading-empty" aria-label={locale === "zh" ? "空值" : "Null"}>—</span>;
  if (depth >= 3) return <DeepValue {...props} />;
  if (Array.isArray(value)) return <ReadableArray {...props} value={value} depth={depth} />;
  return <ReadableObject {...props} value={value as JsonObject} depth={depth} />;
}

function DeepValue(props: Props) {
  const [open, setOpen] = useState(false);
  const count = Array.isArray(props.value) ? props.value.length : Object.keys(props.value as JsonObject).length;
  const number = new Intl.NumberFormat(props.locale === "zh" ? "zh-CN" : "en").format(count);
  return <details className="runtime-reading-deep" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>{props.locale === "zh" ? `展开 ${number} 项内容` : `Expand ${number} ${count === 1 ? "item" : "items"}`}</summary>
    {open ? <ReadableValue {...props} depth={0} /> : null}
  </details>;
}

function ReadableObject(props: Omit<Props, "value"> & { value: JsonObject }) {
  const [visible, setVisible] = useState(20);
  const entries = Object.entries(props.value);
  if (!entries.length) return <p className="runtime-reading-empty">{props.locale === "zh" ? "暂无内容" : "No content"}</p>;
  return <div className="runtime-reading-object">
    <dl className="runtime-reading-fields">
      {entries.slice(0, visible).map(([name, value]) => <div key={name} className={plain(value) ? "is-scalar" : "is-complex"}>
        <dt>{fieldLabel(name, props.locale)}</dt>
        <dd><ReadableValue {...props} value={value} depth={(props.depth ?? 0) + 1} /></dd>
      </div>)}
    </dl>
    {visible < entries.length ? <More locale={props.locale} onClick={() => setVisible((current) => current + 20)} /> : null}
  </div>;
}

function ReadableArray(props: Omit<Props, "value"> & { value: JsonValue[] }) {
  const [visible, setVisible] = useState(20);
  const { value, locale } = props;
  if (!value.length) return <p className="runtime-reading-empty">{locale === "zh" ? "暂无项目" : "No items"}</p>;
  const first = value.slice(0, visible);
  const columns = value.every(object) ? Array.from(new Set(value.flatMap((row) => Object.keys(row as JsonObject)))) : [];
  const table = columns.length > 0 && columns.length <= 6 && value.every((row) => Object.values(row as JsonObject).every(plain));
  return <div className="runtime-reading-array">
    {table ? <div className="runtime-reading-table-wrap" role="region" aria-label={locale === "zh" ? "结果表格，可左右滚动" : "Result table, scroll horizontally"} tabIndex={0}>
      <table className="runtime-reading-table">
        <caption>{locale === "zh" ? "输出项目" : "Output items"}</caption>
        <thead><tr>{columns.map((name) => <th key={name} scope="col">{fieldLabel(name, locale)}</th>)}</tr></thead>
        <tbody>{(first as JsonObject[]).map((row, index) => <tr key={index}>
          {columns.map((name) => <td key={name}>{Object.hasOwn(row, name) ? <ReadableValue {...props} value={row[name]!} depth={(props.depth ?? 0) + 1} /> : "—"}</td>)}
        </tr>)}</tbody>
      </table>
    </div> : <ul className={`runtime-reading-list${value.every(isArtifactRef) ? " is-artifacts" : ""}`}>
      {first.map((item, index) => <li key={index}><ReadableValue {...props} value={item} depth={(props.depth ?? 0) + 1} /></li>)}
    </ul>}
    {visible < value.length ? <More locale={locale} onClick={() => setVisible((current) => current + 20)} /> : null}
  </div>;
}

function More({ locale, onClick }: { locale: Props["locale"]; onClick: () => void }) {
  return <button type="button" className="runtime-reading-more" onClick={onClick}>{locale === "zh" ? "显示更多内容" : "Show more content"}</button>;
}
