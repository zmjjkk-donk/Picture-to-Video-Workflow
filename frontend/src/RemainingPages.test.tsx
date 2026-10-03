import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { message } from "antd";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { QueryClient } from "@tanstack/react-query";
import { mountPage } from "./test/pageHarness";
let client:QueryClient;
afterEach(async()=>{await act(async()=>{cleanup();client?.clear();message.destroy();});vi.unstubAllGlobals();});
describe("remaining pages preserve original operations",()=>{
  it("shows the failure in both the alert and log and resumes exactly once",async()=>{
    const view=mountPage("/jobs/j-ui");client=view.client;
    await waitFor(()=>expect(screen.getAllByText("生成服务暂时不可用")).toHaveLength(2));
    expect(screen.queryByText("取消任务")).not.toBeInTheDocument();
    expect(view.calls.some(c=>c.path.endsWith("/outputs"))).toBe(false);
    fireEvent.click(screen.getByRole("button",{name:/恢复任务$/}));
    await waitFor(()=>expect(view.calls.filter(c=>c.path==="/jobs/j-ui/resume"&&c.method==="POST")).toHaveLength(1));
  });
  it("retains the cancellation and deletion guards for an active job",async()=>{
    const view=mountPage("/jobs/j-ui",{job:{status:"processing",error_message:null}});client=view.client;
    fireEvent.click(await screen.findByRole("button",{name:/取消任务$/}));
    await waitFor(()=>expect(view.calls.filter(c=>c.path==="/jobs/j-ui/cancel"&&c.method==="POST")).toHaveLength(1));
    expect(screen.getByLabelText("删除任务 j-ui")).toBeDisabled();
    expect(screen.queryByText("恢复任务")).not.toBeInTheDocument();
  });
  it("keeps successful video controls, poster and original download link",async()=>{
    const view=mountPage("/jobs/j-ui",{job:{status:"succeeded",progress:100,error_message:null}});client=view.client;
    const download=await screen.findByRole("link",{name:"下载视频"});
    expect(download).toHaveAttribute("href","/video.mp4");expect(download).toHaveAttribute("download");
    const video=view.container.querySelector("video")!;
    expect(video).toHaveAttribute("controls");expect(video).toHaveAttribute("poster","/cover.png");
    expect(screen.queryByText("恢复任务")).not.toBeInTheDocument();
  });
  it("preserves history after project deletion while preventing resume",async()=>{
    const view=mountPage("/jobs/j-ui",{job:{project_deleted:true}});client=view.client;
    expect(await screen.findByText(/历史视频和日志仍可查看/)).toBeInTheDocument();
    expect(screen.queryByText("恢复任务")).not.toBeInTheDocument();
    expect(screen.getByLabelText("删除任务 j-ui")).toBeEnabled();
    fireEvent.click(screen.getByRole("button",{name:"← 返回生成记录"}));
    expect(await screen.findByRole("heading",{name:"生成记录"})).toBeInTheDocument();
  });
  it("exports and imports through the existing ZIP controls and FormData",async()=>{
    const view=mountPage("/backups");client=view.client;
    const download=await screen.findByRole("link",{name:"下载"});
    expect(download.getAttribute("href")).toMatch(/\/api\/backups\/b-ui\/download$/);
    expect(screen.getByRole("button",{name:"导入项目"})).toBeDisabled();
    fireEvent.click(screen.getByRole("button",{name:/创建完整备份$/}));
    await screen.findByText("备份创建成功");
    expect(view.calls.filter(c=>c.path==="/backups/export"&&c.method==="POST")).toHaveLength(1);
    const zip=new File([new Uint8Array([80,75,3,4])],"恢复.zip",{type:"application/zip"});
    await act(async()=>{fireEvent.change(view.container.querySelector('input[type="file"]')!,{target:{files:[zip]}});});
    expect(await screen.findByText("恢复.zip")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button",{name:"导入项目"}));
    await screen.findByText("备份导入成功");
    const imports=view.calls.filter(c=>c.path==="/backups/import"&&c.method==="POST");
    expect(imports).toHaveLength(1);expect((imports[0].body as FormData).get("file")).toBe(zip);
    await waitFor(()=>expect(screen.getByRole("button",{name:"导入项目"})).toBeDisabled());
  });
  it("saves the selected Provider with the existing settings request",async()=>{
    const view=mountPage("/settings");client=view.client;
    await screen.findByText("图像与视频模型");
    fireEvent.mouseDown(screen.getByRole("combobox"));
    fireEvent.click((await screen.findAllByText("Agnes 真实生成")).at(-1)!);
    fireEvent.click(screen.getByRole("button",{name:"保存设置"}));
    await screen.findByText("设置已保存");
    const saves=view.calls.filter(c=>c.path==="/settings"&&c.method==="PATCH");
    expect(saves).toHaveLength(1);expect(JSON.parse(String(saves[0].body))).toEqual({mode:"agnes"});
  });
});
