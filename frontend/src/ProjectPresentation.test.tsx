import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { message } from "antd";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mountPage } from "./test/pageHarness";
import type { QueryClient } from "@tanstack/react-query";
let client:QueryClient;
afterEach(async()=>{ await act(async()=>{cleanup();client?.clear();message.destroy();});vi.unstubAllGlobals(); });

describe("project presentation preserves behavior",()=>{
  it("keeps known and unavailable Token values in project rows",async()=>{
    const view=mountPage("/projects",{tokenStatus:"unavailable"});client=view.client;
    expect(await screen.findByText("Token：接口未提供用量数据")).toBeInTheDocument();
    expect(screen.queryByText("Token 消耗 0")).not.toBeInTheDocument();
    expect(screen.getByLabelText("删除项目 页面测试项目")).toBeEnabled();
  });
  it("creates a project through the existing modal with the original fields",async()=>{
    const view=mountPage("/projects");client=view.client;
    fireEvent.click(screen.getByRole("button",{name:/新建项目$/}));
    const dialog=within(await screen.findByRole("dialog"));
    fireEvent.change(dialog.getByPlaceholderText("例如：春季女装换装展示"),{target:{value:"秋日衣橱"}});
    fireEvent.change(dialog.getByPlaceholderText("记录本次视频的用途和素材说明"),{target:{value:"三套服装"}});
    fireEvent.click(dialog.getByRole("button",{name:"OK"}));
    await waitFor(()=>expect(view.calls.filter(c=>c.path==="/projects"&&c.method==="POST")).toHaveLength(1));
    expect(JSON.parse(String(view.calls.find(c=>c.method==="POST")!.body))).toEqual({name:"秋日衣橱",description:"三套服装"});
    expect(await screen.findByText("LOOK 01")).toBeInTheDocument();
  },20000);
  it("saves four original File objects in order before enabling generation",async()=>{
    // jsdom lacks Blob URL APIs. Keep Ant Design's real Upload and request
    // handling, supplying only the browser primitive used by its preview.
    const createObjectURL=vi.fn(()=>"blob:upload-preview");
    const revokeObjectURL=vi.fn();
    class PreviewURL extends URL {
      static createObjectURL=createObjectURL;
      static revokeObjectURL=revokeObjectURL;
    }
    vi.stubGlobal("URL",PreviewURL);
    const view=mountPage("/projects/p-ui",{mode:"agnes"});client=view.client;
    await screen.findByText("LOOK 01");
    expect(screen.getByRole("button",{name:/生成换装视频$/})).toBeDisabled();
    const inputs=view.container.querySelectorAll('input[type="file"]');
    expect(inputs).toHaveLength(4);
    const files=[0,1,2,3].map(i=>new File([Uint8Array.from(atob("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aF1kAAAAASUVORK5CYII="),c=>c.charCodeAt(0))],`图${i}.png`,{type:"image/png"}));
    await act(async()=>{files.forEach((file,i)=>fireEvent.change(inputs[i],{target:{files:[file]}}));});
    await waitFor(()=>expect(view.container.querySelectorAll(".ant-upload-list-item")).toHaveLength(4));
    expect(createObjectURL).toHaveBeenCalledTimes(4);
    expect(view.calls.filter(c=>c.method==="POST")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button",{name:/保存上传素材$/}));
    await screen.findByText("素材已保存");
    const uploads=view.calls.filter(c=>c.method==="POST");
    expect(uploads.map(c=>c.path)).toEqual(["/projects/p-ui/assets/model","/projects/p-ui/assets/clothing","/projects/p-ui/assets/clothing","/projects/p-ui/assets/clothing"]);
    uploads.forEach((call,i)=>expect((call.body as FormData).get("file")).toBe(files[i]));
    expect(uploads.slice(1).map(c=>(c.body as FormData).get("slot_index"))).toEqual(["0","1","2"]);
    await waitFor(()=>expect(screen.getByRole("button",{name:/生成换装视频$/})).toBeEnabled());
    fireEvent.click(screen.getByRole("button",{name:/生成换装视频$/}));
    await waitFor(()=>expect(view.calls.filter(c=>c.path==="/projects/p-ui/jobs"&&c.method==="POST")).toHaveLength(1));
    const submission=view.calls.find(c=>c.path==="/projects/p-ui/jobs"&&c.method==="POST")!;
    expect(JSON.parse(String(submission.body))).toEqual({provider:"agnes",clothing_order:["a-1","a-2","a-3"]});
  },20000);
});
