import { desktopRoutePaths } from "@veyra/api-contracts";
import { ResourceLibraryPage } from "../features/resources/resource-library";

export function ComponentsPage({ componentId, catalogHref }: { componentId?: string; catalogHref?: string }) {
  const resourceId = componentId && !componentId.includes("@") ? `${componentId}@1.0.0` : componentId;
  return <ResourceLibraryPage resourceId={resourceId} catalogHref={catalogHref ?? desktopRoutePaths.resources} />;
}
