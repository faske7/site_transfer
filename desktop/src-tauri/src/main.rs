#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod runtime;

use runtime::{Runtime, Status};
use std::sync::Mutex;
use tauri::{AppHandle, Manager, WebviewWindow, WebviewWindowBuilder, WebviewUrl};
use tauri::webview::NewWindowResponse;

struct Gate(Mutex<()>);

fn local(window: &WebviewWindow) -> Result<(), String> {
    if window.label() != "main" {
        return Err("Native command denied".into());
    }
    let url = window.url().map_err(|_| "Controller origin unavailable")?;
    if url.scheme() != "tauri" || url.host_str() != Some("localhost") {
        return Err("Native command denied for remote origin".into());
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
        .on_navigation(move |u| u.scheme()=="http" && u.host_str()==Some("127.0.0.1") && u.port()==Some(port))
        .on_new_window(|_, _| NewWindowResponse::Deny)
        .build().map_err(|e| e.to_string())?;
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .manage(Gate(Mutex::new(())))
        .invoke_handler(tauri::generate_handler![
            runtime_status, initialize_runtime, start_runtime, stop_runtime,
            open_studio, open_browser, open_data_folder, export_project
        ])
        .run(tauri::generate_context!())
        .expect("failed to launch Site Transfer");
}
