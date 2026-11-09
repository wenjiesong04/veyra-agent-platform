use std::process::Command;

fn git_sha() -> Option<String> {
    let output = Command::new("git")
        .args(["rev-parse", "HEAD"])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let sha = String::from_utf8(output.stdout).ok()?.trim().to_owned();
    (sha.len() == 40 && sha.chars().all(|character| character.is_ascii_hexdigit())).then_some(sha)
}

fn main() {
    println!("cargo:rerun-if-env-changed=VEYRA_BUILD_SHA");
    println!("cargo:rerun-if-env-changed=VEYRA_APP_VERSION");

    if std::env::var_os("VEYRA_BUILD_SHA").is_none() {
        if let Some(sha) = git_sha() {
            println!("cargo:rustc-env=VEYRA_BUILD_SHA={sha}");
        }
    }

    tauri_build::build();
}
