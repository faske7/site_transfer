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
  id: string; status: string; error: string | null; created_at: string;
  manifest: { asset_manifest?:string; asset_count?:number; design_tokens?:string; design_reports?:{path:string;url:string;viewport:string;screenshot_index:number;element_count:number;hover_count:number;animation_count:number}[]; completed?: number; total?: number; artifacts?: {path:string;url:string;viewport:string;width:number;height:number}[]; errors?: {url:string;viewport:string;error:string}[] };
};
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
    captures: (id:string) => request<{items:Capture[]}>("/api/v1/projects/" + encodeURIComponent(id) + "/captures"),
    startCapture: (id:string) => request<Capture>("/api/v1/projects/" + encodeURIComponent(id) + "/captures", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({authorized:true})}),
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
