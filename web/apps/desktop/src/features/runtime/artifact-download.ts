export function downloadArtifactBlob(blob: Blob, filename: string): void {
  const href = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = href;
  link.download = filename;
  try {
    link.click();
  } finally {
    window.setTimeout(() => URL.revokeObjectURL(href), 1_000);
  }
}
