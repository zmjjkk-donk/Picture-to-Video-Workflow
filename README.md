# 电商服装 AI 换装短视频工作流

这是一个本地可运行的电商服装换装短视频工作台。使用者可以创建项目、上传模特图和三套服装图，并通过 Mock 演示模型或 Agnes 双模型工作流生成竖屏换装视频。

## 启动方式

以下步骤以 Windows PowerShell 为例。请先把本文中的 `<PROJECT_ROOT>` 替换为你下载后的项目根目录，把 `<PYTHON_EXE>` 替换为你实际使用的 Python 解释器路径。Python 版本建议为 3.12 或更高版本，Node.js 建议为 20 或更高版本。

### 1. 获取项目并进入根目录

```powershell
Set-Location "<PROJECT_ROOT>"
```

### 2. 安装后端依赖

```powershell
& "<PYTHON_EXE>" -m pip install -r requirements.txt
```

如果你使用虚拟环境，请将 `<PYTHON_EXE>` 替换为该虚拟环境中的 Python 路径。后续运行测试、FastAPI 和 Uvicorn 时，也要继续使用同一个解释器。

### 3. 配置 Agnes（可选）

项目默认使用 Mock Provider，不需要 API Key 就可以运行本地演示。需要调用真实模型时，在项目根目录复制 `.env.example` 为 `.env`，填写：

```text
AGNES_API_KEY=<YOUR_AGNES_API_KEY>
```

不要把真实 API Key 提交到 Git。没有配置 Key 时，可以在工作台设置中选择演示 Provider；配置完成后选择 Agnes Provider。

### 4. 启动后端和内置前端

```powershell
Set-Location "<PROJECT_ROOT>"
& "<PYTHON_EXE>" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

启动后打开：

- 工作台：http://127.0.0.1:8000/
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

项目已经包含前端构建产物，直接启动后端即可访问完整工作台。也可以使用项目提供的 `start.bat` 或 `start.ps1`，但首次使用前请检查其中的解释器配置。

### 5. 使用 React 开发服务器（可选）

需要修改前端源码时，在另一个终端执行：

```powershell
Set-Location "<PROJECT_ROOT>\frontend"
npm install
npm run dev
```

开发地址通常为 http://127.0.0.1:5173。当前前端默认直接请求 `http://127.0.0.1:8000/api`，Vite 没有配置代理，因此仍需在另一个终端启动 Uvicorn。可在构建时通过 `VITE_API_BASE` 设置 API 地址；Docker 方案使用同源 `/api`。

修改完成后构建前端：

```powershell
Set-Location "<PROJECT_ROOT>\frontend"
npm run build
```

构建产物会写入 `frontend/dist`，之后再次通过后端启动即可访问更新后的页面。

### 6. 首次使用流程

1. 打开工作台并创建换装项目。
2. 上传一张模特图和三张服装图。
3. 点击“保存上传素材”。
4. 在设置中选择 Mock Provider 或 Agnes Provider。
5. 点击“生成换装视频”。
6. 在任务详情中查看工作流进度、中间产物、日志和最终视频。
7. 任务失败时可以查看错误信息，并使用“恢复任务”继续执行。

## 技术选型

- 前端：React、TypeScript、Vite、Ant Design、TanStack Query、React Router；
- 后端：Python、FastAPI、Uvicorn、Pydantic；
- Agent 工作流：LangGraph 和 SQLite Checkpoint；
- 数据库：SQLAlchemy + SQLite；
- 文件存储：本地文件系统；
- 图像生成：Agnes Image 2.0 Flash；
- 视频生成：Agnes Video 2.5 Flash；
- 媒体处理：Pillow、ImageIO、imageio-ffmpeg；
- 测试：pytest、pytest-asyncio、Vitest、Testing Library。

## 已完成功能

- 创建、查看、更新和删除换装项目；
- 上传一张模特图和三张服装图；
- 编辑服装名称并调整三套服装顺序；
- 使用 LangGraph 执行素材校验、提示词准备、模型调用、状态轮询和输出保存；
- Mock Provider 本地生成可播放的竖屏 MP4 演示视频；
- Agnes Image 2.0 Flash 生成三张换装图；
- Agnes Video 2.5 Flash 生成两段首尾帧过渡视频；
- 本地合成约 5 秒竖屏最终视频和封面；
- 查看任务进度、当前节点、工作流日志和中间产物；
- 取消、恢复和重试生成任务；
- 按项目展示 Agnes 接口实际返回的 token 用量；
- 对失败后恢复并最终成功的任务按步骤幂等累计 token；
- Agnes 未返回 usage 时显示“接口未提供用量数据”，不估算用量；
- 将数据库、检查点、项目清单、图片和视频导出为 ZIP；
- 校验 SHA256 并导入恢复 ZIP 备份；
- 通过 FastAPI 托管内置前端并提供 API 文档。

## 项目和生成任务的删除规则（第四版）

- 工作台最近项目、换装项目列表和素材库项目卡片均提供独立的“删除”按钮。
- 删除项目后，上述三个页面同步移除该项目；生成记录、日志、中间产物和历史视频继续保留。
- 项目删除采用数据库中的独立删除标记，必要的项目关联和文件仍保存在磁盘上，以便查看历史视频。页面移除项目并不等于释放全部文件占用。
- 生成队列、生成记录和任务详情均可单独删除成功、失败或已取消的任务。删除任务会清理其日志、Token 用量、检查点、中间产物和输出目录，不影响所属项目或其他任务。
- 正在执行的任务需先在任务详情取消。取消后若后台模型调用尚未结束，请稍后再删除或恢复；项目存在未结束的任务时也不能删除。
- 所属项目已删除的任务会显示“所属项目已删除”。其历史视频和日志仍可查看，恢复或新建生成不再可用，任务可继续单独删除。
- 所有删除操作均先确认影响范围。成功后自动刷新相关列表、统计和项目 Token 汇总。
- 删除标记包含在数据库备份中，重启或恢复该备份后保持生效。恢复删除前的备份会恢复当时的项目状态。

## 本地数据和备份

运行后，数据默认保存在项目根目录的 `data/`：

```text
data/
├── app.db
├── workflow_checkpoints.db
├── projects/
│   └── <project_id>/
│       ├── project.json
│       ├── assets/
│       └── outputs/
└── backups/
```

SQLite 保存业务记录，图片、视频和封面保存为独立文件。工作台的“备份与恢复”页面可以创建完整 ZIP，内容包括数据库、LangGraph 检查点、项目清单、素材、视频、封面和 `manifest.json`。恢复前请关闭正在运行的生成任务。

## Agnes 接入说明

Agnes 接口采用 OpenAI 兼容方式。图像模型负责三张换装图，视频模型负责两段首尾帧视频，最后由本地媒体处理流程合成最终视频。Agnes 的 token 用量只在接口响应提供 `usage` 或 `token_usage` 时记录，接口没有提供时保留为未知状态。

真实 Key 只从环境变量读取，不写入 SQLite，也不会通过前端接口返回。旧 SiliconFlow 文件仅作为历史记录保留，当前工作流不再引用。

## 测试

运行后端测试：

```powershell
Set-Location "<PROJECT_ROOT>"
& "<PYTHON_EXE>" -m pytest
```

运行前端测试：

```powershell
Set-Location "<PROJECT_ROOT>\frontend"
npm test -- --run
```

测试覆盖数据库初始化、项目和素材 API、上传校验、Mock 工作流、Agnes Provider、任务恢复、备份恢复、token 用量解析与累计、项目接口返回值、前端工作台渲染和静态前端托管。

## 当前范围和限制

项目面向本地笔试演示和单机使用，不包含多用户权限、云端对象存储、Redis/Celery 和在线部署。真实视频生成依赖 Agnes API Key、接口额度、网络和 Agnes 返回的可访问媒体地址。项目数据可以通过 ZIP 备份迁移到另一台电脑。

## Docker 单容器部署

已有 Docker Linux 引擎的用户可以使用单容器运行完整工作台，不需要在宿主机安装 Python、Node.js 或 FFmpeg。前端在构建时编译，数据库及媒体挂载到独立目录；镜像不包含开发者的项目数据或真实 API Key。

Windows PowerShell 7 首次启动：

```powershell
Set-Location "<PROJECT_ROOT>"
if (-not (Test-Path -LiteralPath '.env.docker')) {
    Copy-Item -LiteralPath '.env.docker.example' -Destination '.env.docker'
}
& '.\scripts\docker-build.ps1'
& '.\scripts\docker-run.ps1'
```

留空 Key 可用 Mock 演示。需要真实生成时自行填写 `.env.docker`，不要给值加引号；复制示例只需首次执行。默认访问 http://127.0.0.1:8000/，数据保存在 `docker-data/`。端口占用时可传入 `-Port 18000`，自定义数据目录可传入 `-DataDir '<HOST_DATA_DIR>'`。

Linux 命令、数据迁移、备份恢复、运行管理和网络排错见 [Docker 部署说明](DOCKER_DEPLOYMENT.md)，实际测试结果见 [Docker 开发验收记录](DOCKER_DEVELOPMENT_RECORD.md)。
