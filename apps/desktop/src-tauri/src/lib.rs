use serde::Deserialize;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::path::Path;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const LOCAL_HOST: &str = "127.0.0.1";
const LOCAL_PORT: u16 = 8771;
const HEALTH_PATH: &str = "/api/v1/health";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(30);
const CONNECT_TIMEOUT: Duration = Duration::from_millis(400);

#[derive(Debug, Deserialize)]
struct HealthResponse {
    status: String,
    service: String,
    build_sha: String,
    database_ready: bool,
}

struct SidecarState {
    child: Mutex<Option<CommandChild>>,
}

impl SidecarState {
    fn new(child: CommandChild) -> Self {
        Self {
            child: Mutex::new(Some(child)),
        }
    }

    fn stop(&self) {
        let child = self.child.lock().ok().and_then(|mut value| value.take());
        if let Some(child) = child {
            let _ = child.kill();
        }
    }
}

impl Drop for SidecarState {
    fn drop(&mut self) {
        self.stop();
    }
}

fn expected_build_sha() -> &'static str {
    option_env!("VEYRA_BUILD_SHA").unwrap_or("unknown")
}

fn app_version() -> &'static str {
    option_env!("VEYRA_APP_VERSION").unwrap_or("0.1.0")
}

fn ensure_loopback_port_is_free() -> Result<(), String> {
    TcpListener::bind((LOCAL_HOST, LOCAL_PORT))
        .map(|listener| drop(listener))
        .map_err(|error| {
            format!("sidecar_port_in_use: cannot reserve http://{LOCAL_HOST}:{LOCAL_PORT}: {error}")
        })
}

fn sidecar_environment(data_root: &Path) -> (String, String) {
    let local_root = data_root.join("v1").join("local");
    let database_path = local_root.join("app.sqlite3");
    let project_root = data_root.join("v1").join("projects");
    let database_url = format!("sqlite+aiosqlite:///{}", database_path.display());
    (database_url, project_root.to_string_lossy().into_owned())
}

fn probe_health(port: u16) -> Result<HealthResponse, String> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&address, CONNECT_TIMEOUT)
        .map_err(|error| format!("health connection failed: {error}"))?;
    stream
        .set_read_timeout(Some(CONNECT_TIMEOUT))
        .map_err(|error| format!("health read timeout setup failed: {error}"))?;
    stream
        .set_write_timeout(Some(CONNECT_TIMEOUT))
        .map_err(|error| format!("health write timeout setup failed: {error}"))?;
    stream
        .write_all(
            format!(
                "GET {HEALTH_PATH} HTTP/1.1\r\nHost: {LOCAL_HOST}\r\nConnection: close\r\n\r\n"
            )
            .as_bytes(),
        )
        .map_err(|error| format!("health request failed: {error}"))?;

    let mut response = Vec::new();
    stream
        .read_to_end(&mut response)
        .map_err(|error| format!("health response failed: {error}"))?;
    let header_end = response
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or_else(|| "health response has no HTTP header terminator".to_owned())?;
    let status_line = response
        .get(..header_end)
        .and_then(|headers| headers.split(|byte| *byte == b'\n').next())
        .ok_or_else(|| "health response has no status line".to_owned())?;
    let status_line = String::from_utf8_lossy(status_line);
    let status_code = status_line
        .split_whitespace()
        .nth(1)
        .ok_or_else(|| "health response has no status code".to_owned())?;
    if status_code != "200" {
        return Err(format!("health returned HTTP {status_code}"));
    }

    serde_json::from_slice(response.get(header_end + 4..).unwrap_or_default())
        .map_err(|error| format!("health response JSON is invalid: {error}"))
}

fn wait_for_health(expected_sha: &str) -> Result<(), String> {
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    let mut last_error = "no health response yet".to_owned();
    while Instant::now() < deadline {
        match probe_health(LOCAL_PORT) {
            Ok(response) => {
                if response.build_sha != expected_sha {
                    return Err(format!(
                        "health_build_sha_mismatch: expected {expected_sha}, got {}",
                        response.build_sha
                    ));
                }
                if response.service != "local" {
                    return Err(format!(
                        "health_service_mismatch: expected local, got {}",
                        response.service
                    ));
                }
                if response.status == "ok" && response.database_ready {
                    return Ok(());
                }
                last_error = format!(
                    "health is not ready: status={}, database_ready={}",
                    response.status, response.database_ready
                );
            }
            Err(error) => last_error = error,
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    Err(format!("sidecar_health_timeout: {last_error}"))
}

fn drain_sidecar_events(mut receiver: tauri::async_runtime::Receiver<CommandEvent>) {
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    println!("veyra-local: {}", String::from_utf8_lossy(&line).trim_end())
                }
                CommandEvent::Stderr(line) => {
                    eprintln!(
                        "veyra-local stderr: {}",
                        String::from_utf8_lossy(&line).trim_end()
                    )
                }
                CommandEvent::Error(error) => eprintln!("veyra-local process error: {error}"),
                CommandEvent::Terminated(status) => {
                    eprintln!("veyra-local terminated with code {:?}", status.code);
                    break;
                }
                _ => {}
            }
        }
    });
}

fn start_sidecar(app: &mut tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let expected_sha = expected_build_sha();
    if !cfg!(debug_assertions) && expected_sha == "unknown" {
        return Err("release desktop build requires VEYRA_BUILD_SHA".into());
    }

    let command = match app.shell().sidecar("veyra-local") {
        Ok(command) => command,
        Err(error) if cfg!(debug_assertions) => {
            eprintln!(
                "veyra-local sidecar is not bundled; run the local API separately in dev: {error}"
            );
            return Ok(());
        }
        Err(error) => return Err(format!("sidecar_missing: {error}").into()),
    };
    ensure_loopback_port_is_free()?;

    let data_root = app.path().app_data_dir()?;
    let home_dir = app.path().home_dir()?;
    let resource_dir = app.path().resource_dir()?;
    let (database_url, project_root) = sidecar_environment(&data_root);
    let mode = if cfg!(debug_assertions) {
        "development"
    } else {
        "release"
    };
    let (receiver, child) = command
        .env_clear()
        .env("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
        .env("HOME", home_dir)
        .env("VEYRA_LOCAL_MODE", mode)
        .env("VEYRA_LOCAL_HOST", LOCAL_HOST)
        .env("VEYRA_LOCAL_PORT", LOCAL_PORT.to_string())
        .env("VEYRA_LOCAL_DATABASE_URL", database_url)
        .env("VEYRA_LOCAL_PROJECT_STORAGE_ROOT", project_root)
        .env("VEYRA_BUILD_SHA", expected_sha)
        .env("VEYRA_APP_VERSION", app_version())
        .current_dir(resource_dir)
        .spawn()?;
    app.manage(SidecarState::new(child));
    drain_sidecar_events(receiver);

    if let Err(error) = wait_for_health(expected_sha) {
        if let Some(state) = app.try_state::<SidecarState>() {
            state.stop();
        }
        return Err(error.into());
    }
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(start_sidecar)
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                if let Some(state) = window.app_handle().try_state::<SidecarState>() {
                    state.stop();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building Veyra desktop shell")
        .run(|app_handle, event| {
            if matches!(event, RunEvent::Exit) {
                if let Some(state) = app_handle.try_state::<SidecarState>() {
                    state.stop();
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn health_request_is_loopback_only() {
        assert_eq!(LOCAL_HOST, "127.0.0.1");
        assert_eq!(LOCAL_PORT, 8771);
        assert_eq!(HEALTH_PATH, "/api/v1/health");
    }

    #[test]
    fn database_url_stays_inside_the_app_data_contract() {
        let data_root = Path::new("/tmp/veyra-test-data");
        let (database_url, projects) = sidecar_environment(data_root);
        assert_eq!(
            database_url,
            "sqlite+aiosqlite:////tmp/veyra-test-data/v1/local/app.sqlite3"
        );
        assert_eq!(projects, "/tmp/veyra-test-data/v1/projects");
    }

    #[test]
    fn http_probe_rejects_a_non_loopback_target_by_construction() {
        let address = SocketAddr::from(([127, 0, 0, 1], LOCAL_PORT));
        assert_eq!(address.ip().to_string(), LOCAL_HOST);
    }
}
