import { ResourceLibraryPage } from "../features/resources/resource-library";

export function ComponentsPage({ componentId }: { componentId?: string }) {
  const resourceId = componentId && !componentId.includes("@") ? `${componentId}@1.0.0` : componentId;
  return <ResourceLibraryPage resourceId={resourceId} />;
}
