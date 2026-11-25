fn main() {
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(
        tauri_build::AppManifest::new().commands(&[
            "runtime_status", "initialize_runtime", "start_runtime", "stop_runtime",
            "open_studio", "open_browser", "open_data_folder", "export_project"
        ])
    )).expect("failed to build Tauri");
}
