import { useEffect, useRef, useState } from "react";
import { Info, X } from "lucide-react";
import { Button } from "@veyra/ui";

export function WorkflowAbout({ name, description, locale }: { name: string; description: string; locale: "zh" | "en" }) {
  const [open, setOpen] = useState(false);
  const label = locale === "zh" ? "使用说明" : "Usage details";
  return <><Button size="sm" variant="ghost" icon={Info} onClick={() => setOpen(true)}>{label}</Button>{open ? <AboutDialog name={name} description={description} label={label} locale={locale} onClose={() => setOpen(false)} /> : null}</>;
}

function AboutDialog({ name, description, label, locale, onClose }: {
  name: string; description: string; label: string; locale: "zh" | "en"; onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement as HTMLElement | null;
    if (!dialog?.open) dialog?.showModal?.();
    if (dialog && !dialog.open) dialog.setAttribute("open", "");
    return () => { dialog?.close?.(); previous?.focus(); };
  }, []);
  return <dialog ref={ref} className="workflow-about-dialog" aria-label={label} aria-modal="true" onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <header><div><span>{label}</span><h2>{name}</h2></div><button type="button" aria-label={locale === "zh" ? "关闭说明" : "Close usage details"} onClick={onClose}><X size={18} aria-hidden="true" /></button></header>
    <p>{description || (locale === "zh" ? "填写任务输入后，工作流会按已提交的版本执行。" : "Add task inputs to run this Workflow's committed version.")}</p>
  </dialog>;
}
