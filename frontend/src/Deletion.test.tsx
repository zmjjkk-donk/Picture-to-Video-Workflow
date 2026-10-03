import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { message } from "antd";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Job, Project } from "./api/types";

const project: Project = { id: "p-1", name: "待删除项目", description: "test", status: "completed", video_ratio: "9:16", duration_seconds: 5, created_at: "2026-10-03T00:00:00Z", updated_at: "2026-10-03T00:00:00Z", asset_count: 4, job_count: 1, token_usage_status: "available", token_total: 20, token_input: 10, token_output: 10 };
const task: Job = { id: "68968372-task", project_id: project.id, project_name: project.name, project_deleted: false, provider: "agnes", status: "failed", progress: 0, current_node: "failed", workflow_version: "v2", created_at: project.created_at };
let projects: Project[];
let jobs: Job[];
let deleteError: string | null;
let requests: Array<{ path: string; method: string }>;
const clients: QueryClient[] = [];

beforeEach(() => {
  projects = [{ ...project }];
  jobs = [{ ...task }];
  deleteError = null;
  requests = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname.replace(/^\/api/, "");
    const method = init?.method ?? "GET";
    requests.push({ path, method });
    if (method === "DELETE" && deleteError) {
      return new Response(JSON.stringify({ detail: { error: { message: deleteError } } }), { status: 409 });
    }
    if (method === "DELETE" && path === `/projects/${project.id}`) {
      projects = [];
      jobs = jobs.map((j) => ({ ...j, project_deleted: true }));
    }
    if (method === "DELETE" && path === `/jobs/${task.id}`) jobs = [];
    let data: unknown = [];
    if (["/projects", "/dashboard/recent-projects"].includes(path)) data = projects;
    if (["/jobs", "/dashboard/recent-jobs"].includes(path)) data = jobs;
    if (path === `/jobs/${task.id}`) data = jobs[0];
    if (path === "/settings") data = { mode: "agnes" };
    if (path === "/dashboard/summary") data = { project_count: projects.length, asset_count: projects.length * 4, job_count: jobs.length, succeeded_count: 0 };
    return new Response(JSON.stringify({ success: true, data, message: "ok", request_id: "test" }), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

afterEach(async () => {
  await act(async () => {
    cleanup();
    clients.forEach((client) => client.clear());
    message.destroy();
  });
  clients.length = 0;
  vi.unstubAllGlobals();
});

function mount(route: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  clients.push(client);
  // Seed other pages to verify deletion invalidates caches, not just the
  // currently visible entry. The server mock is deliberately stateful.
  client.setQueryData(["projects"], projects);
  client.setQueryData(["dashboard", "projects"], projects);
  client.setQueryData(["dashboard", "jobs"], jobs);
  client.setQueryData(["jobs"], jobs);
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>);
}

describe("project deletion across workspaces", () => {
  it.each(["/dashboard", "/projects", "/assets"])("confirms deletion from %s and keeps history across navigation", async (route) => {
    mount(route);
    fireEvent.click(await screen.findByRole("button", { name: `删除项目 ${project.name}` }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/生成记录、历史视频和日志继续保留/)).toBeInTheDocument();
    expect(requests.some((r) => r.method === "DELETE")).toBe(false);
    fireEvent.click(within(dialog).getByRole("button", { name: /^取\s*消$/ }));
    expect(requests.some((r) => r.method === "DELETE")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: `删除项目 ${project.name}` }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "确认删除" }));
    await waitFor(() => expect(requests).toContainEqual({ path: `/projects/${project.id}`, method: "DELETE" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: `删除项目 ${project.name}` })).not.toBeInTheDocument());
    for (const [page, heading] of [["换装项目", "PROJECTS / 项目空间"], ["素材库", "ASSETS / 素材库"], ["工作台", "OVERVIEW / 工作台概览"]]) {
      fireEvent.click(screen.getByRole("menuitem", { name: new RegExp(`${page}$`) }));
      expect(await screen.findByText(heading)).toBeInTheDocument();
      await waitFor(() => expect(screen.queryByRole("button", { name: `删除项目 ${project.name}` })).not.toBeInTheDocument());
    }
    fireEvent.click(screen.getByRole("menuitem", { name: /生成记录$/ }));
    expect(await screen.findByText("所属项目已删除")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除任务 68968372" })).toBeEnabled();
  }, 20000);
});

describe("single task deletion", () => {
  it.each(["/dashboard", "/history"])("deletes failed task from %s without deleting project", async (route) => {
    mount(route);
    fireEvent.click(await screen.findByRole("button", { name: "删除任务 68968372" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/所属项目及其他任务继续保留/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "确认删除" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "删除任务 68968372" })).not.toBeInTheDocument());
    expect(projects).toHaveLength(1);
    expect(requests).toContainEqual({ path: `/jobs/${task.id}`, method: "DELETE" });
    fireEvent.click(screen.getByRole("menuitem", { name: route === "/history" ? /工作台$/ : /生成记录$/ }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "删除任务 68968372" })).not.toBeInTheDocument());
  }, 20000);

  it.each(["succeeded", "canceled"] as const)("allows deleting a %s task", async (status) => {
    jobs[0].status = status;
    mount("/history");
    expect(await screen.findByRole("button", { name: "删除任务 68968372" })).toBeEnabled();
  }, 20000);

  it.each(["/dashboard", "/history"])("requires stopping an active task on %s", async (route) => {
    jobs[0].status = "processing";
    mount(route);
    expect(await screen.findByRole("button", { name: "删除任务 68968372" })).toBeDisabled();
  }, 20000);

  it("keeps the entry and shows the actual API error if deletion is rejected", async () => {
    deleteError = "项目存在正在执行的任务，请先取消任务再删除";
    mount("/projects");
    fireEvent.click(await screen.findByRole("button", { name: `删除项目 ${project.name}` }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "确认删除" }));
    expect(await screen.findByText(deleteError)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: `删除项目 ${project.name}` })).toBeInTheDocument();
    expect(projects).toHaveLength(1);
  }, 20000);

  it("preserves history access but hides resume for a deleted project", async () => {
    jobs[0].project_deleted = true;
    mount(`/jobs/${task.id}`);
    expect(await screen.findByText(/所属项目已删除，历史视频和日志仍可查看/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "恢复任务" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "删除任务 68968372" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "← 返回生成记录" }));
    expect(await screen.findByText("HISTORY / 生成记录")).toBeInTheDocument();
  }, 20000);
});
