import { ArrowLeft, Compass } from "lucide-react";
import { ErrorState, LinkButton } from "@veyra/ui";

export function NotFoundPage({ backHref = "#/projects", backLabel = "Back to Projects" }: { backHref?: string; backLabel?: string } = {}) {
  return <div className="not-found"><span className="ui-eyebrow">Not found</span><h2>Route not found</h2><ErrorState message="That workspace route is not available." /><LinkButton href={backHref} icon={ArrowLeft} variant="primary">{backLabel}</LinkButton><Compass size={18} aria-hidden="true" /></div>;
}
