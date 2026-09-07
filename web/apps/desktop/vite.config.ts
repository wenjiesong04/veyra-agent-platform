import http from "node:http";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

const hopByHop = new Set(["connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"]);

function copyHeaders(headers: http.IncomingHttpHeaders, extras: http.OutgoingHttpHeaders = {}): http.OutgoingHttpHeaders {
  const next: http.OutgoingHttpHeaders = { ...extras };
  for (const [key, value] of Object.entries(headers)) {
    if (value === undefined || hopByHop.has(key.toLowerCase())) continue;
    if (extras.host !== undefined && key.toLowerCase() === "host") continue;
    next[key] = value;
  }
  return next;
}

function optionalCommunityProxy(target = "http://127.0.0.1:8772"): Plugin {
  const upstream = new URL(target);
  return {
    name: "optional-community-proxy",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        if (!req.url?.startsWith("/community-api")) {
          next();
          return;
        }
        const path = req.url.replace(/^\/community-api/, "") || "/";
        const proxyReq = http.request(
          {
            hostname: upstream.hostname,
            port: upstream.port,
            path,
            method: req.method,
            headers: copyHeaders(req.headers, { host: `${upstream.hostname}:${upstream.port}` }),
          },
          (proxyRes) => {
            res.writeHead(proxyRes.statusCode ?? 502, copyHeaders(proxyRes.headers));
            proxyRes.pipe(res);
          },
        );
        proxyReq.on("error", () => {
          if (res.headersSent) {
            res.destroy();
            return;
          }
          res.statusCode = 503;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ detail: "community_unavailable" }));
        });
        req.pipe(proxyReq);
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), optionalCommunityProxy()],
  publicDir: "../../public",
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8771",
        changeOrigin: false,
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
