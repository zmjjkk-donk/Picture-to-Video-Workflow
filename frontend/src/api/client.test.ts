import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./client";

afterEach(() => vi.unstubAllGlobals());

describe("upload responses", () => {
  it.each([
    [500, { success: false, error: { code: "INTERNAL_ERROR", message: "服务器内部错误" } }, "服务器内部错误"],
    [400, { detail: { error: { message: "上传文件不是有效图片" } } }, "上传文件不是有效图片"],
    [422, { detail: [{ loc: ["body", "file"], msg: "Field required" }] }, "Field required"],
  ])("shows the backend error for HTTP %s", async (status, body, error) => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
    await expect(api.projects.uploadModel("project", new File(["image"], "model.png", { type: "image/png" }))).rejects.toThrow(error);
  });

  it("reports the HTTP status when the server does not return JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("Bad Gateway", { status: 502 })));
    await expect(api.projects.uploadModel("project", new File(["image"], "model.png"))).rejects.toThrow("上传失败（502）");
  });

  it("sends the original image and clothing form fields and returns the saved asset", async () => {
    const saved = { id: "asset", slot_index: 1, display_name: "第二套服装" };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ success: true, data: saved }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File(["image"], "look.png", { type: "image/png" });
    expect(await api.projects.uploadClothing("project", file, "第二套服装", 1)).toEqual(saved);
    const [input, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(new URL(input, "http://localhost").pathname).toBe("/api/projects/project/assets/clothing");
    expect(init.method).toBe("POST");
    expect(init.headers).toBeUndefined();
    const form = init.body as FormData;
    expect(form.get("file")).toBe(file);
    expect(form.get("name")).toBe("第二套服装");
    expect(form.get("slot_index")).toBe("1");
  });
});
