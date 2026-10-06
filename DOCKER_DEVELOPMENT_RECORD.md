# Docker 单容器开发与验收记录

## 范围和环境

- 承接现有 V5，新增单容器构建和部署配置，保留工作流步骤、Provider、数据库结构及业务接口。完整验收发现取消状态被并发进度覆盖，另作最小保护修复，见下方记录。
- 本机 Python：D:\anaconda\envs\interview-agent\python.exe，Python 3.12.14。
- Docker Desktop 4.90.0；Client / Engine 29.7.2；Linux amd64；Buildx 0.36.1。
- 验收使用 test-results/docker/ 隔离数据、未配置真实 Agnes Key；不会操作正式 data/。
- Node 基础镜像和 Python 基础镜像已拉取，Dockerfile 锁定本次解析的镜像摘要。

## 阶段结果

| 阶段 | 状态 | 证据 |
|---|---|---|
| 0 环境及基线 | 通过 | 后端 50 passed / 16.22s；前端 34 passed / 119.96s；基础镜像拉取成功 |
| 1 构建及运行环境 | 通过 | 镜像构建成功；运行探针 5 项通过，Python 3.12.15 / UID 10001 / FFmpeg / SQLite / 写入权限 |
| 2 启动及网页访问 | 通过 | 路由及静态托管 19 passed；真实容器 HTTP 检查 18 项通过 |
| 3 工作流 | 通过 | 容器 HTTP 工作流检查 10 项通过；Linux 工作流/模拟 Agnes/Token 15 passed |
| 4 持久化和恢复 | 通过 | ZIP/重启/重建/Windows 迁移及失败任务恢复 7 项通过 |
| 5 脚本和部署说明 | 通过 | 构建脚本实际构建成功；脚本 8 项通过，包含自动查找 Docker 的验证 |
| 6 最终回归 | 通过 | Windows / Linux 后端各 72 passed，前端各 34 passed；最终镜像环境 5 项、HTTP 验收 35 项、部署脚本 8 项全部通过 |

原始日志保存在 test-results/docker/，失败日志不覆盖。没有删除测试、跳过测试或降低验收标准。

## 最终完整测试结果

| 检查 | 实际结果 | 日志 |
|---|---|---|
| Windows 完整后端 pytest（中断后补跑） | 72 passed / 14.77s | test-results/docker/resume-final-backend-windows.log |
| Linux 最终镜像完整后端 pytest | 72 passed / 67.17s | test-results/docker/final-backend-linux-fixed.log |
| Windows 完整前端 Vitest（中断后补跑） | 9 文件、34 passed / 68.61s | test-results/docker/resume-final-frontend-windows.log |
| Linux 构建环境完整前端 Vitest | 9 文件、34 passed / 77.62s | test-results/docker/final-frontend-linux-fixed.log |
| 环境与媒体探针 | 5 项通过 | test-results/docker/final-environment-fixed.log |
| 实际容器完整 HTTP 验收 | 35 项通过 | test-results/docker/final-container-all-fixed.log；all-result.json |
| Windows 部署脚本 | 8 项通过 | test-results/docker/final-script-checks.log；script-result.json |
| 生产镜像最终构建 | 成功 | test-results/docker/final-runtime-fixed-build.log |

两套前端保持原有测试文件、断言和 5000ms 用例超时，分别以一个 worker 单独执行；未使用跳过或只运行部分用例。Windows 的所有 Python 操作均使用指定绝对路径，Linux 镜像使用 /usr/local/bin/python。Linux pytest 缓存写入 /tmp/pytest-cache，完整运行没有缓存权限告警。

35 项 HTTP 检查覆盖首页静态资源、九个详情/页面刷新路径、错误路径及 HTTP 方法边界、健康与单 worker 配置、图片内容校验、四图上传保存及服装顺序、五秒 Mock 输出、日志、媒体哈希与 Range、未知 Token、无 Key 的 Agnes 失败和同任务恢复、设置、取消/删除保护、项目与历史记录删除关系、ZIP 文件及校验清单、非法 ZIP 拒绝、恢复、重启重建，以及 Windows 备份迁入 Linux 后恢复原失败任务。保留全部断言，无真实模型请求。

## 失败定位及修复

1. 托管层只使用 StaticFiles 时，九个前端文档路径刷新均 404，HEAD 也失败：新增测试首次 10 failed / 8 passed。增加仅覆盖现有前端路由的回退，API、静态文件及其他路径保持 404。
2. 首次回退在 Windows 的多层路径仍失败（4 failed / 15 passed），原因是 StaticFiles 使用操作系统路径分隔符。仅在路由匹配时归一化分隔符，未改文件访问行为；最终相关 19 项全部通过。三个阶段日志分别保留。
3. HTTP 工作流脚本首次在输出保存前判断完成。现有 Provider 轮询节点可先报告 succeeded；将验收完成条件收紧为最终 finish_job 节点提交，没有改工作流状态逻辑，也未降低视频时长/下载/哈希断言。
4. 最终节点提交后，后台检查点清理还可能触发原有 409 删除保护。验收脚本验证准确的保护错误码并在有界时间内等待清理，仍要求最终成功删除且媒体清理正确，没有屏蔽其他错误。
5. Linux 阶段测试全部通过，但普通用户不能写 /app/.pytest_cache。最终容器测试将 cache_dir 指向可写 /tmp；不关闭缓存、不忽略错误。首次提示保留在日志中。
6. PowerShell Get-FileHash 无法打开原本正在使用的 app.db。改用指定 Python 的只读文件读取记录哈希，没有关闭原服务或写入原数据库。
7. 首次最终回归同时运行 Windows/Linux 前端及其他高负载检查，两套前端均为 33 passed / 1 failed：备份交互用例超过原有 5000ms。单独执行原文件全部 6 项通过（该用例 4162ms）。改为串行执行两套前端、每套一个 worker；不增加超时、不修改用例或减少断言。首次失败日志保留为 final-frontend-windows.log / final-frontend-linux.log。
8. 完整容器验收发现取消任务后，晚到的后台更新把 canceled 改回 processing/succeeded，导致不能及时删除。先添加确定性并发测试，首次 3 项均失败；将 update_job 改为 SQL 原子条件更新，已取消任务拒绝晚到更新。补充“取消提交在失败状态写入前”的第 4 项测试，首次该项失败，再让原失败处理仅识别 JOB_CANCELED 并保持取消状态。最终 4 项及既有工作流、Agnes、删除测试共 29 passed / 8.72s。没有改变图节点、模型请求、恢复入口或数据库结构，也未放宽容器取消/删除断言。失败日志 cancel-race-before.log / cancel-late-failure-before.log 和修复日志 cancel-race-final.log 均保留。
9. 中断后补查镜像源码时，首次检查只读取最后四个 COPY 层，漏掉了先于 pip 安装的 requirements.txt 层，完整性断言失败。确认该层实际包含 app/requirements.txt 后，将它纳入读取，保持全部文件集合及 SHA256 断言不变，27 个文件全部一致。失败及修复日志分别为 resume-source-data-check.log / resume-source-data-check-fixed.log，没有改镜像或业务代码。

## 浏览器证据

最终镜像在容器 18002 端口实际显示现有天气风格页面、任务最终节点、日志及视频。刷新任务详情仍正常。原生视频加载 duration=5、readyState=4、error=null，地址指向同源 18002 端口。见 test-results/docker/browser-video-final.png 和 browser-video-final-state.json。早期 18000 端口证据也保留。截图使用合成色块素材及 Mock 演示，不是真实 Agnes 成片；未将浏览器加载检查表述为真实模型质量验收。

## 验收边界

所有写入都使用 test-results/docker/runtime-* 测试数据及专用测试容器，不删除原用户项目。未调用真实 Agnes 服务；Linux amd64 已测试，其他架构、云平台发布、多副本及任意真实远端任务迁移不在本次结果中。已有 Mock 输出的宏块缩放提示和前端组件弃用/jsdom 提示保留，没有为消除提示改业务或依赖。

原 data/app.db 和 data/workflow_checkpoints.db 最终 SHA256 与开始记录一致，见 final-original-data-check.json。未改 requirements.txt、前端依赖锁、前端业务代码、API、Provider 和模型配置；业务运行代码仅有前端路由托管适配，以及测试发现后补充的取消并发保护。git diff --check 通过。

## 中断续接与最终交付

2026-10-04 续接时，阶段 0–6 的实现及完整验收已经完成，未完成的是清理验收容器和记录离线交付文件。本次核对已有修改及测试日志，保留全部实现，补跑 Windows 完整 pytest / Vitest，通过后完成收尾。上一轮 Windows 72 passed / 14.98s 和 34 passed / 80.19s 日志仍保留；Linux 完整测试及 48 项容器检查使用的是同一个最终镜像，没有把缓存命中表述为重新运行 Linux 测试。

- 镜像：outfit-studio:docker-v1，Linux amd64。
- 镜像 ID：sha256:67b07fd8c069caa565b6de76778494b16ed00343439bab27b7f4f7e39a80b6fa。
- 离线文件：docker-artifacts/outfit-studio-docker-v1.tar，316096000 字节，另附 image-info.json 与 .tar.sha256。
- TAR SHA256：967de54ad3e1dcb968e0eb060c7ac448cadd6ccee46245ef1cf4dffd616335b8。
- 离线校验：12 个运行层存在，18 个 blob 全部逐一通过 SHA256，镜像标签、平台、普通用户及启动命令正确，镜像配置未包含 Agnes Key。见 final-archive-check.json。本次恢复后再次核验整个 TAR 哈希，通过。
- 当前后端源码、requirements.txt 和 README 共 27 个文件与镜像内容逐一一致，见 resume-image-source-check.json；原正式数据库和检查点再次核验未变，见 resume-original-data-check.json。
- 最终容器保持 healthy，日志没有意外 ERROR 或 Traceback，见 resume-final-container-server.log。
- 两个本次创建的验收容器都正常退出（ExitCode 0）并已移除；挂载测试目录、日志、镜像、离线包和原服务均保留，见 final-cleanup.json。

没有创建或填写真实 .env.docker，使用者按 DOCKER_DEPLOYMENT.md 从占位模板复制并自行填写。离线包、实际运行数据和真实配置都已加入 Git 忽略规则，源码配置、测试及部署文档可正常提交。镜像加载后按既有运行脚本启动；需要展示原项目时，单独迁移数据或恢复 ZIP 备份。
