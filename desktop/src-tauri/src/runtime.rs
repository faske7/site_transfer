//! Fixed host-side Docker operations. No arbitrary shell, remote context or file path.
use serde::Serialize;
use std::{
    fs::{self, OpenOptions}, io::{Read, Write}, path::{Path, PathBuf},
    process::{Command, Stdio}, thread, time::{Duration, Instant},
};
use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};
use tauri::{AppHandle, Manager};
use uuid::Uuid;

const PROJECT: &str = "site-transfer";
const CONTEXT: &str = "desktop-linux";
const SERVICES: &[&str] = &["db", "redis", "migrate", "api", "worker"];

#[derive(Serialize)]
pub struct Status {
    pub docker_ready: bool,
    pub configured: bool,
    pub ready: bool,
    pub message: String,
    pub data_folder: String,
    pub port: Option<u16>,
    pub services: Vec<String>,
}

pub struct Runtime { data: PathBuf, resources: PathBuf }

fn run(mut command: Command, seconds: u64) -> Result<String, String> {
    // Capture output to files, not pipes that can deadlock on a verbose build.
    let mut out = tempfile::tempfile().map_err(|e| e.to_string())?;
    let err = tempfile::tempfile().map_err(|e| e.to_string())?;
    command.stdin(Stdio::null()).stdout(out.try_clone().map_err(|e| e.to_string())?).stderr(err);
    let mut child = command.spawn().map_err(|_| "Unable to execute required host command".to_string())?;
    let deadline = Instant::now() + Duration::from_secs(seconds);
    loop {
        match child.try_wait().map_err(|e| e.to_string())? {
            Some(status) if status.success() => break,
            Some(_) => return Err("Host command failed; check Docker Desktop and compose logs in Terminal".into()),
            None if Instant::now() >= deadline => {
                let _ = child.kill(); let _ = child.wait();
                return Err("Host command timed out; inspect Docker state before retrying".into());
            }
            None => thread::sleep(Duration::from_millis(150)),
        }
    }
    use std::io::{Seek, SeekFrom};
    out.seek(SeekFrom::Start(0)).map_err(|e| e.to_string())?;
    let mut text = String::new();
    out.take(2 * 1024 * 1024).read_to_string(&mut text).map_err(|e| e.to_string())?;
    Ok(text.trim().to_string())
}

fn read_port(content: &str) -> Result<u16, String> {
    let mut port = None;
    for line in content.lines() {
        let line = line.trim();
        if let Some(raw) = line.strip_prefix("SITE_TRANSFER_PORT=") {
            if port.is_some() { return Err("Duplicate port setting".into()); }
            let n = raw.parse::<u16>().map_err(|_| "Use a plain numeric SITE_TRANSFER_PORT".to_string())?;
            if n < 1024 { return Err("Use port 1024–65535".into()); }
            port = Some(n);
        }
    }
    Ok(port.unwrap_or(8080))
}

fn valid_env(content: &str) -> Result<u16, String> {
    let mut password_count = 0;
    for raw in content.lines() {
        let line = raw.trim();
        if line.is_empty() || line.starts_with('#') { continue; }
        if let Some(value) = line.strip_prefix("POSTGRES_PASSWORD=") {
            if value.is_empty() || value == "replace-with-a-local-password" {
                return Err("Set a real PostgreSQL password in .env".into());
            }
            password_count += 1;
        } else if !line.starts_with("SITE_TRANSFER_PORT=") {
            return Err("Desktop .env accepts only POSTGRES_PASSWORD and SITE_TRANSFER_PORT".into());
        }
    }
    if password_count != 1 { return Err("Exactly one POSTGRES_PASSWORD is required".into()); }
    read_port(content)
}

impl Runtime {
    pub fn new(app: &AppHandle) -> Result<Self, String> {
        let data = app.path().app_data_dir().map_err(|e| e.to_string())?;
        let resources = app.path().resource_dir().map_err(|e| e.to_string())?.join("runtime");
        fs::create_dir_all(&data).map_err(|e| e.to_string())?;
        fs::set_permissions(&data, fs::Permissions::from_mode(0o700)).map_err(|e| e.to_string())?;
        Ok(Self { data, resources })
    }
    fn env_path(&self) -> PathBuf { self.data.join(".env") }
    fn port(&self) -> Result<u16, String> {
        let path = self.env_path();
        let meta = fs::symlink_metadata(&path).map_err(|_| "Initialize runtime or import the existing .env first".to_string())?;
        if !meta.is_file() || meta.file_type().is_symlink() || meta.permissions().mode() & 0o077 != 0 || meta.len()>16384 {
            return Err("Use a regular .env file with chmod 600".into());
        }
        valid_env(&fs::read_to_string(path).map_err(|_| "Cannot read runtime .env")?)
    }
    fn docker(&self) -> Result<Command, String> {
        let path = ["/usr/local/bin/docker", "/opt/homebrew/bin/docker", "/Applications/Docker.app/Contents/Resources/bin/docker"]
            .iter().map(Path::new).find(|p| p.is_file())
            .ok_or("Install Docker Desktop for Apple Silicon")?;
        let home = std::env::var_os("HOME").ok_or("HOME not available")?;
        let mut cmd = Command::new(path);
        cmd.env_clear().env("HOME",home).env("PATH","/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:/Applications/Docker.app/Contents/Resources/bin");
        cmd.args(["--context", CONTEXT]);
        Ok(cmd)
    }
    fn check_docker(&self) -> Result<(), String> {
        let mut context = self.docker()?;
        context.args(["context","inspect",CONTEXT,"--format","{{.Endpoints.docker.Host}}"]);
        let host = run(context, 10).map_err(|_| "Docker Desktop context desktop-linux is unavailable".to_string())?;
        if !host.starts_with("unix://") { return Err("Only local Unix Docker endpoints are supported".into()); }
        let mut info = self.docker()?;
        info.args(["info","--format","{{.Architecture}}"]);
        let arch = run(info, 15).map_err(|_| "Start Docker Desktop and wait until its engine is ready".to_string())?;
        if !["aarch64","arm64"].contains(&arch.as_str()) { return Err("Native ARM64 Docker engine required".into()); }
        let mut version = self.docker()?;
        version.args(["compose","version"]);
        run(version, 10)?;
        Ok(())
    }
    fn compose(&self, args: &[&str], seconds: u64) -> Result<String, String> {
        self.port()?;
        if !self.resources.join("compose.yaml").is_file() { return Err("Bundled runtime resources missing; rebuild desktop app".into()); }
        let mut cmd = self.docker()?;
        cmd.arg("compose").args(["--project-name",PROJECT,"--project-directory"])
            .arg(&self.resources).arg("--env-file").arg(self.env_path())
            .arg("-f").arg(self.resources.join("compose.yaml")).args(args);
        run(cmd,seconds)
    }
    pub fn initialize(&self) -> Result<(), String> {
        self.check_docker()?;
        if self.env_path().exists() { self.port()?; return Ok(()); }
        let mut cmd = self.docker()?;
        cmd.args(["volume","ls","--format","{{.Name}}"]);
        let volumes = run(cmd,15)?;
        if volumes.lines().any(|v| ["site-transfer_postgres","site-transfer_projects","site-transfer_redis"].contains(&v)) {
            return Err("Existing Site Transfer volumes detected. Open data folder, copy the original .env there, chmod 600, then refresh. Do not create a new password.".into());
        }
        let mut file=OpenOptions::new().write(true).create_new(true).mode(0o600).open(self.env_path()).map_err(|e|e.to_string())?;
        writeln!(file,"POSTGRES_PASSWORD={}\nSITE_TRANSFER_PORT=8080",Uuid::new_v4().simple()).map_err(|e|e.to_string())
    }
    fn mapped_port(&self) -> Result<u16,String> {
        let port = self.port()?;
        let actual = self.compose(&["port","api","8080"],15)?;
        if actual != format!("127.0.0.1:{port}") {
            return Err("Expected Site Transfer API on its configured loopback port".into());
        }
        Ok(port)
    }
    fn client() -> Result<reqwest::blocking::Client,String> {
        reqwest::blocking::Client::builder().no_proxy().redirect(reqwest::redirect::Policy::none())
            .timeout(Duration::from_secs(120)).connect_timeout(Duration::from_secs(3)).build().map_err(|e|e.to_string())
    }
    pub fn studio_url(&self) -> Result<String,String> {
        self.check_docker()?;
        let port = self.mapped_port()?;
        let base = format!("http://127.0.0.1:{port}");
        let response = Self::client()?.get(format!("{base}/health/ready")).timeout(Duration::from_secs(5))
            .send().map_err(|_|"Studio is not ready")?;
        if !response.status().is_success() { return Err("Studio is not ready".into()); }
        let body: serde_json::Value = response.json().map_err(|_|"Unexpected health response")?;
        if body["status"] != "ready" { return Err("Studio is not ready".into()); }
        Ok(base)
    }
    pub fn status(&self) -> Result<Status,String> {
        let docker=self.check_docker();
        let port=self.port();
        let services=if docker.is_ok() && port.is_ok() {
            self.compose(&["ps","--all","--format","{{.Service}}: {{.State}} ({{.Health}})"],15)
                .unwrap_or_default().lines().map(str::to_owned).collect()
        } else { vec![] };
        let ready=docker.is_ok() && port.is_ok() && self.studio_url().is_ok();
        let message=if let Err(e)=&docker { e.clone() } else if let Err(e)=&port {e.clone()}
            else if ready {"Studio API is ready. Check worker state below.".into()}
            else {"Runtime stopped or not ready; start services or check the configured port.".into()};
        Ok(Status{docker_ready:docker.is_ok(),configured:port.is_ok(),ready,message,
            data_folder:self.data.display().to_string(),port:port.ok(),services})
    }
    pub fn start(&self) -> Result<(),String> {
        self.check_docker()?;
        self.compose(&["config","--quiet"],30)?;
        self.compose(&["up","-d","--build","--wait","--wait-timeout","180"],1800)?;
        self.studio_url()?;
        Ok(())
    }
    pub fn stop(&self) -> Result<(),String> {
        self.check_docker()?;
        let mut args=vec!["stop","--timeout","60"];
        args.extend(SERVICES);
        self.compose(&args,150)?;
        Ok(())
    }
    pub fn open_data(&self) -> Result<(),String> {
        let mut cmd=Command::new("/usr/bin/open");cmd.arg(&self.data);run(cmd,10)?;Ok(())
    }
    pub fn open_browser(&self) -> Result<(),String> {
        let url=self.studio_url()?;
        let mut cmd=Command::new("/usr/bin/open");cmd.arg(url);run(cmd,10)?;Ok(())
    }
    pub fn export_project(&self, project: &str, run_id: &str) -> Result<String,String> {
        let project=Uuid::parse_str(project).map_err(|_|"Invalid project UUID")?;
        let run_id=Uuid::parse_str(run_id).map_err(|_|"Invalid capture UUID")?;
        let base=self.studio_url()?;
        let folder=self.data.join("exports").join(project.to_string());
        fs::create_dir_all(&folder).map_err(|e|e.to_string())?;
        if !folder.canonicalize().map_err(|e|e.to_string())?.starts_with(self.data.canonicalize().map_err(|e|e.to_string())?) {
            return Err("Export folder outside app data".into());
        }
        let target=folder.join(format!("reference-kit-{run_id}.zip"));
        let mut response=Self::client()?.get(format!("{base}/api/v1/projects/{project}/captures/{run_id}/reference-kit"))
            .send().map_err(|_|"Export request failed")?.error_for_status().map_err(|_|"Select a completed or partial capture")?;
        if response.headers().get("content-type").and_then(|v|v.to_str().ok())!=Some("application/zip") {
            return Err("Unexpected export content type".into());
        }
        const MAX: u64=520*1024*1024;
        if response.content_length().is_some_and(|n|n>MAX) { return Err("Export too large".into()); }
        let mut temp=tempfile::NamedTempFile::new_in(&folder).map_err(|e|e.to_string())?;
        let bytes=std::io::copy(&mut (&mut response).take(MAX+1),&mut temp).map_err(|e|e.to_string())?;
        if bytes>MAX || bytes==0 {return Err("Invalid export size".into());}
        temp.persist_noclobber(&target).map_err(|_|"Export already exists; review or move the existing ZIP".to_string())?;
        let mut cmd=Command::new("/usr/bin/open");cmd.arg(folder);run(cmd,10)?;
        Ok(target.display().to_string())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn default_port() { assert_eq!(valid_env("POSTGRES_PASSWORD=abc").unwrap(),8080); }
    #[test] fn custom_port() { assert_eq!(valid_env("POSTGRES_PASSWORD=abc\nSITE_TRANSFER_PORT=8090").unwrap(),8090); }
    #[test] fn bad_port() { assert!(read_port("SITE_TRANSFER_PORT=80").is_err()); }
    #[test] fn duplicate_port() { assert!(read_port("SITE_TRANSFER_PORT=8080\nSITE_TRANSFER_PORT=9090").is_err()); }
    #[test] fn deny_extra_env() { assert!(valid_env("POSTGRES_PASSWORD=abc\nCOMPOSE_FILE=other.yaml").is_err()); }
    #[test] fn password_required() { assert!(valid_env("SITE_TRANSFER_PORT=8080").is_err()); }
}
