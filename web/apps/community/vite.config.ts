import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);
const COMMUNITY_UPSTREAM = "http://127.0.0.1:8772";

function isLoopbackHttpOrigin(origin: string): boolean {
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

export default defineConfig({
  plugins: [react()],
  publicDir: "../../public",
  server: {
    host: "127.0.0.1",
    port: 5174,
    proxy: {
      "/api": {
        target: COMMUNITY_UPSTREAM,
        changeOrigin: false,
        configure(proxy) {
          proxy.on("proxyReq", (proxyReq, req) => {
            const origin = req.headers.origin;
            if (typeof origin === "string" && isLoopbackHttpOrigin(origin)) {
              proxyReq.setHeader("origin", COMMUNITY_UPSTREAM);
            }
          });
        },
      },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
});
