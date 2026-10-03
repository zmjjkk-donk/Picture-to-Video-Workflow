import type { Asset, DashboardSummary, GeneratedArtifact, Job, Project, VideoOutput, WorkflowLog } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000/api").replace(/\/$/, "");

type Envelope<T> = { success: boolean; data: T; message: string; request_id: string };

function errorMessage(body: any, fallback: string): string {
  const message = body?.detail?.error?.message ?? body?.error?.message;
  if (typeof message === "string" && message) return message;
  if (typeof body?.detail === "string" && body.detail) return body.detail;
  if (Array.isArray(body?.detail)) {
    const messages = body.detail.map((item: any) => item?.msg).filter((item: unknown) => typeof item === "string");
    if (messages.length) return messages.join("；");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, ...init });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.success === false) {
    throw new Error(errorMessage(body, `请求失败（${response.status}）`));
  }
  return (body as Envelope<T>).data;
}

async function upload<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { method: "POST", body: form });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.success === false) throw new Error(errorMessage(body, `上传失败（${response.status}）`));
  return body.data as T;
}

export const api = {
  dashboard: {
    summary: () => request<DashboardSummary>("/dashboard/summary"),
    projects: () => request<Project[]>("/dashboard/recent-projects"),
    jobs: () => request<Job[]>("/dashboard/recent-jobs"),
  },
  projects: {
    delete: (id: string) => request<null>(`/projects/${id}`, { method: "DELETE" }),
    list: () => request<Project[]>("/projects"),
    get: (id: string) => request<Project>(`/projects/${id}`),
    assets: (id: string) => request<Asset[]>(`/projects/${id}/assets`),
    create: (payload: { name: string; description?: string }) => request<Project>("/projects", { method: "POST", body: JSON.stringify(payload) }),
    update: (id: string, payload: Record<string, unknown>) => request<Project>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
    uploadModel: (id: string, file: File) => { const form = new FormData(); form.append("file", file); return upload<Asset>(`/projects/${id}/assets/model`, form); },
    uploadClothing: (id: string, file: File, name: string, slot: number) => { const form = new FormData(); form.append("file", file); form.append("name", name); form.append("slot_index", String(slot)); const query = new URLSearchParams({ name, slot_index: String(slot) }); return upload<Asset>(`/projects/${id}/assets/clothing?${query.toString()}`, form); },
    reorder: (id: string, assetIds: string[]) => request<null>(`/projects/${id}/assets/reorder`, { method: "POST", body: JSON.stringify({ asset_ids: assetIds }) }),
    createJob: (id: string, clothingOrder: string[], provider = "mock") => request<Job>(`/projects/${id}/jobs`, { method: "POST", body: JSON.stringify({ provider, clothing_order: clothingOrder }) }),
  },
  jobs: {
    delete: (id: string) => request<null>(`/jobs/${id}`, { method: "DELETE" }),
    list: () => request<Job[]>("/jobs"),
    get: (id: string) => request<Job>(`/jobs/${id}`),
    logs: (id: string) => request<WorkflowLog[]>(`/jobs/${id}/logs`),
    steps: (id: string) => request<any[]>(`/jobs/${id}/steps`),
    artifacts: (id: string) => request<GeneratedArtifact[]>(`/jobs/${id}/artifacts`),
    outputs: (id: string) => request<VideoOutput[]>(`/jobs/${id}/outputs`),
    retry: (id: string) => request<Job>(`/jobs/${id}/retry`, { method: "POST" }),
    resume: (id: string) => request<Job>(`/jobs/${id}/resume`, { method: "POST" }),
    cancel: (id: string) => request<Job>(`/jobs/${id}/cancel`, { method: "POST" }),
  },
  backups: {
    list: () => request<any[]>("/backups"),
    export: () => request<any>("/backups/export", { method: "POST" }),
    import: (file: File) => { const form = new FormData(); form.append("file", file); return upload<any>("/backups/import", form); },
    downloadUrl: (id: string) => `${API_BASE}/backups/${id}/download`,
  },
  settings: {
    get: () => request<Record<string, unknown>>("/settings"),
    update: (payload: Record<string, unknown>) => request<Record<string, unknown>>("/settings", { method: "PATCH", body: JSON.stringify(payload) }),
    providers: () => request<any[]>("/providers"),
  },
};
