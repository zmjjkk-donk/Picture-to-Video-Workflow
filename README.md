# 电商服装 AI 换装短视频工作流

这是一个本地可运行的 AI 换装短视频工作台，用于完成电商服装换装视频笔试题。项目采用 React + TypeScript + Vite + Ant Design 前端，Python + FastAPI + LangGraph 后端，SQLite 和本地文件系统保存数据。

## 当前能力

- 创建和管理换装项目；
- 上传一张模特图和三张服装图；
- 编辑商品名称，保存服装顺序；
- 使用 LangGraph 执行素材校验、提示词准备、Provider 提交、状态轮询和输出保存；
- Mock Provider 本地生成可播放的竖屏 MP4 演示视频；
- 查看任务进度、工作流日志、视频封面和视频输出；
- 查询历史任务、重试失败任务；
- 将数据库、项目清单、图片和视频导出为 ZIP；
- 校验 SHA256 并导入恢复 ZIP；
- Provider 接口可替换，支持 Mock Provider 和 Agnes 双模型工作流。

默认使用 Mock Provider，不会调用真实 AI 服务。配置 Agnes API Key 后，可执行“3 次图生图 + 2 次首尾帧图生视频 + 本地合成”的真实流程。

## 技术栈

- 前端源码：React、TypeScript、Vite、Ant Design、TanStack Query、React Router；
- 后端：Python 3.12、FastAPI、Uvicorn、Pydantic；
- Agent 工作流：LangGraph + SQLite Checkpoint；
- 数据：SQLAlchemy、SQLite；
- 媒体：Pillow、ImageIO、imageio-ffmpeg；
- 测试：pytest、pytest-asyncio、Vitest、Testing Library。

## 环境要求

- Windows；
- Python 环境：`D:\anaconda\envs\interview-agent\python.exe`；
- Node.js 24+ 和 npm 11+（仅在需要重新构建 React 前端时需要）。

## 启动方式

### 方式一：直接启动本地完整应用

项目已经提供无需 npm 的 `frontend/dist` 演示构建。它由 FastAPI 直接托管，适合在当前没有前端依赖时运行：

```powershell
Set-Location "D:\VibeCoding Project Record\2.Interview_TestQuestion_Project"
& "D:\anaconda\envs\interview-agent\python.exe" -m pip install -r requirements.txt
& "D:\anaconda\envs\interview-agent\python.exe" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

也可以双击 `start.bat`，或在 PowerShell 中运行 `./start.ps1`。

打开：

- 工作台：http://127.0.0.1:8000/
- API 文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/health

### 方式二：开发 React 前端

当 npm 可以访问 registry 时：

```powershell
Set-Location frontend
npm install
npm run dev
```

另开一个终端运行后端：

```powershell
Set-Location "D:\VibeCoding Project Record\2.Interview_TestQuestion_Project"
& "D:\anaconda\envs\interview-agent\python.exe" -m uvicorn backend.app.main:app --reload --port 8000
```

前端开发地址：http://localhost:5173

构建 React 前端：

```powershell
Set-Location frontend
npm run build
```

构建产物会替换 `frontend/dist`，FastAPI 生产模式会自动托管该目录。

## 本地数据结构

```text
data/
├── app.db
├── workflow_checkpoints.db
├── projects/
│   └── {project_id}/
│       ├── project.json
│       ├── assets/
│       └── outputs/
└── backups/
```

SQLite 保存业务数据，图片、视频和封面保存为独立文件。数据库只记录文件路径、大小和 SHA256。

## 备份和恢复

在“备份与恢复”页面点击“创建完整备份”，系统会生成 ZIP，包含：

- `app.db`；
- `workflow_checkpoints.db`；
- `manifest.json`；
- 项目 `project.json`；
- 模特图、服装图；
- 生成的视频和封面。

恢复时会校验 ZIP 路径、文件数量和 SHA256，然后使用显式 `replace` 模式恢复数据库和项目文件。恢复前请关闭正在运行的生成任务。

## Agnes 真实模型接入

第二版已接入 Agnes 的 OpenAI 兼容接口：`Agnes Image 2.0 Flash` 负责生成三张换装图，`Agnes Video 2.5 Flash` 负责生成两段首尾帧过渡视频，最后由本地 FFmpeg 合成为约 5 秒的竖屏视频。新任务只允许 `mock` 和 `agnes` 两种 Provider，旧 SiliconFlow 文件仅作为历史记录保留，不再被工作流引用。

复制 `.env.example` 为项目根目录 `.env`，填入：

```text
AGNES_API_KEY=在此填入你的 Agnes API Key
```

其余 Agnes 地址、模型、轮询和输出尺寸配置也可以在 `.env` 中覆盖。Key 只从环境变量读取，不写入 SQLite 和前端接口；没有填入真实 Key 时，Agnes 任务会明确返回 `KEY_NOT_CONFIGURED`，本地 Mock 仍可完整演示。

## 测试

后端测试必须使用指定 Python 解释器：

```powershell
& "D:\anaconda\envs\interview-agent\python.exe" -m pytest
```

当前后端测试覆盖：

- SQLite 初始化、关系和级联删除；
- 项目和素材 API；
- 上传校验、顺序调整和文件读取；
- LangGraph Mock 工作流和 MP4 输出；
- Provider 失败状态；
- 首页统计、任务取消、重试、设置；
- ZIP 导出、导入、SHA256 校验和恢复；
- FastAPI 静态前端托管和健康检查。

React 源码测试：

```powershell
Set-Location frontend
npm test
```

当前机器 npm registry 访问受限时，可以先使用已提供的 `frontend/dist` 本地演示构建；React 测试在依赖安装成功后执行。

## 项目范围说明

项目当前支持本地 Mock 演示和 Agnes 真实双模型工作流，不包含多用户权限、云端对象存储、Redis/Celery 和在线部署。生成任务、三张换装图、两段过渡视频、最终视频、封面和 LangGraph 检查点都会落盘到 `data/`，可通过工作台导出 ZIP 并恢复。
