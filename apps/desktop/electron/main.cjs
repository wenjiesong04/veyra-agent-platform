const { app, BrowserWindow, dialog, ipcMain, nativeImage, protocol, session, shell } = require('electron');
const { mkdirSync, mkdtempSync, readFileSync, realpathSync, writeSync } = require('node:fs');
const { mkdir, readFile, rm, writeFile } = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { createDesktopProtocol, DESKTOP_ORIGIN, isDesktopUrl } = require('./desktop-protocol.cjs');
const { availablePort, existingDataRoot, LOCAL_PORT, startSidecar } = require('./sidecar.cjs');

protocol.registerSchemesAsPrivileged([{
  scheme: 'veyra',
  privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true },
}]);

const { productName } = require('../package.json');
app.setName(productName);
const icon = path.join(__dirname, '..', 'assets', 'icon.png');
const smoke = process.argv.includes('--veyra-package-smoke');
const dataRoot = smoke
  ? realpathSync(mkdtempSync(path.join(os.tmpdir(), 'veyra-electron-smoke-')))
  : existingDataRoot(app);
const profile = path.join(dataRoot, 'electron');
mkdirSync(profile, { recursive: true });
app.setPath('userData', profile);
app.setPath('sessionData', profile);
if (process.platform === 'win32') app.setAppUserModelId('com.veyra.agentplatform');

const resources = app.isPackaged ? process.resourcesPath
  : path.resolve(app.getAppPath(), '../../build/desktop-package/electron-stage');
const abortStartup = new AbortController();
let mainWindow;
let sidecar;
let startup;
let shutdown;

function externalUrl(value) {
  if (typeof value !== 'string') throw new Error('An HTTP or HTTPS website address is required.');
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) {
    throw new Error('An HTTP or HTTPS website address is required.');
  }
  return url.href;
}

function openExternal(value) {
  return shell.openExternal(externalUrl(value));
}

function createWindow(rendererSession) {
  const window = new BrowserWindow({
    title: productName,
    icon,
    width: 1440,
    height: 960,
    minWidth: 1024,
    minHeight: 720,
    show: false,
    webPreferences: {
      session: rendererSession,
      preload: path.join(__dirname, 'preload.cjs'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });
  window.webContents.on('will-navigate', (event) => event.preventDefault());
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (isDesktopUrl(window.webContents.getURL()) && /^https?:\/\//i.test(url)) {
      void Promise.resolve().then(() => openExternal(url)).catch(console.error);
    }
    return { action: 'deny' };
  });
  if (!smoke) window.once('ready-to-show', () => window.show());
  return window;
}

function configureRenderer(rendererSession) {
  const localPermission = (contents, permission, origin) => (
    contents === mainWindow?.webContents && isDesktopUrl(origin) &&
    ['clipboard-read', 'clipboard-sanitized-write', 'fullscreen'].includes(permission)
  );
  rendererSession.setPermissionCheckHandler(localPermission);
  rendererSession.setPermissionRequestHandler((contents, permission, callback, details) => {
    callback(details.isMainFrame && localPermission(contents, permission, details.requestingUrl));
  });
  rendererSession.protocol.handle('veyra', createDesktopProtocol({
    renderer: path.join(resources, 'renderer'),
    getSidecar: () => sidecar,
    getWindow: () => mainWindow,
  }));
  ipcMain.handle('veyra:open-external', (event, value) => {
    const contents = mainWindow?.webContents;
    if (!contents || event.sender !== contents || event.senderFrame !== contents.mainFrame ||
        event.senderFrame?.origin !== DESKTOP_ORIGIN) {
      throw new Error('The website can only be opened from the Desktop window.');
    }
    return openExternal(value);
  });
}

async function launch() {
  const { buildSha } = JSON.parse(readFileSync(path.join(resources, 'build-info.json'), 'utf8'));
  if (typeof buildSha !== 'string' || !/^[0-9a-f]{7,64}$/.test(buildSha)) {
    throw new Error('The desktop package has no valid build identity.');
  }
  const suffix = process.platform === 'win32' ? '.exe' : '';
  sidecar = await startSidecar({
    binary: path.join(resources, 'sidecar', `veyra-local${suffix}`),
    resources,
    dataRoot,
    buildSha,
    version: app.getVersion(),
    port: smoke ? 0 : LOCAL_PORT,
    signal: abortStartup.signal,
  });
  abortStartup.signal.throwIfAborted();
  const rendererSession = session.fromPartition('persist:veyra-desktop');
  configureRenderer(rendererSession);
  mainWindow = createWindow(rendererSession);
  await mainWindow.loadURL(`${DESKTOP_ORIGIN}/`);
  return buildSha;
}

async function verifyPackagedWorkspace(buildSha, sentinel) {
  if (app.getName() !== productName || mainWindow.getTitle() !== productName) {
    throw new Error('The packaged window is missing the Veyra name.');
  }
  await mainWindow.webContents.executeJavaScript(`(async () => {
    const deadline = Date.now() + 12_000;
    while (!document.querySelector('.app-shell .agent-convo-hero')) {
      if (Date.now() >= deadline) throw new Error('The local workspace did not open.');
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    if (location.hash.startsWith('#/login') || typeof window.veyraDesktop?.openExternal !== 'function') {
      throw new Error('The Desktop renderer did not start in its local workspace.');
    }
    const healthResponse = await fetch('/api/v1/health');
    const health = await healthResponse.json();
    if (!healthResponse.ok || health.build_sha !== ${JSON.stringify(buildSha)} || !health.database_ready) {
      throw new Error('The Desktop renderer cannot reach its Local API.');
    }
    const chooser = await fetch('/api/v1/system/select-directory', { method: 'POST' });
    if (chooser.status !== 403) throw new Error('The file chooser did not require desktop intent.');
    const name = 'Packaged smoke';
    const created = await fetch('/api/v1/projects', {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name }),
    });
    if (created.status !== 201) {
      const response = await created.json().catch(() => ({}));
      throw new Error('The renderer could not create a local Project (HTTP ' +
        created.status + ', ' + (response.code || JSON.stringify(response.detail)) + ').');
    }
    const listed = await fetch('/api/v1/projects');
    if (!listed.ok || !(await listed.json()).projects.some((project) => project.name === name)) {
      throw new Error('The renderer could not read its created Project.');
    }
  })()`);
  if (await readFile(sentinel, 'utf8') !== 'existing workspace') {
    throw new Error('The Local API did not preserve the existing Project data.');
  }
}

function quit(code, smokePassed = false) {
  if (shutdown) return shutdown;
  abortStartup.abort();
  shutdown = (async () => {
    try {
      await startup?.catch(() => {});
      if (mainWindow && !mainWindow.isDestroyed()) mainWindow.destroy();
      await sidecar?.stop();
      if (smoke) {
        if (sidecar) await availablePort(sidecar.port);
        await rm(dataRoot, { recursive: true, force: true, maxRetries: 4, retryDelay: 150 });
      }
      if (smokePassed) writeSync(1, 'electron_package_smoke=ok\n');
    } catch (error) {
      console.error(error);
      code = 1;
    }
    app.exit(code);
  })();
  return shutdown;
}

function fail(error) {
  if (shutdown) return;
  console.error(error);
  if (!smoke) dialog.showErrorBox(productName, error.message);
  void quit(1);
}

if (!app.requestSingleInstanceLock()) {
  app.exit(smoke ? 1 : 0);
} else {
  app.on('second-instance', () => {
    if (!mainWindow || mainWindow.isDestroyed()) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });
  app.on('window-all-closed', () => { void quit(0); });
  app.on('before-quit', (event) => {
    event.preventDefault();
    void quit(0);
  });
  process.on('SIGTERM', () => { void quit(smoke ? 1 : 0); });
  process.on('SIGINT', () => { void quit(smoke ? 1 : 0); });
  void app.whenReady().then(async () => {
    if (shutdown) return;
    const brandIcon = nativeImage.createFromPath(icon);
    if (brandIcon.isEmpty()) throw new Error('The Veyra application icon could not be loaded.');
    if (app.dock) app.dock.setIcon(brandIcon);
    const projectRoot = path.join(dataRoot, 'v1', 'projects');
    const sentinel = path.join(projectRoot, 'upgrade-sentinel.txt');
    startup = (async () => {
      if (smoke) {
        await mkdir(projectRoot, { recursive: true });
        await writeFile(sentinel, 'existing workspace');
      }
      return launch();
    })();
    const buildSha = await startup;
    if (!smoke || shutdown) return;
    await verifyPackagedWorkspace(buildSha, sentinel);
    await quit(0, true);
  }).catch(fail);
}
