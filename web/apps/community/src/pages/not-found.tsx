import { ArrowLeft } from "lucide-react";
import { ErrorState, LinkButton } from "@veyra/ui";

export function CommunityNotFoundPage({ message = "That Community route is not available." }: { message?: string } = {}) {
  return <div className="community-page-stack"><span className="ui-eyebrow">Not found</span><h2>Route not found</h2><ErrorState message={message} /><LinkButton href="#/community" icon={ArrowLeft} variant="primary">Back to Community</LinkButton></div>;
}
