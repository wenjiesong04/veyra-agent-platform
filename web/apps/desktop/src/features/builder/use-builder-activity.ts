import * as React from "react";
import type { BuilderActivityItem } from "@veyra/api-contracts";
import { useProjectWorkspace } from "../../api/project-workspace";

export const BUILDER_ACTIVITY_EVENT = "veyra:builder-activity";

export function notifyBuilderActivity(): void {
  window.dispatchEvent(new Event(BUILDER_ACTIVITY_EVENT));
}

export function useBuilderActivity(): BuilderActivityItem[] {
  const { api } = useProjectWorkspace();
  const [items, setItems] = React.useState<BuilderActivityItem[]>([]);

  React.useEffect(() => {
    if (!api.listBuilderActivity) {
      setItems([]);
      return;
    }
    let active = true;
    const load = () => {
      void api.listBuilderActivity!().then((result) => {
        if (active) setItems(result.items);
      }).catch(() => {
        if (active) setItems([]);
      });
    };
    load();
    window.addEventListener(BUILDER_ACTIVITY_EVENT, load);
    return () => {
      active = false;
      window.removeEventListener(BUILDER_ACTIVITY_EVENT, load);
    };
  }, [api]);

  return items;
}
