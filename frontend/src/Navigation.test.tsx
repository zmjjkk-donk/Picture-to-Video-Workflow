import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { message } from "antd";
import App from "./App";

let client: QueryClient;
let writes: string[];
beforeEach(() => {
  writes = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), "http://localhost").pathname.replace(/^\/api/, "");
    if (init?.method && init.method !== "GET") writes.push(path);
    const data = path === "/settings" ? { mode:"mock" } : path === "/dashboard/summary" ? { project_count:0,asset_count:0,job_count:0,succeeded_count:0 } : [];
    return new Response(JSON.stringify({success:true,data}),{status:200});
  }));
  client = new QueryClient({defaultOptions:{queries:{retry:false}}});
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={["/dashboard"]}><App /></MemoryRouter></QueryClientProvider>);
});
afterEach(async () => { await act(async () => { cleanup(); client.clear(); message.destroy(); }); vi.unstubAllGlobals(); });

describe("themed shared navigation", () => {
  it("retains all six navigation entries without submitting anything", async () => {
    const menu = within(screen.getByRole("menu"));
    for (const [label,heading] of [["换装项目","PROJECTS / 项目空间"],["素材库","ASSETS / 素材库"],["生成记录","HISTORY / 生成记录"],["备份与恢复","BACKUP / 数据安全"],["系统设置","SETTINGS / 系统设置"],["工作台","OVERVIEW / 工作台概览"]]) {
      fireEvent.click(menu.getByRole("menuitem",{name:new RegExp(`${label}$`)}));
      expect(await screen.findByText(heading)).toBeInTheDocument();
    }
    expect(writes).toEqual([]);
  },20000);
  it("retains the header create entry and original required-field validation", async () => {
    fireEvent.click(screen.getByRole("button",{name:/创建换装任务$/}));
    expect(await screen.findByText("NEW PROJECT / 新建项目")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"创建并上传素材"}));
    expect(await screen.findByText("请输入项目名称")).toBeInTheDocument();
    expect(writes).toEqual([]);
  });
});
