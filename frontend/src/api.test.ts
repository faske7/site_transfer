import { describe, expect, it, vi } from "vitest";
import { createClient, newConfig } from "./api";

describe("Studio API client", () => {
  it("builds a safe default project configuration", () => {
    const config = newConfig(" demo ", " https://example.com ", "Django", "React");
    expect(config.target.project_name).toBe("demo");
    expect(config.source.url).toBe("https://example.com");
    expect(config.execution).toMatchObject({require_review_before_push:true});
  });
  it("uses same-origin routes and pagination", async () => {
    const transport = vi.fn(async () => Response.json({items:[],limit:50,offset:50}));
    await createClient(transport).list(50);
    expect(transport).toHaveBeenCalledWith("/api/v1/projects?limit=50&offset=50",undefined);
  });
  it("reports API validation errors", async () => {
    const transport = vi.fn(async () => Response.json({detail:"Invalid config"},{status:422}));
    await expect(createClient(transport).validate(newConfig("demo","https://example.com","Django","React"))).rejects.toThrow("Invalid config");
  });
  it("reports unavailable readiness without claiming success", async () => {
    const transport = vi.fn(async () => Response.json({status:"unavailable",checks:{database:false,redis:true}},{status:503}));
    expect((await createClient(transport).health()).status).toBe("unavailable");
  });
  it("creates a project with JSON", async () => {
    const transport = vi.fn(async (_path:string,_init?:RequestInit) => Response.json({id:"demo"},{status:201}));
    const config = newConfig("demo","https://example.com","Django","React");
    await createClient(transport).create(config);
    expect(transport).toHaveBeenCalledWith("/api/v1/projects",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(config)});
  });
});
