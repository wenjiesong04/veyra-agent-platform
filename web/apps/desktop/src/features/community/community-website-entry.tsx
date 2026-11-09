import { ArrowUpRight, Copy, X } from "lucide-react";
import { createContext, useContext, useState, type ReactNode } from "react";
import type { DesktopRouteLocation } from "@veyra/api-contracts";
import { desktopRoutePaths } from "@veyra/api-contracts";
import { Button, LinkButton, Panel, useLocale } from "@veyra/ui";
import { COMMUNITY_SITE_SETUP, communityWebsiteConfig, communityWebsiteHref, isCommunityWebsiteRoute, openCommunityWebsite } from "./community-website";
import "./community-website-entry.css";

const WebsiteContext = createContext<(hash: string) => void>(() => {});

const text = {
  zh: {
    title: "社区已移至网页", body: "在社区网站发现、发布和收藏资源。网页会在浏览器中打开，当前桌面工作空间会保留。",
    open: "打开社区网站", back: "返回工作空间", address: "社区网页地址", copy: "复制链接", copied: "已复制。", copyFailed: "请选中下面的内容手动复制。",
    missing: "尚未配置社区网站", invalid: "社区网站地址配置无效", failed: "无法打开社区网站", close: "关闭社区提示",
    configure: "部署社区网页后，在构建 Desktop 前设置公开网站地址。这里填写网站基础地址，不填写账号、密钥、查询参数或页面锚点；随后重新构建。",
    setup: "复制配置示例", native: "请重试，或复制链接到浏览器打开。当前桌面页面会保留。",
  },
  en: {
    title: "Community is on the web", body: "Discover, publish, and save resources on the Community website. It opens in your browser while your desktop workspace stays here.",
    open: "Open Community website", back: "Back to workspace", address: "Community website URL", copy: "Copy link", copied: "Copied.", copyFailed: "Select the text below and copy it manually.",
    missing: "Community website not configured", invalid: "Invalid Community website configuration", failed: "Could not open the Community website", close: "Close Community notice",
    configure: "After deploying Community, set its public base URL before building Desktop, then rebuild. Use the website address without account details, secrets, query parameters, or a page hash.",
    setup: "Copy configuration example", native: "Try again or copy the link into your browser. Your current desktop page stays here.",
  },
};

function CopyText({ value, label }: { value: string; label: string }) {
  const { locale } = useLocale();
  const copy = text[locale];
  const [message, setMessage] = useState("");
  return <div className="community-website-copy"><input aria-label={label} readOnly value={value} onFocus={(event) => event.currentTarget.select()} /><Button size="sm" icon={Copy} onClick={() => {
    if (!navigator.clipboard?.writeText) { setMessage(copy.copyFailed); return; }
    void navigator.clipboard.writeText(value).then(() => setMessage(copy.copied)).catch(() => setMessage(copy.copyFailed));
  }}>{label}</Button>{message ? <p role="status">{message}</p> : null}</div>;
}

export function CommunityWebsiteBoundary({ children }: { children: ReactNode }) {
  const { locale } = useLocale();
  const copy = text[locale];
  const [notice, setNotice] = useState<{ status: "missing" | "invalid" | "failed"; href?: string } | null>(null);
  const open = (hash: string) => {
    const config = communityWebsiteConfig();
    if (config.status !== "ready") { setNotice({ status: config.status }); return; }
    const href = communityWebsiteHref(config, hash, locale);
    setNotice(null);
    void openCommunityWebsite(href).catch(() => setNotice({ status: "failed", href }));
  };
  return <WebsiteContext.Provider value={open}><div className="community-website-boundary" onClickCapture={(event) => {
    const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
    const hash = anchor?.getAttribute("href");
    if (!hash || !isCommunityWebsiteRoute(hash)) return;
    event.preventDefault();
    open(hash);
  }}>{children}{notice ? <aside className="community-website-notice" role="region" aria-live="polite" aria-label={copy[notice.status]}><button type="button" className="community-website-close" aria-label={copy.close} onClick={() => setNotice(null)}><X size={18} /></button><h2>{copy[notice.status]}</h2><p>{notice.status === "failed" ? copy.native : copy.configure}</p><CopyText value={notice.href ?? COMMUNITY_SITE_SETUP} label={notice.href ? copy.copy : copy.setup} /></aside> : null}</div></WebsiteContext.Provider>;
}

export function CommunityWebsitePage({ route }: { route: DesktopRouteLocation }) {
  const { locale } = useLocale();
  const copy = text[locale];
  const open = useContext(WebsiteContext);
  const config = communityWebsiteConfig();
  const href = config.status === "ready" ? communityWebsiteHref(config, route, locale) : null;
  return <div className="page-stack community-website-page"><Panel><h1>{copy.title}</h1><p>{copy.body}</p>{href ? <><p>{copy.address}</p><CopyText value={href} label={copy.copy} /><Button icon={ArrowUpRight} variant="primary" onClick={() => open(route.path)}>{copy.open}</Button></> : <><h2>{copy[config.status === "invalid" ? "invalid" : "missing"]}</h2><p>{copy.configure}</p><CopyText value={COMMUNITY_SITE_SETUP} label={copy.setup} /></>}<LinkButton href={desktopRoutePaths.chat} variant="ghost">{copy.back}</LinkButton></Panel></div>;
}
