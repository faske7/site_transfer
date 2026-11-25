"use strict";
const invoke = window.__TAURI__.core.invoke;
const $ = id => document.getElementById(id);
let current = null;
let busy = false;
function buttons() {
  for (const b of document.querySelectorAll("button")) b.disabled = busy;
  if (!busy && current) {
    $("initialize").disabled = !current.docker_ready || current.configured;
    $("start").disabled = !current.docker_ready || !current.configured;
    $("stop").disabled = !current.docker_ready || !current.configured;
    $("studio").disabled = !current.ready;
    $("browser").disabled = !current.ready;
    $("export").disabled = !current.ready;
  }
}
function render(value) {
  current = value;
  $("status").textContent = value.message + (value.port ? " · port " + value.port : "");
  $("services").textContent = value.services.join("\n");
  $("folder").textContent = value.data_folder;
}
async function action(command, args={}, status=true) {
  if (busy) return;
  busy = true; buttons(); $("error").textContent = "";
  $("status").textContent = command === "start_runtime" ? "Building / starting Docker services…" : "Checking local runtime…";
  try {
    const result = await invoke(command, args);
    if (status) render(result);
    else { render(await invoke("runtime_status")); if (typeof result === "string") $("status").textContent = "Exported: "+result; }
  } catch (e) {
    $("error").textContent = String(e);
    if(current) render(current);
    else $("status").textContent = "Runtime status unavailable";
  } finally {busy=false;buttons();}
}
$("refresh").onclick = () => action("runtime_status");
$("initialize").onclick = () => action("initialize_runtime");
$("start").onclick = () => action("start_runtime");
$("stop").onclick = () => {if(confirm("Stop Site Transfer services? Active jobs may be interrupted. Volumes are kept.")) action("stop_runtime",{confirmed:true});};
$("studio").onclick = () => action("open_studio",{},false);
$("browser").onclick = () => action("open_browser",{},false);
$("data").onclick = () => action("open_data_folder",{},false);
$("export").onclick = () => action("export_project",{projectId:$("project").value.trim(),runId:$("run").value.trim()},false);
action("runtime_status");
