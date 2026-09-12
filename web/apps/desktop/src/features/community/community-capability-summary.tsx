import type { CommunityAgentScan, CommunityRegistryEntry } from "@veyra/api-contracts";
import { SectionHeading, StatusBadge, Tag } from "@veyra/ui";

type Capabilities = NonNullable<CommunityRegistryEntry["capabilities"]>;

export function CommunityCapabilitySummary({
  capabilities,
  scan,
  zh,
}: {
  capabilities: Capabilities;
  scan?: CommunityAgentScan | null;
  zh: boolean;
}) {
  const none = zh ? "无" : "None";
  const values = (items: string[]) => items.length ? items.join(", ") : none;
  const riskLabel = zh
    ? { low: "低", medium: "中", high: "高" }[capabilities.risk_level]
    : capabilities.risk_level;
  const riskTone = capabilities.risk_level === "high" ? "bad" : capabilities.risk_level === "medium" ? "warn" : "good";
  const permissions = capabilities.permissions;

  return (
    <div className="resource-detail-block community-capability-summary">
      <SectionHeading
        eyebrow={zh ? "运行前检查" : "Pre-run review"}
        title={zh ? "能力与权限" : "Capabilities and permissions"}
        detail={zh ? "这是从发布版本源文件推导的摘要，不包含任何密钥值；导入到本机后仍会再次校验。" : "Derived from the published source without secret values; local import validates it again."}
      />
      <div className="settings-facts">
        <div><span>{zh ? "风险级别" : "Risk level"}</span><StatusBadge label={riskLabel} tone={riskTone} /></div>
        <div><span>{zh ? "图节点" : "Graph nodes"}</span><strong>{capabilities.node_count}</strong></div>
        <div><span>{zh ? "需要验证" : "Verification"}</span><strong>{capabilities.verification_required ? (zh ? "需要" : "Required") : (zh ? "未声明" : "Not declared")}</strong></div>
        <div><span>{zh ? "工作区 Shell" : "Workspace Shell"}</span><strong>{permissions.shell_workspace_only ? (zh ? "允许" : "Allowed") : none}</strong></div>
      </div>
      <div className="resource-capability-grid">
        <div><strong>{zh ? "工具" : "Tools"}</strong><p>{values(capabilities.tools)}</p></div>
        <div><strong>{zh ? "网络主机" : "Network hosts"}</strong><p>{values(permissions.network_hosts)}</p></div>
        <div><strong>{zh ? "读取目录" : "Read roots"}</strong><p>{values(permissions.filesystem_read_roots)}</p></div>
        <div><strong>{zh ? "写入目录" : "Write roots"}</strong><p>{values(permissions.filesystem_write_roots)}</p></div>
        <div><strong>{zh ? "主机 Secret 引用" : "Host Secret refs"}</strong><p>{values(capabilities.secret_refs)}</p></div>
        <div><strong>{zh ? "Skills" : "Skills"}</strong><p>{values(capabilities.skills)}</p></div>
      </div>
      {capabilities.risk_reasons.length ? <div className="resource-card-meta">{capabilities.risk_reasons.map((reason) => <Tag key={reason}>{reason}</Tag>)}</div> : null}
      {scan ? <div className="community-scan-summary"><div className="resource-card-meta"><StatusBadge label={scan.status} tone={scan.status === "passed" ? "good" : "warn"} />{scan.warnings.map((warning) => <Tag key={warning.code}>{warning.code}</Tag>)}</div>{scan.warnings.map((warning) => warning.details.length ? <small key={`${warning.code}-details`} className="community-scan-detail">{warning.code}: {warning.details.join(" · ")}</small> : null)}</div> : null}
    </div>
  );
}
