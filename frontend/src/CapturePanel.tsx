import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import type { Capture } from "./api";

export default function CapturePanel({projectId}:{projectId:string}) {
  const [items,setItems] = useState<Capture[]>([]);
  const [selected,setSelected] = useState("");
  const [authorized,setAuthorized] = useState(false);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState("");
  const [loaded,setLoaded] = useState(false);
  const alive = useRef(false);
  const active = items.some(j => j.status === "queued" || j.status === "running");
  useEffect(() => {
    alive.current = true;
    let running = false;
    async function refresh() {
      if (running) return;
      running = true;
      try { const result = await api.captures(projectId); if (alive.current) {setItems(result.items); setLoaded(true); setError("");} }
      catch(e) {if(alive.current) setError(e instanceof Error ? e.message : String(e));}
      finally {running=false;}
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 2500);
    return () => {alive.current=false; window.clearInterval(timer);};
  },[projectId]);
  async function start(pipeline=false) {
    if (!authorized || busy || active) return;
    setBusy(true);setError("");
    try {const job=await api.startCapture(projectId,pipeline); if(alive.current){setItems(old=>[job,...old.filter(x=>x.id!==job.id)]);setSelected(job.id);setAuthorized(false);}}
    catch(e){if(alive.current)setError(e instanceof Error ? e.message : String(e));}
    finally{if(alive.current)setBusy(false);}
  }
  async function action(kind:"cancel"|"kit"|"retry",id:string){setBusy(true);setError("");try{if(kind==="cancel")await api.cancelCapture(projectId,id);else if(kind==="kit")await api.buildKit(projectId,id);else {const next=await api.retryCapture(projectId,id);setItems(old=>[next,...old.filter(x=>x.id!==next.id)]);setSelected(next.id);setAuthorized(false); }}catch(e){setError(e instanceof Error?e.message:String(e));}finally{setBusy(false);}}
  const job=items.find(x=>x.id===selected) ?? items[0];
  return <div className="capture-panel">
    <h3>Reference capture</h3>
    <p>Public reference routes · desktop and mobile · computed design evidence · immutable run history.</p>
    <label className="capture-consent"><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)}/> I am authorized to capture this reference site.</label>
    <button className="primary" disabled={!loaded||!authorized||active||busy} onClick={()=>void start()}>{active?"Capture in progress":busy?"Starting…":"Start capture"}</button>
    <button className="secondary" disabled={!loaded||!authorized||active||busy} onClick={()=>void start(true)}>Run pipeline (capture + kit)</button>
    {error&&<p role="alert" className="alert error">{error}</p>}
    {job&&<>
      <label>Capture run<select value={job.id} onChange={e=>setSelected(e.target.value)}>{items.map(x=><option key={x.id} value={x.id}>{new Date(x.created_at).toLocaleString()} · {x.status}</option>)}</select></label>
      <p role="status">Status: <strong>{job.status}</strong> · {job.manifest.completed??0}/{job.manifest.total??0} attempts</p>
      {(["queued","running"].includes(job.status)||["pending","building"].includes(job.kit_status??"")&&["completed","partial"].includes(job.status))&&<button className="secondary" disabled={busy||job.cancel_requested} onClick={()=>void action("cancel",job.id)}>{job.cancel_requested?"Cancellation requested" :"Cancel active stage"}</button>}
      <p>Capture attempt {job.attempt??1}/3 · Dispatch reservations {job.dispatch_attempts??0} · Kit attempt {job.kit_attempt??0}/3</p>
      {job.heartbeat_at&&<p>Last recorded progress: {new Date(job.heartbeat_at).toLocaleString()}</p>}
      {job.status==="failed"&&(job.attempt??1)<3&&<button className="secondary" disabled={busy||active||!authorized} onClick={()=>void action("retry",job.id)}>Retry capture as new run</button>}
      <a className="secondary" href={"/api/v1/projects/"+encodeURIComponent(projectId)+"/captures/"+encodeURIComponent(job.id)+"/events"} target="_blank" rel="noreferrer">Lifecycle events (JSON)</a>
      <h3>Pipeline checkpoint</h3>
      <p>Kit: {job.kit_status??"not_requested"}</p>
      {job.kit_info?.error&&<p role="alert">{job.kit_info.error}</p>}
      {["completed","partial"].includes(job.status)&&!job.cancel_requested&&["failed","not_requested"].includes(job.kit_status??"not_requested")&&(job.kit_attempt??0)<3&&<button className="secondary" disabled={busy} onClick={()=>void action("kit",job.id)}>Build / retry kit from saved capture</button>}
      {job.kit_status==="ready"&&<><p>SHA256: <code>{job.kit_info?.sha256}</code></p><a className="primary" href={"/api/v1/projects/"+encodeURIComponent(projectId)+"/captures/"+encodeURIComponent(job.id)+"/pipeline-kit"} download>Download pipeline kit</a><p>Review ZIP locally before using site-transfer publish.</p></>}
      {job.error&&<p className="alert error">{job.error}</p>}
      <div className="capture-grid">{(job.manifest.artifacts??[]).map((a,i)=>{
        const src="/api/v1/projects/"+encodeURIComponent(projectId)+"/captures/"+encodeURIComponent(job.id)+"/screenshots/"+i;
        return <figure key={a.path}><a href={src} target="_blank" rel="noreferrer"><img loading="lazy" src={src} alt={a.viewport+" screenshot of "+a.url}/></a><figcaption>{a.viewport} · {a.width} × {a.height}<small>{a.url}</small></figcaption></figure>;
      })}</div>
      <h3>Assets &amp; Reference Kit</h3>
      {job.manifest.asset_manifest ? <p><a className="secondary" href={"/api/v1/projects/"+encodeURIComponent(projectId)+"/captures/"+encodeURIComponent(job.id)+"/assets"} target="_blank" rel="noreferrer">Asset inventory ({job.manifest.asset_count??0} entries)</a></p> : <p className="muted">No asset inventory for this run.</p>}
      <p>Inventory only. Source asset licenses are unknown; verify permission before reuse.</p>
      {["completed","partial"].includes(job.status) && (job.manifest.artifacts??[]).length>0 && <p><a className="primary" href={"/api/v1/projects/"+encodeURIComponent(projectId)+"/captures/"+encodeURIComponent(job.id)+"/reference-kit"} download>Download Reference Kit (.zip)</a></p>}
      <p className="muted">Review reference evidence before sharing. The kit contains only the selected run, generated Codex instructions and observed evidence.</p>
      <h3>Design intelligence</h3>
      {job.manifest.design_tokens && <p><a className="secondary" href={"/api/v1/projects/"+encodeURIComponent(projectId)+"/captures/"+encodeURIComponent(job.id)+"/design-tokens"} target="_blank" rel="noreferrer">Open design tokens and responsive observations (JSON)</a></p>}
      {(job.manifest.design_reports??[]).length===0 && <p className="muted">No design reports recorded for this run. Older PR-04 captures remain available; start a new capture if you need design data.</p>}
      {(job.manifest.design_reports??[]).map((report,i)=><div className="project-row" key={report.path}>
        <span><strong>{report.viewport} · {report.element_count} sampled elements</strong><small>{report.url}</small><small>{report.hover_count} hover attempts · {report.animation_count} observed animations</small></span>
        <a className="secondary" href={"/api/v1/projects/"+encodeURIComponent(projectId)+"/captures/"+encodeURIComponent(job.id)+"/design/"+i} target="_blank" rel="noreferrer">JSON report</a>
      </div>)}
      {(job.manifest.errors??[]).map((e,i)=><p key={i} className="alert error">{e.viewport} · {e.url}: {e.error}</p>)}
    </>}
  </div>;
}
