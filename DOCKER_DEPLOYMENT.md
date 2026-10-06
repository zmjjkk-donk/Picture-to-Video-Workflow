# Docker 单容器部署

## 1. 运行方式与前提

一个 Linux 容器运行 FastAPI / Uvicorn，同时提供前端页面、API、图片和视频。SQLite、LangGraph 检查点及媒体保存在宿主机挂载目录中。前端在构建阶段编译，正式运行不需要 Node.js、独立数据库、缓存或 GPU。

需要 Docker Engine 正常运行并使用 Linux 容器模式，支持 BuildKit 多阶段构建。本次验证环境：Docker Desktop 4.90.0、Engine 29.7.2、Linux amd64。基础镜像摘要固定在 Dockerfile 中；更新摘要需重新执行完整验证。

Windows 脚本使用 PowerShell 7。其他系统可使用本文提供的 Docker 原生命令。`<PROJECT_ROOT>` 是项目源码位置，`<HOST_DATA_DIR>` 是专门用于容器的持久化目录；请替换占位符。电脑不需要另装 Python、Node.js 或 FFmpeg。现有本机启动方式仍保留。

本项目当前面向单机使用，保持单个应用容器和一个 Uvicorn worker。任务执行保护保存在进程内，不应直接多副本运行或提高 worker 数量。

## 2. Windows 快速启动

先打开 Docker Desktop，等待引擎就绪。进入项目目录：

```powershell
Set-Location "<PROJECT_ROOT>"
if (-not (Test-Path -LiteralPath '.env.docker')) {
    Copy-Item -LiteralPath '.env.docker.example' -Destination '.env.docker'
}
```

复制操作只需首次执行，不要覆盖已经填写的配置。编辑 `.env.docker`：

```text
AGNES_API_KEY=
```

留空可以使用 Mock 演示。真实生成时填入自己的 Key，值不要加引号，不要使用 `export`；其余参数可沿用示例。Docker 的环境文件解析方式与项目本机 `.env` 加载器不同，不建议直接复用原 `.env`。

构建并启动：

```powershell
& '.\scripts\docker-build.ps1'
& '.\scripts\docker-run.ps1'
```

默认镜像 `outfit-studio:docker-v1`，容器 `outfit-studio`，数据目录 `<PROJECT_ROOT>\docker-data`。访问 http://127.0.0.1:8000/，API 文档为 http://127.0.0.1:8000/docs。

如果本机原服务占用 8000，改用其他宿主机端口：

```powershell
& '.\scripts\docker-run.ps1' -Port 18000 -DataDir '<HOST_DATA_DIR>' -Name 'outfit-studio-demo'
```

访问 http://127.0.0.1:18000/。脚本根据自身位置定位源码，不要求调用者当前目录与项目相同，支持带空格的路径。数据目录不能包含逗号。脚本不会替换已有同名容器或删除数据；遇到冲突会报错，需明确选择另一个名称或按更新流程处理。

如果 `docker` 没有加入 PATH，脚本会查找 Docker Desktop 的常见安装位置；也可传入 `-DockerExe '<DOCKER_EXE>'`。可使用 `-DryRun` 查看参数，此选项不启动容器、不创建目录，也不打印 Key 的值。

首次打开后，在系统设置中选择 Mock Provider，创建项目，上传并保存四张图片，再生成视频。准备好 Key 后可切换为 Agnes，真实调用仍遵循现有工作流。

## 3. Linux 原生命令

以下命令从项目根目录执行。使用新的独立数据目录，应用用户 UID/GID 为 10001：

```bash
if [ ! -f .env.docker ]; then
  cp .env.docker.example .env.docker
fi
mkdir -p docker-data
sudo chown 10001:10001 docker-data
docker build --build-arg VITE_API_BASE=/api -t outfit-studio:docker-v1 .
docker run -d \
  --name outfit-studio \
  --restart unless-stopped \
  --stop-timeout 150 \
  --publish 127.0.0.1:8000:8000 \
  --env-file .env.docker \
  --env APP_DATA_DIR=/app/data \
  --mount "type=bind,source=$(pwd)/docker-data,target=/app/data" \
  outfit-studio:docker-v1
```

修改 `.env.docker` 后需要重新创建容器才能加载新值，仅重启不会更新 Docker 注入的环境变量。已有数据目录需保证 UID 10001 对数据库、子目录和媒体文件有读写权限；不要将任意系统目录当作应用数据目录。

如选择命名数据卷，可先创建数据卷，再将 `--mount` 改为 `type=volume,source=outfit-studio-data,target=/app/data`。空卷会继承镜像目录权限；已存在的卷需验证权限。挂载持久化不替代 ZIP 备份。

## 4. 配置、网络与媒体

- `VITE_API_BASE=/api` 在镜像构建时写入前端，运行时设置该变量不会改变已经构建的页面。
- Uvicorn 在容器内监听 `0.0.0.0:8000`；默认脚本只将端口发布到宿主机回环地址。局域网或云端访问需要另行配置发布地址、域名、访问控制和 HTTPS，不属于本次本地部署默认范围。
- `APP_DATA_DIR` 固定为 `/app/data`，数据库、检查点、素材、生成视频、封面和备份都放在挂载目录中。
- Python 依赖沿用 requirements.txt，包含现有测试依赖；没有为缩小镜像擅自拆分或升级。最终镜像不包含 Node.js、node_modules、本机 .env、真实 Key 或用户数据。
- FFmpeg 位于 `/usr/bin/ffmpeg`，通过 `IMAGEIO_FFMPEG_EXE` 指定。应用以普通用户运行。
- 默认 Mock 模式不需要外部模型网络；Agnes 模式需要可访问接口及其返回的媒体地址。
- 镜像拉取、npm/pip 下载与运行时 Agnes 访问属于不同网络环节。代理问题应分别检查，不能直接认为容器里的 `127.0.0.1` 是宿主机。Docker Desktop 中容器访问宿主机服务可使用 `host.docker.internal`；这不等于镜像拉取代理已配置。本项目不会自动修改系统或 Docker Desktop 的代理设置。

## 5. 数据迁移与备份恢复

迁移前等待任务结束，创建并下载 ZIP 备份。容器初次运行默认是空工作台，不会自动出现开发者电脑上的项目。

### 直接复制数据

停止原本地服务后，将原 data/ 的完整内容复制到新的 `<HOST_DATA_DIR>`，保留原目录，再用该目录启动容器。不能只复制 app.db，否则素材、检查点和视频会缺失。复制后验证项目列表、素材、历史视频、Token 状态及失败任务恢复。

Windows 到 Linux 的路径迁移已用隔离 Mock 备份验证，包括历史视频校验和原失败任务 ID 恢复成功；不保证任意历史版本或真实 Agnes 远端任务都可恢复。

### ZIP 导入和恢复

现有页面可创建、下载和导入备份。**导入 ZIP 只创建备份记录，恢复需调用已有恢复 API；replace 会替换当前业务数据库和项目目录。** 请先备份当前数据，并确保没有任务正在执行。

PowerShell 7 示例：

```powershell
$baseUrl = 'http://127.0.0.1:8000'
$backupPath = '<BACKUP_ZIP>'
$imported = Invoke-RestMethod -Method Post -Uri "$baseUrl/api/backups/import" -Form @{file = Get-Item -LiteralPath $backupPath}
$backupId = $imported.data.id
Invoke-RestMethod -Method Post -Uri "$baseUrl/api/backups/$backupId/restore?mode=replace"
```

恢复完成后刷新工作台。ZIP 包含数据库、检查点、项目清单、素材和媒体及 SHA256 校验清单；不会递归打包 backups/ 下的旧 ZIP。

## 6. 查看状态、停止、更新和回退

以下命令中的 docker 可以替换为 Docker 可执行文件绝对路径；自定义容器名时同步替换 outfit-studio。

```text
docker ps
docker logs --tail 100 outfit-studio
docker logs -f outfit-studio
docker inspect --format "{{.State.Health.Status}}" outfit-studio
docker stop --time 150 outfit-studio
docker start outfit-studio
```

健康检查访问 `/api/health`，包含数据库连接检查。`unhealthy` 本身不会触发 Docker 自动重启；`unless-stopped` 主要处理进程退出和引擎恢复后的启动行为。Key 未配置也可以健康运行，因为 Mock 和页面不依赖 Agnes。

更新流程：等待任务结束 → 导出备份 → 给旧镜像保留单独标签 → 构建新镜像 → 停止并删除旧容器 → 使用相同数据目录创建新容器。删除容器不等于删除挂载目录，**不要删除数据目录或数据卷**。

回退时停止新容器，使用旧镜像和相同数据目录重新创建。若未来版本更改数据库结构，还需使用与旧版本匹配的备份；本次封装没有更改数据库结构。

正在执行的任务随容器停止而中断，现有程序不会自动恢复全部任务，也不会自动将 processing 状态改成 failed。关闭前等待任务结束；如果发生意外中断，先查看记录，不要盲目重复提交真实模型请求。本次没有新增自动恢复机制。

## 7. 测试与镜像交付

本机 Python 测试继续使用既有环境的绝对路径。本项目开发环境为 `D:\anaconda\envs\interview-agent\python.exe`，他人机器用自己的虚拟环境路径代替 `<PYTHON_EXE>`：

```powershell
& '<PYTHON_EXE>' -m pytest
```

前端完整测试也可以在 Linux 构建阶段运行：

```text
docker build --target frontend-test --progress=plain -t outfit-studio:frontend-test .
```

这个目标只是测试镜像，正式运行应构建默认 runtime 目标。容器里的 Python 使用 `/usr/local/bin/python`，与宿主机解释器分开。

显式容器验收脚本为 scripts/container_acceptance.py，需要特定验收标签、标记文件及 test-results/docker/runtime-* 目录，拒绝操作普通应用容器和正式数据。它验证网页、HTTP 工作流、ZIP、重启重建和跨平台恢复。Windows 脚本另由 scripts/docker_script_checks.py 验证。详见 DOCKER_DEVELOPMENT_RECORD.md 及 test-results/docker/ 日志。

若需要离线交付镜像：

```text
docker save --output outfit-studio-docker-v1.tar outfit-studio:docker-v1
docker load --input outfit-studio-docker-v1.tar
```

镜像不包含项目数据或 Key。需要展示已有项目时，另附 ZIP 数据备份；接收者自行配置 Key，再进行启动和恢复。当前镜像验证平台为 Linux amd64，其他架构需要重新构建和验收。不要把大型镜像 TAR 或真实 .env.docker 推到 Git。

## 8. 常见问题

| 现象 | 检查方法 |
|---|---|
| docker 命令无法识别 | 重新打开终端，或使用 Docker Desktop 中 docker.exe 的绝对路径；Windows脚本支持自动查找 |
| 无法连接引擎 | 打开 Docker Desktop，确认 version 同时显示 Client / Server，info 显示 linux |
| 启动失败 | 查看脚本错误和 docker logs，检查端口、同名容器与目录权限 |
| 页面可以打开但无法上传 | 检查 /api 请求地址、HTTP 错误、挂载目录权限；前端应使用同源 /api |
| 直接刷新详情页面 404 | 确认运行的是包含本次前端路由托管适配的镜像 |
| 历史视频没有了 | 检查是否挂载原数据目录，以及数据库对应的 projects/ 文件是否完整 |
| Agnes 认证失败 | 检查运行配置文件是否填写 Key、有无外层引号，以及修改后是否重新创建容器 |
| 生成失败或超时 | 查看工作流日志，区分 Agnes 网络/额度、媒体下载和本地 FFmpeg 错误 |
