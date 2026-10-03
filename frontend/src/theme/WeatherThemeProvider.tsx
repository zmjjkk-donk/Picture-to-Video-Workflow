import type { PropsWithChildren } from "react";
import { ConfigProvider } from "antd";
import { weatherTheme } from "./tokens";

// Static notifications render outside the app tree. Theme their holder without
// changing any message callback, request or submission lifecycle.
ConfigProvider.config({
  holderRender: (children) => <ConfigProvider theme={weatherTheme}>{children}</ConfigProvider>,
});
export function WeatherThemeProvider({ children }: PropsWithChildren) {
  return <ConfigProvider theme={weatherTheme}>{children}</ConfigProvider>;
}
