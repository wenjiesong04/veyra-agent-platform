import { ArrowLeft, Compass } from "lucide-react";
import { ErrorState, LinkButton, useLocale } from "@veyra/ui";

export function NotFoundPage({ backHref = "#/projects", backLabel = "Back to Projects" }: { backHref?: string; backLabel?: string } = {}) {
  const { locale } = useLocale();
  const copy = locale === "zh" ? { eyebrow: "找不到页面", title: "找不到路由", message: "当前工作区路由不可用。", defaultBack: "返回项目" } : { eyebrow: "Not found", title: "Route not found", message: "That workspace route is not available.", defaultBack: "Back to Projects" };
  return <div className="not-found"><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><ErrorState message={copy.message} /><LinkButton href={backHref} icon={ArrowLeft} variant="primary">{backLabel === "Back to Projects" ? copy.defaultBack : backLabel}</LinkButton><Compass size={18} aria-hidden="true" /></div>;
}
