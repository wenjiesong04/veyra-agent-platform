const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

export function isLoopbackHttpOrigin(origin: string): boolean {
  try {
    const parsed = new URL(origin);
    return parsed.protocol === "http:"
      && LOOPBACK_HOSTS.has(parsed.hostname)
      && parsed.username === ""
      && parsed.password === ""
      && (parsed.pathname === "" || parsed.pathname === "/")
      && parsed.search === ""
      && parsed.hash === "";
  } catch {
    return false;
  }
}

export function rewriteOriginForCommunityProxy(
  origin: string | string[] | undefined,
  upstreamOrigin: string,
): string | undefined {
  const value = Array.isArray(origin) ? origin[0] : origin;
  if (!value) return undefined;
  return isLoopbackHttpOrigin(value) ? upstreamOrigin : value;
}
