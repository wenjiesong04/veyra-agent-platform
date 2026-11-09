import { Check, FileCode, LoaderCircle, Upload, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { CommunityPluginEntry, CommunityRegistryEntry } from "@veyra/api-contracts";
import { CommunityApiError, useAuth } from "@veyra/connected-account";
import { Button, useLocale } from "@veyra/ui";
import { preparePublicationFile, type PublicationFile, type PublicationKind } from "./publication-file";

type PublicationReceipt = CommunityRegistryEntry | CommunityPluginEntry;
export function PublicationUpload({ kind, onPublished }: { kind: PublicationKind; onPublished: (entry: PublicationReceipt) => void }) {
  const { api, account, ensureSession } = useAuth();
  const { locale } = useLocale();
  const zh = locale === "zh";
  const input = useRef<HTMLInputElement>(null);
  const selection = useRef(0);
  const [preview, setPreview] = useState<(PublicationFile & { publisherId: string }) | null>(null);
  const publisher = useRef(account?.id); publisher.current = account?.id;
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState("");
  const [receipt, setReceipt] = useState<PublicationReceipt | null>(null);
  useEffect(() => () => { selection.current++; }, []);

  const choose = async (file: File | undefined) => {
    if (!file) return;
    const current = ++selection.current;
    const publisherId = account?.id;
    if (!publisherId) return;
    setPreview(null); setError(""); setReceipt(null); setConfirmed(false); setReading(true);
    try {
      const prepared = await preparePublicationFile(file, kind);
      if (current === selection.current && publisher.current === publisherId) setPreview({ ...prepared, publisherId });
    } catch (cause) {
      if (current !== selection.current) return;
      const code = cause instanceof Error ? cause.message : "file_read_failed";
      const errors: Record<string, string> = zh ? {
        empty_file: "文件是空的，请重新选择。", file_type_invalid: kind === "agent" ? "请选择桌面版导出的 .vagent.yaml 文件。" : "请选择 .vplugin.zip 插件包。", file_too_large: kind === "agent" ? "Agent 文件不能超过 1 MB。" : "插件包不能超过 5 MB。", credential_marker: "文件中检测到疑似密钥。请移除后重新导出。", workflow_not_supported: "Workflow 分享包尚未接通，请选择 Agent 导出文件。",
      } : {
        empty_file: "This file is empty.", file_type_invalid: kind === "agent" ? "Choose a .vagent.yaml file exported from Desktop." : "Choose a .vplugin.zip Plugin Pack.", file_too_large: kind === "agent" ? "Agent files must be at most 1 MB." : "Plugin Packs must be at most 5 MB.", credential_marker: "A possible credential was detected. Remove it and export again.", workflow_not_supported: "Workflow sharing is not connected yet. Choose an Agent export.",
      };
      setError(errors[code] ?? (zh ? "无法读取文件，请选择 UTF-8 编码的有效导出包。" : "Could not read this file. Choose a valid UTF-8 export."));
    } finally { if (current === selection.current) setReading(false); }
  };
  const publish = async () => {
    if (!preview || !confirmed || busy) return;
    if (preview.publisherId !== account?.id) { setConfirmed(false); setError(zh ? "登录身份已变化，请重新选择文件并确认。" : "Your sign-in changed. Select the file and confirm again."); return; }
    const expectedPublisherId = preview.publisherId;
    setBusy(true); setError("");
    try {
      const entry = kind === "agent" ? await api.publishRegistryAgent(preview.file, undefined, { expectedPublisherId }) : await api.publishRegistryPlugin(preview.file, { expectedPublisherId });
      if (publisher.current !== expectedPublisherId) return;
      setReceipt(entry); setPreview(null); setConfirmed(false); onPublished(entry);
    } catch (cause) {
      if (cause instanceof CommunityApiError && ["publication_account_changed", "authentication_required"].includes(cause.code)) {
        setConfirmed(false); setError(zh ? "登录身份已变化，请重新检查文件并确认。" : "Your sign-in changed. Review the file and confirm again.");
        void ensureSession();
      } else setError(cause instanceof Error ? cause.message : (zh ? "发布失败，请重试。" : "Publication failed. Try again."));
    } finally { setBusy(false); }
  };
  return <section className="creator-upload" aria-label={zh ? "上传发布" : "Upload and publish"}>
    <input ref={input} type="file" className="creator-file-input" accept={kind === "agent" ? ".vagent.yaml,.yaml,.yml" : ".vplugin.zip"} aria-label={zh ? "选择导出包" : "Choose an export"} disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; void choose(file); }} />
    {!preview ? <div className="creator-upload-start"><Upload size={24} /><div><strong>{zh ? "上传桌面版导出的文件" : "Upload a Desktop export"}</strong><p>{kind === "agent" ? (zh ? ".vagent.yaml · 最大 1 MB" : ".vagent.yaml · Up to 1 MB") : ".vplugin.zip · 5 MB"}</p></div><Button icon={reading ? LoaderCircle : Upload} variant="secondary" disabled={reading || busy} onClick={() => input.current?.click()}>{zh ? "选择文件" : "Choose file"}</Button></div> : <div className="creator-upload-preview">
      <div className="creator-preview-title"><FileCode size={20} /><div><strong>{preview.file.name}</strong><span>{(preview.file.size / 1024).toFixed(1)} KB · {zh ? "仅本地预览，尚未上传" : "Local preview · Not uploaded"}</span></div><Button variant="ghost" size="sm" icon={X} aria-label={zh ? "取消选择" : "Clear selection"} disabled={busy} onClick={() => { setPreview(null); setConfirmed(false); }} /></div>
      {preview.sha256 ? <p className="creator-file-hash"><span>SHA-256</span><code>{preview.sha256}</code></p> : null}
      {preview.text ? <details><summary>{zh ? "检查文件内容" : "Inspect file contents"}</summary><pre>{preview.text}</pre></details> : <p>{zh ? "ZIP 包将由服务端检查声明、依赖和包内容。" : "The server checks the ZIP contents, declarations, and dependencies."}</p>}
      <label className="creator-confirm"><input type="checkbox" checked={confirmed} disabled={busy} onChange={(event) => setConfirmed(event.target.checked)} /><span>{zh ? "我已检查文件内容，同意将这个版本发布到社区。" : "I have reviewed this file and agree to publish this version to Community."}</span></label>
      <div className="creator-confirm-row"><p>{zh ? "请确认包内不含密钥或私有资料。发布结果以服务端检查与审核状态为准。" : "Check that the package contains no credentials or private material. Server validation and moderation determine publication status."}</p><Button variant="primary" icon={busy ? LoaderCircle : Upload} disabled={!confirmed || busy} onClick={() => void publish()}>{busy ? (zh ? "正在上传…" : "Uploading…") : (zh ? "确认上传并发布" : "Upload and publish")}</Button></div>
    </div>}
    {error ? <p className="creator-upload-error" role="alert">{error}</p> : null}
    {receipt ? <div className="creator-upload-receipt" role="status"><Check size={18} /><span>{receipt.name} · v{receipt.version} — {receipt.status === "published" ? (zh ? "已发布" : "Published") : receipt.status === "quarantined" ? (zh ? "已提交审核" : "Submitted for review") : (zh ? "发布被拒绝" : "Rejected")}</span></div> : null}
  </section>;
}
