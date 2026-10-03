import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Modal, message, theme } from "antd";
import { WeatherThemeProvider } from "./WeatherThemeProvider";
import { weatherColors } from "./tokens";

afterEach(async () => { await act(async () => { cleanup(); message.destroy(); }); });
function Probe() { const { token } = theme.useToken(); return <output data-testid="theme" style={{ color: token.colorText, background: token.colorBgElevated }}>{token.colorText}</output>; }
function luminance(hex: string) {
  const rgb = hex.replace("#", "").match(/../g)!.map((n) => parseInt(n, 16) / 255).map((v) => v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
}
function contrast(a: string, b: string) { const x=luminance(a), y=luminance(b); return (Math.max(x,y)+.05)/(Math.min(x,y)+.05); }
describe("weather theme foundation", () => {
  it("carries the theme into a modal portal", () => {
    render(<WeatherThemeProvider><Modal open title="确认" footer={null}><Probe /></Modal></WeatherThemeProvider>);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByTestId("theme")).toHaveStyle({ color: weatherColors.text, background: weatherColors.popup });
  });
  it("themes static notifications without changing the error text", async () => {
    await act(async () => { message.error(<><span>保存失败：测试错误</span><Probe /></>); });
    const notice = await screen.findByText("保存失败：测试错误");
    expect(notice.closest(".ant-message-notice-wrapper")).toBeInTheDocument();
    expect(screen.getByTestId("theme")).toHaveStyle({ color: weatherColors.text, background: weatherColors.popup });
  });
  it("keeps text, status and control colors readable", () => {
    for (const bg of [weatherColors.surface, weatherColors.popup, "#294761"]) {
      for (const fg of [weatherColors.text,weatherColors.secondary,weatherColors.muted,weatherColors.success,weatherColors.warning,weatherColors.error]) expect(contrast(fg,bg)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(weatherColors.border,bg)).toBeGreaterThanOrEqual(3);
    }
    expect(contrast(weatherColors.onAccent,weatherColors.accent)).toBeGreaterThanOrEqual(4.5);
  });
});
