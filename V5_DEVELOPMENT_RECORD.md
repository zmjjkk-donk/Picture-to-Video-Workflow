# V5 开发及验收记录

## 范围与环境
- 沿用已有项目和 PRD5，后端、API 客户端、工作流、数据及依赖版本不作更改。
- Python 环境已确认：D:\anaconda\envs\interview-agent\python.exe，Python 3.12.14。
- 前端测试使用真实 React / Ant Design 控件及模拟 API；视觉验收使用隔离数据目录 test-results/v5/runtime 和 Mock Provider，不消耗 Agnes 额度，不操作用户 data/ 数据。
- 业务绑定保护测试与改造前 TypeScript AST 基线逐项比对请求、事件、校验、禁用、轮询、媒体地址和路由。

## 阶段记录
| 阶段 | 已完成内容 | 验证 |
|---|---|---|
| 0 | 保存 Git 状态、九页同视口改造前截图、业务绑定基线 | 后端 50 passed；前端 17 passed；绑定保护 1 passed |
| 1 | 颜色、主题、Portal 通知、材质与降级 | 主题及绑定 4 passed |
| 2 | 导航、全局框架、公共控件 | 公共回归 16 passed；导航及绑定 3 passed |
| 3 | 工作台、项目列表、创建、Upload | 项目及绑定 4 passed |
| 4 | 任务、视频/日志、历史、素材摘要、备份、设置 | 其余页面及绑定 7 passed |
| 5 | 六种宽度、触控、键盘菜单、长文本及降级样式 | 最终阶段回归 9 passed；真实浏览器 54 组页面/宽度检查无根页面水平溢出 |
| 6 | 完整回归、生产构建、静态资源联调、截图及记录 | 后端 50 passed；前端 34 passed；构建及 HTTP 联调通过 |

## 保留的失败与修复记录
1. 基线删除测试因大型辅助功能树查询超时。将四处“已删除控件不存在”查询改成同一控件的精确 aria-label 查询，保留全部断言和超时时限，原 17 项重新全部通过。
2. 基线 AST 工具最初在 jsdom 中以文件 URL 读取失败，改为 Vite raw 导入源代码；未调整业务基线内容。
3. Ant Design 6 通知 DOM 类名与旧版本不同，修正测试目标为实际 notice wrapper，并验证真实通知内主题令牌。
4. 创建 Modal 沿用项目原有英文 OK 按钮，测试最初误用中文名称，按实际控件修正；未更改产品文案。
5. jsdom 不提供 URL.createObjectURL，导致图片预览异常。在 Upload 测试中补充浏览器 Blob URL 原语，保留真实 Upload、四个原始 File、上传顺序和生成参数断言。实际图像预览另用真实浏览器验证。jsdom Canvas 及伪元素计算提示保留在日志中，未屏蔽。
6. Ant Design 6 Select DOM 已不使用旧 selector 类名，测试改用实际 combobox 角色；保存参数和次数断言保留。
7. 真实浏览器发现默认 Tag 规则优先级覆盖主题，增加特定状态样式优先级；核实实际颜色已统一。
8. 320px 浏览器有纵向滚动条时，原 body min-width:320px 产生水平溢出；改为流式宽度，并将设置描述表限制在卡片内部。修复后重新检查九页 × 六种宽度，根页面水平溢出为零；长名称、长描述另在 320px 验证。

日志及截图均位于 test-results/v5/；原失败日志保留，不覆盖。

## 最终自动化结果（2026-10-03）

所有阶段的实现及阶段回归完成后，执行以下完整检查：

| 检查 | 命令与运行目录 | 真实结果 | 日志 |
|---|---|---|---|
| 后端完整测试 | 项目根目录：`& 'D:\anaconda\envs\interview-agent\python.exe' -m pytest` | 50 passed，13.89 秒 | [full-backend.log](test-results/v5/full-backend.log) |
| 前端完整测试 | frontend 目录：`npm run test -- --reporter=dot --maxWorkers=2` | 9 个文件，34 passed，45.71 秒 | [full-frontend.log](test-results/v5/full-frontend.log) |
| 生产构建 | frontend 目录：`npm run build` | TypeScript 检查及 Vite 构建成功；Vite 构建 10.59 秒 | [build-final.log](test-results/v5/build-final.log) |
| 生产静态资源联调 | 项目根目录：`& 'D:\anaconda\envs\interview-agent\python.exe' -m test-results.v5.verify_static`，针对隔离验收服务 | 首页、健康检查、构建后 JS、CSS 均 HTTP 200 | [serving-smoke.log](test-results/v5/serving-smoke.log) |

没有删除、跳过测试或降低验收断言。业务 AST 基线在最终完整回归中通过，未重写基线来适应修改。

日志保留原有 Ant Design 组件弃用提示，以及 jsdom 的 Canvas/伪元素计算限制和部分 React act 提示；这些不等于测试失败，也没有被屏蔽。生产构建仍有 JS 分包超过 500KB 的提示，本次未为消除提示调整依赖或业务加载方式。

## 页面及功能证据

- 九个页面均完成统一主题：工作台、项目列表、创建项目、项目详情、任务详情、素材库、生成记录、备份恢复、设置。通知、弹窗、下拉菜单、状态标签同步适配主题。
- 真实浏览器在 320、390、768、1024、1440、1920px 下分别检查九页，共 54 组；根页面无横向溢出，表格保留容器内滚动。移动端创建入口可见，按钮高度 44px。数据见 [responsive-matrix.json](test-results/v5/responsive-matrix.json)，修复前测量保留在 responsive-before-fix.json。
- 实际页面抽查 26 组文字/背景颜色，对半透明层进行背景合成后计算，全部达到 4.5:1，最低约 6.12:1。此项为抽查，不代表穷举所有像素或状态。数据见 [actual-contrast.json](test-results/v5/actual-contrast.json)。
- 真实浏览器验证四张图片的选择、预览、保存，以及保存后生成按钮启用；图片保持原色、contain 显示。无效图片仍显示原有失败提示且不能生成。没有调用真实 Agnes 视频生成接口。
- 真实浏览器检查菜单键盘展开、必填校验、长中文名称和描述、删除确认弹窗、失败任务提示、下拉菜单及静态生产页面；删除弹窗仅打开及取消，没有删除用户数据。
- 自动化测试覆盖原上传文件、上传顺序和生成参数，项目创建/删除、任务恢复/取消及按钮条件，已删除项目的生成记录保留，原生视频控件与媒体链接，ZIP 导出/导入、设置参数保存、Token 展示和业务事件绑定。
- 原有后端全量回归通过，包括持久化、上传、备份恢复、删除关系、Token 统计、工作流及模拟 Agnes 接口测试。真实 Agnes 服务可用性和成片质量不属于本次视觉优化验证结果。
- 改造前截图 9 张在 before/；改造后页面及交互截图 25 张在 after/。截图使用隔离测试项目，里面的项目名和 Token 数据是测试样本。

## 兼容性验证边界

可用浏览器环境为 Codex 内置浏览器。下列项目没有实际操作系统或第二浏览器的验收条件，不能声称已实测通过：

1. 浏览器原生 200% 缩放；小视口检查不能替代原生缩放。
2. 操作系统的减少动态效果、减少透明度、强制颜色设置。相关 CSS 降级规则及结构测试已完成，系统设置触发后的真实画面未验证。
3. macOS / Safari 及第二种独立浏览器。

因此代码阶段及可执行回归已完成，以上兼容性检查保留为人工验收项。

## 交付及数据保护

- git 范围检查确认 backend/、frontend/src/api/、Python/前端依赖清单无修改；未改 API、数据库、Provider、工作流、Token 统计或删除规则。
- 前端最新生产包已生成到 frontend/dist/。沿用现有启动方式重新启动项目并刷新页面即可查看。
- 本次验收服务使用独立 runtime 数据目录并已停止；用户 data/ 和 API Key 配置未更改，也没有产生真实 API 调用费用。
- .gitignore 仅补充隔离验收 runtime/ 和 browser-inputs/；原测试日志、失败记录和截图保留。没有自动提交或推送 Git。
