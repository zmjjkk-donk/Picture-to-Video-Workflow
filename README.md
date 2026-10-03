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

开发地址通常为 http://127.0.0.1:5173。开发服务器会把 `/api` 请求转发到本地后端，因此仍需在另一个终端启动 Uvicorn。

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
