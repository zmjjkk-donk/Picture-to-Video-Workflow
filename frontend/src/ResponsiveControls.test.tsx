import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { mountPage } from "./test/pageHarness";
import type { QueryClient } from "@tanstack/react-query";
import weatherCss from "./weather.css?raw";
let client:QueryClient;
afterEach(()=>{cleanup();client?.clear();vi.restoreAllMocks();vi.unstubAllGlobals();});
it("exposes the existing collapsed menu as a keyboard reachable native button",async()=>{
  vi.spyOn(window,"matchMedia").mockImplementation(query=>({matches:query.includes("max-width"),media:query,onchange:null,addListener(){},removeListener(){},addEventListener(){},removeEventListener(){},dispatchEvent(){return false;}}));
  const view=mountPage("/dashboard");client=view.client;
  const toggle=await screen.findByRole("button",{name:"展开或收起导航"});
  const sider=view.container.querySelector(".app-sider")!;
  await waitFor(()=>expect(sider).toHaveClass("ant-layout-sider-collapsed"));
  await act(async()=>{fireEvent.click(toggle);});
  expect(sider).not.toHaveClass("ant-layout-sider-collapsed");
  expect(screen.getAllByRole("menuitem")).toHaveLength(6);
  fireEvent.click(screen.getByRole("menuitem",{name:/换装项目$/}));
  expect(await screen.findByRole("heading",{name:"换装项目"})).toBeInTheDocument();
  expect(screen.getByRole("button",{name:/创建换装任务$/})).toBeEnabled();
  expect(view.calls.filter(c=>c.method!=="GET")).toHaveLength(0);
});
it("declares reduced motion, solid material fallback and focus feedback",()=>{
  expect(weatherCss).toMatch(/@media\s*\(prefers-reduced-motion:reduce\)[\s\S]*?\.page\s*\{\s*animation:none/);
  expect(weatherCss).toMatch(/@supports not\s*\(backdrop-filter:blur\(10px\)\)[\s\S]*?background:var\(--weather-panel\)/);
  expect(weatherCss).toContain(".nav-toggle:focus-visible");
  expect(weatherCss).toContain("overflow-x:auto");
});
