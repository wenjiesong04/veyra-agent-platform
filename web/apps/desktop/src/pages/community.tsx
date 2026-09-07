import { GitFork, Globe2, ShieldCheck } from "lucide-react";
import { communityRoutePaths, desktopRoutePaths } from "@veyra/api-contracts";
import { EmptyState, LinkButton, Panel, useLocale } from "@veyra/ui";
import { NotFoundPage } from "./not-found";

export function CommunityPage({ owner, slug, versionId }: { owner?: string; slug?: string; versionId?: string }) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const copy = zh ? {
    backCommunity: "返回社区",
    eyebrow: "社区注册表",
    title: "社区目录尚未接入。",
    description: "本机桌面不会展示精选或评分过的示例包。等 Community 注册表可用后，才能检查来源、权限和哈希再导入。",
    openAccount: "打开账号",
    emptyTitle: "没有可发现的社区包",
    emptyDetail: "当前没有已连接的注册表。连接账号不会伪造可导入的 Agent 或 Workflow。",
    lineageTitle: "导入是第二道验证边界。",
    lineageDetail: "包会携带哈希、权限、兼容性和来源信息；本机导入前会再次检查。现在没有可检查的远程条目。",
  } : {
    backCommunity: "Back to Community",
    eyebrow: "Community registry",
    title: "The Community catalog is not connected.",
    description: "Desktop does not show featured or scored sample packages. Inspect source, permissions, and hashes only after a real Community registry is available.",
    openAccount: "Open account",
    emptyTitle: "No discoverable Community packages",
    emptyDetail: "No registry is connected. Signing in does not invent importable Agents or Workflows.",
    lineageTitle: "Import is a second validation boundary.",
    lineageDetail: "Packages carry hashes, permissions, compatibility, and provenance; local import checks them again before use. There is nothing remote to inspect yet.",
  };
  if (owner || slug || versionId) {
    return <NotFoundPage backHref={communityRoutePaths.catalog} backLabel={copy.backCommunity} />;
  }
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.eyebrow}</span>
          <h2>{copy.title}</h2>
          <p>{copy.description}</p>
        </div>
        <LinkButton href={desktopRoutePaths.account} icon={Globe2} variant="ghost">{copy.openAccount}</LinkButton>
      </div>
      <EmptyState icon={Globe2} title={copy.emptyTitle} detail={copy.emptyDetail} />
      <Panel className="lineage-panel">
        <div className="boundary-mark"><GitFork size={17} /></div>
        <div><strong>{copy.lineageTitle}</strong><p>{copy.lineageDetail}</p></div>
        <ShieldCheck size={19} />
      </Panel>
    </div>
  );
}
