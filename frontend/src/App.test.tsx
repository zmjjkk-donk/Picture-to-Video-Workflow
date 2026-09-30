import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const payloads: Record<string, unknown> = {
  "/dashboard/summary": { project_count: 2, asset_count: 8, job_count: 3, succeeded_count: 2 },
  "/dashboard/recent-projects": [],
  "/dashboard/recent-jobs": [],
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input), "http://localhost").pathname.replace("/api", "");
    return new Response(JSON.stringify({ success: true, data: payloads[path] ?? [], message: "ok", request_id: "test" }), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

describe("workbench shell", () => {
  it("renders the dashboard and summary cards", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter></QueryClientProvider>);
    expect(screen.getByText("电商服装换装短视频")).toBeInTheDocument();
    expect(await screen.findByText("让每一套服装都拥有自己的展示视频")).toBeInTheDocument();
    expect(await screen.findByText("成功输出")).toBeInTheDocument();
    expect(screen.getByText("本地演示模式")).toBeInTheDocument();
  });
});
