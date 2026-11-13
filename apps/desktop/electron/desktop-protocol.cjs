const { createReadStream } = require('node:fs');
const { stat } = require('node:fs/promises');
const http = require('node:http');
const path = require('node:path');
const { Readable, pipeline } = require('node:stream');
const { localOrigin } = require('./sidecar.cjs');
const { handleProjectDialog } = require('./project-dialogs.cjs');

const DESKTOP_ORIGIN = 'veyra://desktop';
const CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'";
const HOP_BY_HOP = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization', 'proxy-connection',
  'te', 'trailer', 'transfer-encoding', 'upgrade',
]);
const CONTENT_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

function isDesktopUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === 'veyra:' && url.host === 'desktop' && !url.username && !url.password;
  } catch {
    return false;
  }
}

function secureHeaders(headers) {
  const result = new Headers(headers);
  result.set('Content-Security-Policy', CSP);
  result.set('X-Content-Type-Options', 'nosniff');
  return result;
}

function localUnavailable() {
  return Response.json({ detail: 'local_api_unavailable' }, { status: 503, headers: secureHeaders() });
}

function localApiPath(pathname) {
  return pathname === '/api/v1' || pathname.startsWith('/api/v1/');
}

function forwardHeaders(headers) {
  const excluded = new Set([
    ...HOP_BY_HOP,
    ...(headers.get('connection') ?? '').split(',').map((name) => name.trim().toLowerCase()),
  ]);
  return Object.fromEntries([...headers].filter(([name]) => !excluded.has(name)));
}

// Use Node's direct HTTP transport so a system proxy cannot see local requests.
function requestLocal(port, apiPath, { method = 'GET', headers, body, signal } = {}) {
  const origin = localOrigin(port);
  const outbound = new Headers(headers);
  outbound.delete('host');
  outbound.delete('cookie');
  outbound.set('accept-encoding', 'identity');
  if (outbound.has('origin')) outbound.set('origin', origin);
  return new Promise((resolve, reject) => {
    const upstream = http.request(`${origin}${apiPath}`, {
      method,
      headers: forwardHeaders(outbound),
      signal,
      agent: false,
    }, (incoming) => {
      const status = incoming.statusCode;
      const received = new Headers();
      for (let index = 0; index < incoming.rawHeaders.length; index += 2) {
        received.append(incoming.rawHeaders[index], incoming.rawHeaders[index + 1]);
      }
      const resultHeaders = secureHeaders(forwardHeaders(received));
      resultHeaders.delete('set-cookie');
      const location = resultHeaders.get('location');
      if (status >= 300 && status < 400 && location) {
        try {
          const destination = new URL(location, `${origin}${apiPath}`);
          if (destination.origin !== origin || !localApiPath(destination.pathname)) {
            throw new Error('The Local API returned an external redirect.');
          }
          resultHeaders.set('location', `${DESKTOP_ORIGIN}${destination.pathname}${destination.search}`);
        } catch (cause) {
          incoming.destroy();
          reject(cause);
          return;
        }
      }
      if (method === 'HEAD' || status === 204 || status === 205 || status === 304) {
        incoming.resume();
        resolve(new Response(null, { status, headers: resultHeaders }));
      } else {
        resolve(new Response(Readable.toWeb(incoming), { status, headers: resultHeaders }));
      }
    });
    upstream.once('error', reject);
    if (body) {
      pipeline(Readable.fromWeb(body), upstream, (error) => {
        if (error) reject(error);
      });
    } else {
      upstream.end();
    }
  });
}

async function rendererResponse(request, url, renderer) {
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    return new Response(null, { status: 405 });
  }
  try {
    const relative = decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname);
    const file = path.resolve(renderer, `.${relative}`);
    const fromRenderer = path.relative(renderer, file);
    if (!fromRenderer || fromRenderer === '..' || fromRenderer.startsWith(`..${path.sep}`) || path.isAbsolute(fromRenderer)) {
      return new Response(null, { status: 404 });
    }
    const info = await stat(file);
    if (!info.isFile()) return new Response(null, { status: 404 });
    const headers = secureHeaders({
      'content-type': CONTENT_TYPES[path.extname(file)] ?? 'application/octet-stream',
      'content-length': String(info.size),
    });
    const body = request.method === 'HEAD' ? null : Readable.toWeb(createReadStream(file));
    return new Response(body, { headers });
  } catch {
    return new Response(null, { status: 404 });
  }
}

function createDesktopProtocol({ renderer, getSidecar, getWindow }) {
  return async (request) => {
    if (!isDesktopUrl(request.url)) return new Response(null, { status: 404 });
    const url = new URL(request.url);
    if (!localApiPath(url.pathname)) return rendererResponse(request, url, renderer);
    if (request.initiatorOrigin !== DESKTOP_ORIGIN) return new Response(null, { status: 403 });
    const sidecar = getSidecar();
    if (!sidecar?.isRunning()) return localUnavailable();
    try {
      const nativeResponse = await handleProjectDialog(
        request, getWindow(), (apiPath) => requestLocal(sidecar.port, apiPath),
      );
      if (nativeResponse) return nativeResponse;
      return await requestLocal(sidecar.port, `${url.pathname}${url.search}`, request);
    } catch {
      return localUnavailable();
    }
  };
}

module.exports = { createDesktopProtocol, DESKTOP_ORIGIN, isDesktopUrl };
