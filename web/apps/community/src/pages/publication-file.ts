export type PublicationKind = "agent" | "plugin";
export type PublicationFile = { file: File; text: string | null; sha256: string | null };

function readBytes(file: File): Promise<ArrayBuffer> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => reader.result instanceof ArrayBuffer ? resolve(reader.result) : reject(new Error("file_read_failed"));
    reader.onerror = () => reject(new Error("file_read_failed"));
    reader.readAsArrayBuffer(file);
  });
}

export async function preparePublicationFile(file: File, kind: PublicationKind): Promise<PublicationFile> {
  if (!file.size) throw new Error("empty_file");
  if (kind === "agent" && /\.vworkflow\.ya?ml$/i.test(file.name)) throw new Error("workflow_not_supported");
  if (kind === "agent" ? !/\.ya?ml$/i.test(file.name) : !/\.vplugin\.zip$/i.test(file.name)) throw new Error("file_type_invalid");
  if (file.size > (kind === "agent" ? 1_000_000 : 5_000_000)) throw new Error("file_too_large");
  const bytes = await readBytes(file);
  const text = kind === "agent" ? new TextDecoder("utf-8", { fatal: true }).decode(bytes) : null;
  if (text && /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|github_pat_|ghp_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|\bsk-[A-Za-z0-9_-]{24,}/.test(text)) throw new Error("credential_marker");
  const hash = crypto.subtle ? await crypto.subtle.digest("SHA-256", bytes) : null;
  return { file: new File([bytes], file.name, { type: file.type, lastModified: file.lastModified }), text, sha256: hash ? Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("") : null };
}
