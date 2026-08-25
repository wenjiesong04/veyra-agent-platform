import { Check, Cloud, KeyRound, LogIn, ShieldCheck } from "lucide-react";
import { LinkButton, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";

function communityLoginHref(): string {
  const configuredOrigin = import.meta.env.VITE_COMMUNITY_ORIGIN?.trim();
  const origin = (configuredOrigin || "http://127.0.0.1:5174").replace(/\/+$/, "");
  return `${origin}/#/login`;
}

export function AccountPage() {
  const { locale } = useLocale();
  const copy = locale === "zh" ? {
    eyebrow: "身份边界",
    title: "没有账号，本机工作也依然有用。",
    description: "连接账号可以启用分享能力，但不会拥有你的本地源文件或运行历史。",
    guest: "访客模式",
    profileEyebrow: "当前资料",
    local: "本机",
    workspace: "工作区",
    workspaceValue: "本地且私密",
    sourceFiles: "源文件",
    sourceValue: "由此设备拥有",
    runs: "运行记录",
    runsValue: "存放在定义文件之外",
    connect: "连接账号",
    capabilities: "能力",
    available: "当前可用能力",
    availableLocally: "本机可用",
    credentialNote: "凭据保留在宿主系统钥匙串中，永远不会写入 Agent 源文件。",
    optional: "可选连接",
    share: "只在你选择时分享",
    optionalDetail: "连接账号后可以在社区服务中发布、导入和提交评审。",
    community: "社区连接",
    disconnected: "未连接 · 本机模式仍可继续工作",
    manage: "管理连接",
    displayName: "本机工作区",
    workspaceLabel: "此设备",
    permissions: ["Studio", "Runtime", "组件库", "监控"],
  } : {
    eyebrow: "Identity boundary",
    title: "Keep local work useful without an account.",
    description: "Account connections add sharing capabilities; they never own your local source or run history.",
    guest: "Guest mode",
    profileEyebrow: "Current profile",
    local: "Local",
    workspace: "Workspace",
    workspaceValue: "Local and private",
    sourceFiles: "Source files",
    sourceValue: "Owned by this device",
    runs: "Runs",
    runsValue: "Stored outside definition files",
    connect: "Connect account",
    capabilities: "Capabilities",
    available: "What is available now",
    availableLocally: "Available locally",
    credentialNote: "Credentials stay in the host keychain and are never placed in Agent source.",
    optional: "Optional connection",
    share: "Share only when you choose",
    optionalDetail: "A connected account enables publishing, importing, and reviews in the Community service.",
    community: "Community connection",
    disconnected: "Not connected · local mode continues to work",
    manage: "Manage connection",
    displayName: "Local workspace",
    workspaceLabel: "This device",
    permissions: ["Studio", "Runtime", "Library", "Monitor"],
  };
  const loginHref = communityLoginHref();
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><StatusBadge label={copy.guest} tone="good" /></div><div className="content-grid two-thirds"><Panel><SectionHeading eyebrow={copy.profileEyebrow} title={copy.displayName} detail={copy.workspaceLabel} action={<Tag tone="good">{copy.local}</Tag>} /><div className="account-page-avatar">V</div><dl className="detail-list"><div><dt>{copy.workspace}</dt><dd>{copy.workspaceValue}</dd></div><div><dt>{copy.sourceFiles}</dt><dd>{copy.sourceValue}</dd></div><div><dt>{copy.runs}</dt><dd>{copy.runsValue}</dd></div></dl><LinkButton href={loginHref} icon={LogIn} variant="primary">{copy.connect}</LinkButton></Panel><Panel><SectionHeading eyebrow={copy.capabilities} title={copy.available} /><div className="capability-list">{copy.permissions.map((permission) => <div key={permission}><Check size={15} /><span>{permission}<small>{copy.availableLocally}</small></span></div>)}</div><div className="account-note"><ShieldCheck size={16} /><span>{copy.credentialNote}</span></div></Panel></div><Panel><SectionHeading eyebrow={copy.optional} title={copy.share} detail={copy.optionalDetail} /><div className="connection-card"><span className="connection-icon"><Cloud size={18} /></span><span><strong>{copy.community}</strong><small>{copy.disconnected}</small></span><LinkButton href={loginHref} icon={KeyRound} size="sm">{copy.manage}</LinkButton></div></Panel></div>;
}
