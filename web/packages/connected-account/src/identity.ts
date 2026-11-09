export function accountInitials(displayName: string | null, handle: string): string {
  const value = (displayName || handle).trim();
  const parts = value.split(/\s+/).filter(Boolean);
  return parts.length > 1
    ? `${parts[0]?.[0] ?? ""}${parts[1]?.[0] ?? ""}`.toUpperCase()
    : value.slice(0, 2).toUpperCase();
}
