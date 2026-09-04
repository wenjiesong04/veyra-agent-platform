const KEY = "veyra.pending-factory-prompt";

export function writePendingFactoryPrompt(prompt: string): void {
  const value = prompt.trim();
  if (!value) return;
  try {
    sessionStorage.setItem(KEY, value);
  } catch {
    /* sessionStorage may be unavailable in private/test environments. */
  }
}

export function takePendingFactoryPrompt(): string | undefined {
  try {
    const value = sessionStorage.getItem(KEY)?.trim() ?? "";
    sessionStorage.removeItem(KEY);
    return value || undefined;
  } catch {
    return undefined;
  }
}
