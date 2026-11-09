import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

export function SettingsDialog({ title, busy, onClose, children, closeLabel }: {
  title: string;
  busy: boolean;
  onClose: () => void;
  children: ReactNode;
  closeLabel: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    if (dialog && !dialog.open) {
      if (dialog.showModal) dialog.showModal();
      else dialog.setAttribute("open", "");
    }
    return () => { dialog?.close?.(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} className="runtime-provider-modal" aria-label={title} aria-modal="true"
    onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
    <div className="runtime-provider-modal-header"><h2>{title}</h2><button className="runtime-provider-modal-close" type="button" disabled={busy} aria-label={closeLabel} onClick={onClose}><X size={18} aria-hidden="true" /></button></div>
    {children}
  </dialog>;
}
