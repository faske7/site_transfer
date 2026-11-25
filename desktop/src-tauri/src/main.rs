#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod runtime;

use runtime::{Runtime, Status};
use std::sync::Mutex;
use tauri::{AppHandle, Manager, WebviewWindow, WebviewWindowBuilder, WebviewUrl};
use tauri::webview::NewWindowResponse;

struct Gate(Mutex<()>);

fn controller_origin(url: &tauri::Url) -> bool {
    url.scheme() == "tauri" && url.host_str() == Some("localhost")
        && url.port().is_none() && url.username().is_empty() && url.password().is_none()
        && matches!(url.path(), "/" | "/index.html" | "")
}

fn controller_allowed(label: &str, url: &tauri::Url) -> bool {
    label == "main" && controller_origin(url)
}

fn studio_origin(url: &tauri::Url, port: u16) -> bool {
    url.scheme()=="http" && url.host_str()==Some("127.0.0.1") && url.port_or_known_default()==Some(port)
        && url.username().is_empty() && url.password().is_none()
}

fn local(window: &WebviewWindow) -> Result<(), String> {
    let url = window.url().map_err(|_| "Controller origin unavailable")?;
    if !controller_allowed(window.label(), &url) {
        return Err("Native command denied for window or origin".into());
    }
    Ok(())
}

async fn execute<T: Send + 'static>(
    window: WebviewWindow, app: AppHandle,
    operation: impl FnOnce(Runtime) -> Result<T, String> + Send + 'static
) -> Result<T, String> {
    local(&window)?;
    tauri::async_runtime::spawn_blocking(move || {
        let gate = app.state::<Gate>();
        let _guard = gate.0.try_lock().map_err(|_| "Another runtime operation is active".to_string())?;
        operation(Runtime::new(&app)?)
    }).await.map_err(|_| "Runtime operation interrupted".to_string())?
}

#[tauri::command]
async fn runtime_status(window: WebviewWindow, app: AppHandle) -> Result<Status, String> {
    execute(window, app, |r| r.status()).await
}
#[tauri::command]
async fn initialize_runtime(window: WebviewWindow, app: AppHandle) -> Result<Status, String> {
    execute(window, app, |r| { r.initialize()?; r.status() }).await
}
#[tauri::command]
async fn start_runtime(window: WebviewWindow, app: AppHandle) -> Result<Status, String> {
    execute(window, app, |r| { r.start()?; r.status() }).await
}
#[tauri::command]
async fn stop_runtime(window: WebviewWindow, app: AppHandle, confirmed: bool) -> Result<Status, String> {
    if !confirmed { return Err("Confirm stopping the runtime".into()); }
    execute(window, app, |r| { r.stop()?; r.status() }).await
}
#[tauri::command]
async fn open_data_folder(window: WebviewWindow, app: AppHandle) -> Result<(), String> {
    execute(window, app, |r| r.open_data()).await
}
#[tauri::command]
async fn export_project(window: WebviewWindow, app: AppHandle, project_id: String, run_id: String) -> Result<String, String> {
    execute(window, app, move |r| r.export_project(&project_id, &run_id)).await
}
#[tauri::command]
async fn open_browser(window: WebviewWindow, app: AppHandle) -> Result<(), String> {
    execute(window, app, |r| r.open_browser()).await
}
#[tauri::command]
async fn open_studio(window: WebviewWindow, app: AppHandle) -> Result<(), String> {
    let url = execute(window, app.clone(), |r| r.studio_url()).await?;
    if let Some(existing) = app.get_webview_window("studio") {
        existing.close().map_err(|e| e.to_string())?;
    }
    let parsed = url.parse::<tauri::Url>().map_err(|e| e.to_string())?;
    let port = parsed.port().ok_or("Missing runtime port")?;
    WebviewWindowBuilder::new(&app, "studio", WebviewUrl::External(parsed))
        .title("Site Transfer Studio").inner_size(1280.0, 850.0)
        .on_navigation(move |u| studio_origin(u,port))
        .on_new_window(|_, _| NewWindowResponse::Deny)
        .build().map_err(|e| e.to_string())?;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .manage(Gate(Mutex::new(())))
        .setup(|app| {
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Site Transfer — Runtime").inner_size(780.0,760.0)
                .min_inner_size(580.0,520.0)
                .on_navigation(controller_origin)
                .on_new_window(|_, _| NewWindowResponse::Deny)
                .build()?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            runtime_status, initialize_runtime, start_runtime, stop_runtime,
            open_studio, open_browser, open_data_folder, export_project
        ])
        .run(tauri::generate_context!())
        .expect("failed to launch Site Transfer");
}

#[cfg(test)]
mod security_tests {
    use super::*;
    fn url(value: &str) -> tauri::Url { value.parse().unwrap() }

    #[test]
    fn bundled_controller_only() {
        assert!(controller_allowed("main",&url("tauri://localhost/index.html")));
        assert!(!controller_allowed("studio",&url("tauri://localhost/index.html")));
        assert!(!controller_allowed("main",&url("http://127.0.0.1:8080/")));
        assert!(!controller_allowed("main",&url("tauri://other/index.html")));
        assert!(!controller_allowed("main",&url("tauri://localhost/other.html")));
    }

    #[test]
    fn studio_requires_exact_loopback_origin() {
        assert!(studio_origin(&url("http://127.0.0.1:8080/api/v1/projects"),8080));
        for value in ["https://127.0.0.1:8080/", "http://localhost:8080/",
                      "http://127.0.0.1:8081/", "http://127.0.0.1.example:8080/",
                      "http://user@127.0.0.1:8080/", "file:///tmp/test.html"] {
            assert!(!studio_origin(&url(value),8080),"{value}");
        }
    }
}
