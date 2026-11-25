import {useEffect,useState} from "react";
import {api} from "./api";
import type {Capture,Comparison,ComparisonSummary,Project} from "./api";

const terminal=(items:Capture[])=>items.filter(x=>["completed","partial"].includes(x.status)&&(x.manifest.artifacts??[]).length>0);
const label=(x:Capture)=>new Date(x.created_at).toLocaleString()+" · "+x.status+" · "+x.id.slice(0,8);
const errorMessage=(e:unknown)=>e instanceof Error?e.message:String(e);
const screenshot=(p:string,r:string,i:number)=>"/api/v1/projects/"+encodeURIComponent(p)+"/captures/"+encodeURIComponent(r)+"/screenshots/"+i;
export default function ComparisonPanel({projectId}:{projectId:string}){
  const [projects,setProjects]=useState<Project[]>([]);
  const [refs,setRefs]=useState<Capture[]>([]);
  const [targets,setTargets]=useState<Capture[]>([]);
  const [ref,setRef]=useState("");
  const [target,setTarget]=useState(projectId);
  const [run,setRun]=useState("");
  const [history,setHistory]=useState<ComparisonSummary[]>([]);
  const [report,setReport]=useState<Comparison|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [page,setPage]=useState(0);
  async function refresh(){
    setError("");
    try{
      const [p,r,h]=await Promise.all([api.list(page),api.captures(projectId),api.comparisons(projectId)]);
      setProjects(p.items);setRefs(terminal(r.items));setHistory(h.items);
    }catch(e){setError(errorMessage(e));}
  }
  useEffect(()=>{void refresh();},[projectId,page]);
  useEffect(()=>{
    let live=true;setTargets([]);setRun("");
    api.captures(target).then(x=>{if(live)setTargets(terminal(x.items));}).catch(e=>{if(live)setError(errorMessage(e));});
    return()=>{live=false;};
  },[target,projectId]);
  async function compare(){
    if(busy||!ref||!run||ref===run)return;
    setBusy(true);setError("");
    try{const value=await api.compare(projectId,ref,target,run);setReport(value);await refresh();}
    catch(e){setError(errorMessage(e));}finally{setBusy(false);}
  }
  async function view(id:string){
    setError("");
    try{setReport(await api.comparison(projectId,id));}catch(e){setError(errorMessage(e));}
  }
  return <section className="capture-panel">
    <h3>Visual comparison</h3>
    <p>Compare saved captures by route path and exact viewport. No new browser visit.</p>
    <button className="secondary" disabled={busy} onClick={()=>{void refresh();void api.captures(target).then(x=>setTargets(terminal(x.items))).catch(e=>setError(errorMessage(e)));}}>Refresh capture choices</button>
    <label>Reference run<select value={ref} disabled={busy} onChange={e=>setRef(e.target.value)}><option value="">Select capture</option>{refs.map(x=><option key={x.id} value={x.id}>{label(x)}</option>)}</select></label>
    <label>Implementation project<select value={target} disabled={busy} onChange={e=>setTarget(e.target.value)}><option value={projectId}>Current project</option>{projects.filter(p=>p.id!==projectId).map(p=><option key={p.id} value={p.id}>{p.config.target.project_name} · {p.config.source.url}</option>)}{target!==projectId&&!projects.some(p=>p.id===target)&&<option value={target}>{target}</option>}</select></label>
    <div className="pagination"><button className="secondary" disabled={page===0||busy} onClick={()=>setPage(p=>Math.max(0,p-50))}>Previous projects</button><button className="secondary" disabled={projects.length<50||busy} onClick={()=>setPage(p=>p+50)}>Next projects</button></div>
    <label>Implementation run<select value={run} disabled={busy} onChange={e=>setRun(e.target.value)}><option value="">Select capture</option>{targets.filter(x=>x.id!==ref).map(x=><option key={x.id} value={x.id}>{label(x)}</option>)}</select></label>
    <button className="primary" disabled={busy||!ref||!run||ref===run} onClick={()=>void compare()}>{busy?"Comparing…":"Compare captures"}</button>
    {error&&<p role="alert" className="alert error">{error}</p>}
    <label>Saved comparisons<select value={report?.id??""} onChange={e=>{if(e.target.value)void view(e.target.value);else setReport(null);}}><option value="">Select report</option>{history.map(h=><option key={h.id} value={h.id}>{h.id.slice(0,8)} · {h.passes?"Within threshold":"Differences found"}</option>)}</select></label>
    {report&&<>
      <p role="status"><strong>{report.passes?"Within threshold":"Differences found"}</strong> · tolerance {report.pixel_tolerance}/255 · max changed {report.max_changed_percent}%</p>
      <p>Unmatched reference: {report.reference_only.length} · unmatched implementation: {report.implementation_only.length}</p>
      <a className="secondary" href={"/api/v1/projects/"+projectId+"/comparisons/"+report.id} target="_blank" rel="noreferrer">Open full comparison JSON</a>
      {report.pairs.map((pair,i)=><section key={i}>
        <h4>{pair.route} · {pair.viewport} · {pair.width} × {pair.height}</h4>
        <p>{pair.metrics.similarity_percent.toFixed(3)}% pixels within tolerance · {pair.metrics.dimensions_match?"Matching dimensions":"Different screenshot dimensions"}</p>
        <div className="capture-grid">{[
          ["Reference",screenshot(report.reference_project,report.reference_run,pair.reference_index)],
          ["Implementation",screenshot(report.implementation_project,report.implementation_run,pair.implementation_index)],
          ["Pixel difference","/api/v1/projects/"+projectId+"/comparisons/"+report.id+"/diff/"+i]
        ].map(([name,src])=><figure key={name}><a href={src} target="_blank" rel="noreferrer"><img loading="lazy" src={src} alt={name+" "+pair.route}/></a><figcaption>{name}</figcaption></figure>)}</div>
        {pair.structure!=null&&<details><summary>Sampled structural differences</summary><pre>{JSON.stringify(pair.structure,null,2)}</pre></details>}
      </section>)}
    </>}
  </section>;
}
