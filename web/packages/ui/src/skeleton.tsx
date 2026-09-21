export function SkeletonItem({
  variant = "text",
  className = "",
}: {
  variant?: "text" | "title" | "avatar" | "block";
  className?: string;
}) {
  return <span className={`ui-skeleton ui-skeleton-${variant} ${className}`.trim()} aria-hidden="true" />;
}

export function Skeleton({
  rows = 3,
  animated = true,
  className = "",
}: {
  rows?: number;
  animated?: boolean;
  className?: string;
}) {
  return (
    <div className={`ui-skeleton-stack${animated ? "" : " is-static"} ${className}`.trim()} aria-hidden="true">
      <SkeletonItem variant="title" />
      {Array.from({ length: rows }, (_, index) => <SkeletonItem key={index} variant="text" className={index === rows - 1 ? "is-short" : ""} />)}
    </div>
  );
}

export function ListSkeleton({
  rows = 5,
  label = "Loading",
}: {
  rows?: number;
  label?: string;
}) {
  return (
    <div className="ui-list-skeleton" role="status" aria-label={label}>
      {Array.from({ length: rows }, (_, index) => (
        <div className="ui-list-skeleton-row" key={index}>
          <SkeletonItem variant="avatar" />
          <span className="ui-list-skeleton-copy">
            <SkeletonItem variant="title" />
            <SkeletonItem variant="text" className="is-short" />
          </span>
        </div>
      ))}
    </div>
  );
}
