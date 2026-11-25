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
  async function start() {
    if (!authorized || busy || active) return;
    setBusy(true);setError("");
    try {const job=await api.startCapture(projectId); if(alive.current){setItems(old=>[job,...old.filter(x=>x.id!==job.id)]);setSelected(job.id);setAuthorized(false);}}
    catch(e){if(alive.current)setError(e instanceof Error ? e.message : String(e));}
    finally{if(alive.current)setBusy(false);}
  }
  const job=items.find(x=>x.id===selected) ?? items[0];
  return <div className="capture-panel">
    <h3>Reference capture</h3>
    <p>Public reference routes · desktop and mobile · immutable run history.</p>
    <label className="capture-consent"><input type="checkbox" checked={authorized} onChange={e=>setAuthorized(e.target.checked)}/> I am authorized to capture this reference site.</label>
    <button className="primary" disabled={!loaded||!authorized||active||busy} onClick={()=>void start()}>{active?"Capture in progress":busy?"Starting…":"Start capture"}</button>
    {error&&<p role="alert" className="alert error">{error}</p>}
    {job&&<>
      <label>Capture run<select value={job.id} onChange={e=>setSelected(e.target.value)}>{items.map(x=><option key={x.id} value={x.id}>{new Date(x.created_at).toLocaleString()} · {x.status}</option>)}</select></label>
      <p role="status">Status: <strong>{job.status}</strong> · {job.manifest.completed??0}/{job.manifest.total??0} attempts</p>
      {job.error&&<p className="alert error">{job.error}</p>}
      <div className="capture-grid">{(job.manifest.artifacts??[]).map((a,i)=>{
        const src="/api/v1/projects/"+encodeURIComponent(projectId)+"/captures/"+encodeURIComponent(job.id)+"/screenshots/"+i;
        return <figure key={a.path}><a href={src} target="_blank" rel="noreferrer"><img loading="lazy" src={src} alt={a.viewport+" screenshot of "+a.url}/></a><figcaption>{a.viewport} · {a.width} × {a.height}<small>{a.url}</small></figcaption></figure>;
      })}</div>
      {(job.manifest.errors??[]).map((e,i)=><p key={i} className="alert error">{e.viewport} · {e.url}: {e.error}</p>)}
    </>}
  </div>;
}
