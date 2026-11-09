import type { CSSProperties, ReactNode } from "react";
import brandIconUrl from "./assets/veyra-icon.png";

export function BrandMark({
  size = 72,
  src = brandIconUrl,
}: {
  size?: number;
  src?: string;
}) {
  return (
    <span className="ui-brand-mark" style={{ "--ui-brand-size": `${size}px` } as CSSProperties} aria-hidden="true">
      <img className="ui-brand-mark-gray" src={src} alt="" />
      <img className="ui-brand-mark-color" src={src} alt="" />
    </span>
  );
}

export function BrandLoading({
  label,
  fullscreen = false,
  size = 72,
}: {
  label?: string;
  fullscreen?: boolean;
  size?: number;
}) {
  return (
    <div className={`ui-brand-loading${fullscreen ? " is-fullscreen" : ""}`} role="status">
      <BrandMark size={size} />
      {label ? <span>{label}</span> : null}
    </div>
  );
}

export function LoadingMask({
  active,
  label,
  children,
}: {
  active: boolean;
  label?: string;
  children?: ReactNode;
}) {
  return (
    <div className={`ui-loading-mask-host${active ? " is-active" : ""}`}>
      {children}
      {active ? (
        <div className="ui-loading-mask" role="status">
          <BrandMark size={58} />
          {label ? <span>{label}</span> : null}
        </div>
      ) : null}
    </div>
  );
}
