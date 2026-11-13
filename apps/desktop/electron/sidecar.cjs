const { execFile, spawn } = require('node:child_process');
const net = require('node:net');
const path = require('node:path');
const { setTimeout: delay } = require('node:timers/promises');
const { promisify } = require('node:util');

const LOCAL_HOST = '127.0.0.1';
const LOCAL_PORT = 8771;
const HEALTH_PATH = '/api/v1/health';
const STARTUP_TIMEOUT = 30_000;
const execFileAsync = promisify(execFile);

function localOrigin(port) {
  return `http://${LOCAL_HOST}:${port}`;
}

function existingDataRoot(app) {
  if (process.platform !== 'linux') {
    return path.join(app.getPath('appData'), 'com.veyra.agentplatform');
  }
  const dataHome = process.env.XDG_DATA_HOME;
  const directory = dataHome && path.isAbsolute(dataHome)
    ? dataHome : path.join(app.getPath('home'), '.local', 'share');
  return path.join(directory, 'com.veyra.agentplatform');
}

function sidecarEnvironment(dataRoot, port, buildSha, version) {
  const inherited = {};
  const keys = process.platform === 'win32'
    ? ['SystemRoot', 'WINDIR', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP']
    : ['HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'XDG_DATA_HOME', 'XDG_CONFIG_HOME', 'XDG_RUNTIME_DIR', 'DBUS_SESSION_BUS_ADDRESS'];
  for (const key of keys) {
    if (process.env[key]) inherited[key] = process.env[key];
  }
  const systemRoot = inherited.SystemRoot || inherited.WINDIR;
  const executablePath = process.platform === 'win32'
    ? path.join(systemRoot, 'System32') : '/usr/bin:/bin:/usr/sbin:/sbin';
  const database = path.join(dataRoot, 'v1', 'local', 'app.sqlite3').split(path.sep).join('/');
  return {
    ...inherited,
    PATH: executablePath,
    PYTHONNOUSERSITE: '1',
    VEYRA_LOCAL_MODE: 'release',
    VEYRA_LOCAL_HOST: LOCAL_HOST,
    VEYRA_LOCAL_PORT: String(port),
    VEYRA_LOCAL_DATABASE_URL: `sqlite+aiosqlite:///${database}`,
    VEYRA_LOCAL_PROJECT_STORAGE_ROOT: path.join(dataRoot, 'v1', 'projects'),
    VEYRA_BUILD_SHA: buildSha,
    VEYRA_APP_VERSION: version,
  };
}

function availablePort(port) {
  return new Promise((resolve, reject) => {
    const listener = net.createServer();
    listener.once('error', (cause) => reject(new Error(
      `Cannot start the Local API on ${localOrigin(port)}: ${cause.message}`, { cause },
    )));
    listener.listen(port, LOCAL_HOST, () => {
      const boundPort = listener.address().port;
      listener.close((error) => error ? reject(error) : resolve(boundPort));
    });
  });
}

async function waitForHealth(port, buildSha, stopped, signal) {
  const deadline = Date.now() + STARTUP_TIMEOUT;
  let lastError = 'No health response received';
  while (Date.now() < deadline) {
    signal.throwIfAborted();
    const failure = stopped();
    if (failure) throw new Error(failure);
    let health;
    try {
      const response = await fetch(`${localOrigin(port)}${HEALTH_PATH}`, {
        redirect: 'error',
        signal: AbortSignal.any([signal, AbortSignal.timeout(600)]),
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      health = await response.json();
    } catch (cause) {
      lastError = cause.message;
      await delay(180, undefined, { signal });
      continue;
    }
    if (health?.service !== 'local' || health.build_sha !== buildSha) {
      throw new Error('The Local API did not report the build identity of this application.');
    }
    if (health.status === 'ok' && health.database_ready === true) return;
    lastError = 'The Local API database is still starting';
    await delay(180, undefined, { signal });
  }
  throw new Error(`The Local API did not start: ${lastError}`);
}

async function stopProcess(child, closed, isRunning) {
  if (!isRunning()) return;
  if (process.platform === 'win32') {
    // The PyInstaller bootloader owns a second process on Windows.
    const systemRoot = process.env.SystemRoot || process.env.WINDIR;
    try {
      await execFileAsync(path.join(systemRoot, 'System32', 'taskkill.exe'), [
        '/PID', String(child.pid), '/T', '/F',
      ], { windowsHide: true, timeout: 5_000 });
    } catch (cause) {
      if (isRunning()) {
        child.kill('SIGKILL');
        throw new Error('Could not stop the Local API process tree.', { cause });
      }
    }
  } else {
    child.kill('SIGTERM');
  }
  await Promise.race([closed, delay(5_000, undefined, { ref: false })]);
  if (!isRunning()) return;
  if (process.platform === 'win32') {
    child.kill('SIGKILL');
  } else {
    // The child is spawned in its own process group on POSIX hosts.
    try {
      process.kill(-child.pid, 'SIGKILL');
    } catch (cause) {
      if (cause.code !== 'ESRCH') throw cause;
    }
  }
  await Promise.race([closed, delay(3_000, undefined, { ref: false })]);
  if (isRunning()) throw new Error('The Local API did not stop.');
}

async function startSidecar({ binary, resources, dataRoot, buildSha, version, port, signal }) {
  const boundPort = await availablePort(port);
  signal.throwIfAborted();
  const child = spawn(binary, [], {
    cwd: resources,
    env: sidecarEnvironment(dataRoot, boundPort, buildSha, version),
    stdio: ['ignore', 'inherit', 'inherit'],
    detached: process.platform !== 'win32',
    windowsHide: true,
  });
  let failure;
  child.once('error', (cause) => { failure = `Could not start the Local API: ${cause.message}`; });
  child.once('exit', (code, childSignal) => { failure = `The Local API exited (${code ?? childSignal}).`; });
  const closed = new Promise((resolve) => child.once('close', resolve));
  const isRunning = () => !failure && child.pid !== undefined;
  let stopping;
  const stop = () => stopping ??= stopProcess(child, closed, isRunning);
  try {
    await waitForHealth(boundPort, buildSha, () => failure, signal);
  } catch (cause) {
    await stop();
    throw cause;
  }
  return { port: boundPort, isRunning, stop };
}

module.exports = { existingDataRoot, HEALTH_PATH, LOCAL_PORT, localOrigin, startSidecar, availablePort };
