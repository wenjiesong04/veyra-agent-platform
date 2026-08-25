import { ArrowLeft, Compass } from "lucide-react";
import { ErrorState, LinkButton } from "@veyra/ui";

export function NotFoundPage() {
  return <div className="not-found"><ErrorState message="That workspace route is not available." /><LinkButton href="#/projects" icon={ArrowLeft} variant="primary">Back to Projects</LinkButton><Compass size={18} aria-hidden="true" /></div>;
}
