type ScreenshotQuality = {status:string;code:string;warnings?:string[];attempts?:{attempt:number;quality?:{code:string}}[]};
export type Config = {
  version?: number;
  source: { url: string; pages?: string[] };
  target: { project_name: string; backend?: string; frontend?: string };
  [key: string]: unknown;
};
export type Project = { id: string; config: Config; created_at: string };
export type Health = { status: string; checks?: Record<string, boolean> };
export type ProjectPage = { items: Project[]; limit: number; offset: number };

export type Capture = {
  id: string; status: string; error: string | null; created_at: string; attempt?:number; kit_attempt?:number; retry_of?:string|null; heartbeat_at?:string|null; lease_until?:string|null; dispatch_attempts?:number; pipeline_enabled?:boolean; cancel_requested?:boolean; kit_status?:string; kit_info?:{sha256?:string;bytes?:number;error?:string};
  manifest: { capture_quality_version?:number; capture_quality?:{url:string;viewport:string;quality:ScreenshotQuality}[]; device_manifest?:string; device_route_limit?:number; device_captures?:{id:string;label:string;url:string;width:number;height:number;dpr:number;status:string;reason?:string;screenshot_mode?:string;quality?:ScreenshotQuality}[]; interaction_manifest?:string; interaction_states?:{id:string;url:string;viewport:string;action:string;status:string;reason?:string;expectation_verified?:boolean|null;path?:string;quality?:ScreenshotQuality}[]; asset_manifest?:string; asset_count?:number; design_tokens?:string; design_reports?:{path:string;url:string;viewport:string;screenshot_index:number;element_count:number;hover_count:number;animation_count:number;report_schema_version?:number;probe_status?:string;probe_count?:number}[]; completed?: number; total?: number; artifacts?: {path:string;url:string;viewport:string;width:number;height:number;quality?:ScreenshotQuality}[]; errors?: {url:string;viewport:string;error:string}[] };
};
export type ComparisonSummary = {id:string;reference_run:string;implementation_run:string;passes:boolean};
export type Comparison = ComparisonSummary & {reference_project:string;implementation_project:string;reference_only:unknown[][];implementation_only:unknown[][];pixel_tolerance:number;max_changed_percent:number;pairs:{route:string;viewport:string;width:number;height:number;reference_index:number;implementation_index:number;metrics:{changed_percent:number;similarity_percent:number;dimensions_match:boolean;passes:boolean};structure:unknown}[]};
export type Transport = (path: string, init?: RequestInit) => Promise<Response>;
// The desktop adapter can supply a transport in PR-09; web uses same-origin fetch.
export function createClient(transport: Transport = (path, init) => fetch(path, init)) {
  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await transport(path, init);
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(typeof data?.detail === "string" ? data.detail : "Request failed (" + response.status + ")");
    }
    return data as T;
  }
  function post<T>(path: string, config: Config) {
    return request<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(config) });
  }
  return {
    async health(): Promise<Health> {
      const response = await transport("/health/ready");
      if (response.status !== 200 && response.status !== 503) throw new Error("Health request failed");
      return response.json();
    },
    comparisons: (id:string) => request<{items:ComparisonSummary[]}>('/api/v1/projects/'+encodeURIComponent(id)+'/comparisons'),
    comparison: (id:string,cid:string) => request<Comparison>('/api/v1/projects/'+encodeURIComponent(id)+'/comparisons/'+encodeURIComponent(cid)),
    compare: (id:string,reference_run:string,implementation_project:string,implementation_run:string) => request<Comparison>('/api/v1/projects/'+encodeURIComponent(id)+'/comparisons',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reference_run,implementation_project,implementation_run})}),
    captures: (id:string) => request<{items:Capture[]}>("/api/v1/projects/" + encodeURIComponent(id) + "/captures"),
    startCapture: (id:string,pipeline=false) => request<Capture>("/api/v1/projects/" + encodeURIComponent(id) + "/captures", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(pipeline?{authorized:true,pipeline:true}:{authorized:true})}),
    cancelCapture: (id:string,run:string) => request<Capture>("/api/v1/projects/"+encodeURIComponent(id)+"/captures/"+encodeURIComponent(run)+"/cancel",{method:"POST"}),
    retryCapture: (id:string,run:string) => request<Capture>("/api/v1/projects/"+encodeURIComponent(id)+"/captures/"+encodeURIComponent(run)+"/retry",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({authorized:true})}),
    buildKit: (id:string,run:string) => request<{status:string}>("/api/v1/projects/"+encodeURIComponent(id)+"/captures/"+encodeURIComponent(run)+"/build-kit",{method:"POST"}),
    list: (offset = 0) => request<ProjectPage>("/api/v1/projects?limit=50&offset=" + offset),
    get: (id: string) => request<Project>("/api/v1/projects/" + encodeURIComponent(id)),
    validate: (config: Config) => post<{ valid: boolean }>("/api/v1/config/validate", config),
    create: (config: Config) => post<Project>("/api/v1/projects", config),
  };
}
export const api = createClient();

export function newConfig(name: string, url: string, backend: string, frontend: string): Config {
  return {
    version: 1,
    source: { url: url.trim(), pages: ["/"] },
    target: { project_name: name.trim(), backend, frontend },
    browser: { engine: "chromium", headless: true, timeout_ms: 30000 },
    viewports: [{ name: "desktop", width: 1440, height: 900 }, { name: "mobile", width: 390, height: 844 }],
    discovery: { enabled: true, max_pages: 30 },
    interactions: { enabled: true }, measurements: { enabled: true }, assets: { enabled: true },
    documentation: { language: "en" }, execution: { require_review_before_push: true, resume: true, retries: 2 },
  };
}
