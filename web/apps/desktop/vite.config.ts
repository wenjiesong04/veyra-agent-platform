import http from "node:http";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";
import { rewriteOriginForCommunityProxy } from "./community-proxy-origin";

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
        const upstreamOrigin = `${upstream.protocol}//${upstream.host}`;
        const headers = copyHeaders(req.headers, { host: `${upstream.hostname}:${upstream.port}` });
        const origin = rewriteOriginForCommunityProxy(req.headers.origin, upstreamOrigin);
        if (origin) headers.origin = origin;
        const proxyReq = http.request(
          {
            hostname: upstream.hostname,
            port: upstream.port,
            path,
            method: req.method,
            headers,
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

function localApiStreamProxy(target = "http://127.0.0.1:8771"): Plugin {
  const upstream = new URL(target);
  return {
    name: "local-api-stream",
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const accept = Array.isArray(req.headers.accept) ? req.headers.accept.join(",") : (req.headers.accept ?? "");
        if (!req.url?.startsWith("/api/") || !accept.includes("text/event-stream")) {
          next();
          return;
        }
        const headers = copyHeaders(req.headers, { host: `${upstream.hostname}:${upstream.port}` });
        let upstreamDone = false;
        const proxyReq = http.request(
          {
            hostname: upstream.hostname,
            port: upstream.port,
            path: req.url,
            method: req.method,
            headers,
          },
          (proxyRes) => {
            const responseHeaders = copyHeaders(proxyRes.headers, {
              "cache-control": "no-cache, no-transform",
              "x-accel-buffering": "no",
            });
            delete responseHeaders["content-length"];
            delete responseHeaders["content-encoding"];
            res.writeHead(proxyRes.statusCode ?? 502, responseHeaders);
            proxyRes.on("end", () => {
              upstreamDone = true;
            });
            proxyRes.pipe(res);
          },
        );
        proxyReq.on("error", () => {
          if (res.writableEnded) return;
          if (res.headersSent) {
            res.destroy();
            return;
          }
          res.statusCode = 502;
          res.end();
        });
        res.on("close", () => {
          if (!upstreamDone) proxyReq.destroy();
        });
        req.pipe(proxyReq);
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), optionalCommunityProxy(), localApiStreamProxy()],
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
