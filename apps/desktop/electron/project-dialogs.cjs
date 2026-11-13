const { randomUUID } = require("node:crypto");
const { lstat, realpath } = require("node:fs/promises");
const { isAbsolute } = require("node:path");
const { dialog, shell } = require("electron");

const SYSTEM_PREFIX = "/api/v1/system/";
const DESKTOP_ORIGIN = "veyra://desktop";

function result(status, fields = {}) {
  return Response.json({ schema_version: "1.0", status, ...fields });
}

function failure(status, code, message) {
  return Response.json(
    { schema_version: "1.0", code, message, request_id: randomUUID() },
    { status },
  );
}

async function resolveSelection(path, directory) {
  if (typeof path !== "string" || !isAbsolute(path)) throw new Error("Invalid selection");
  const info = await lstat(path);
  if (info.isSymbolicLink() || (directory ? !info.isDirectory() : !info.isFile())) {
    throw new Error("Selection has the wrong type");
  }
  return realpath(path);
}

async function pickProject(window, action) {
  const directory = action === "select-directory";
  const title = directory ? "Choose a Veyra Project folder" : "Choose a Veyra Project archive";
  const options = directory
    ? { title, properties: ["openDirectory"] }
    : { title, properties: ["openFile"], filters: [{ name: "Veyra Project archive", extensions: ["zip"] }] };
  const { canceled, filePaths } = await dialog.showOpenDialog(window, options);
  const key = directory ? "root_path" : "path";
  if (canceled) return result("cancelled", { [key]: null });
  const path = await resolveSelection(filePaths[0], directory);
  if (!directory && !path.toLowerCase().endsWith(".zip")) throw new Error("Invalid archive");
  return result("selected", { [key]: path });
}

async function revealProject(request, fetchLocal) {
  const payload = await request.json().catch(() => null);
  const projectId = payload?.project_id;
  if (typeof projectId !== "string" || !/^[a-zA-Z0-9_-]{1,128}$/.test(projectId)) {
    return failure(422, "invalid_project_id", "A valid Project ID is required.");
  }
  const response = await fetchLocal(`/api/v1/projects/${encodeURIComponent(projectId)}`);
  if (!response.ok) return response;
  const project = await response.json();
  const root = await resolveSelection(project.root_path, true);
  shell.showItemInFolder(root);
  return result("revealed", { root_path: project.root_path });
}

async function handleProjectDialog(request, window, fetchLocal) {
  const url = new URL(request.url);
  if (!url.pathname.startsWith(SYSTEM_PREFIX)) return null;
  const action = url.pathname.slice(SYSTEM_PREFIX.length);
  if (!["select-directory", "select-archive", "reveal-project"].includes(action)) return null;

  const origin = request.headers.get("origin");
  if (
    url.protocol !== "veyra:" || url.host !== "desktop" || url.search ||
    (origin !== null && origin !== DESKTOP_ORIGIN) ||
    request.method !== "POST" || request.headers.get("X-Veyra-Desktop-Intent") !== action
  ) {
    return failure(403, "desktop_intent_required", "This action requires a Veyra desktop request.");
  }
  if (!window || window.isDestroyed()) {
    return failure(503, "desktop_unavailable", "The Veyra desktop window is unavailable.");
  }

  try {
    return action === "reveal-project"
      ? await revealProject(request, fetchLocal)
      : await pickProject(window, action);
  } catch {
    const message = action === "reveal-project"
      ? "The Project folder could not be shown in the file manager."
      : "The Project selection could not be completed.";
    return failure(500, "directory_picker_failed", message);
  }
}

module.exports = { handleProjectDialog };
