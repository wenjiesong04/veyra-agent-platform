import { Check, LogIn, ShieldCheck } from "lucide-react";
import { Button, Panel, SectionHeading, StatusBadge, useLocale } from "@veyra/ui";

export function CommunityAccountPage() {
  const { locale } = useLocale();
  const copy = locale === "zh" ? {
    eyebrow: "社区身份", title: "定义准备好后再发布。", description: "无需登录也可以浏览和进行本机导入。", disconnected: "未连接", connectTitle: "连接社区账号", connectDetail: "账号仅用于发布、保存、评审和来源关系。本地源文件仍保留在你的设备上。", publish: "发布版本", save: "保存条目", fork: "保留来源 Fork", connect: "连接账号", boundary: "边界", public: "公共目录，本机执行", boundaryDetail: "社区服务保存已发布的元数据和包，但不会执行下载的定义。",
  } : {
    eyebrow: "Community identity", title: "Publish when your definition is ready.", description: "Browsing and local imports remain available without signing in.", disconnected: "Not connected", connectTitle: "Connect a community account", connectDetail: "Use an account only for publishing, saving, reviews, and lineage. Local source stays on your device.", publish: "Publish versions", save: "Save entries", fork: "Fork with lineage", connect: "Connect account", boundary: "Boundary", public: "Public catalog, local execution", boundaryDetail: "The Community service stores published metadata and packages. It does not execute downloaded definitions.",
  };
  return <div className="community-page-stack"><div className="community-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><StatusBadge label={copy.disconnected} tone="neutral" /></div><Panel className="account-connect-panel"><div className="account-connect-mark"><LogIn size={22} /></div><div><h3>{copy.connectTitle}</h3><p>{copy.connectDetail}</p><div className="account-benefits"><span><Check size={14} />{copy.publish}</span><span><Check size={14} />{copy.save}</span><span><Check size={14} />{copy.fork}</span></div></div><Button icon={LogIn} variant="primary">{copy.connect}</Button></Panel><Panel><SectionHeading eyebrow={copy.boundary} title={copy.public} detail={copy.boundaryDetail} action={<ShieldCheck size={18} />} /></Panel></div>;
}
