# 上传失败修复记录（2026-10-03）

## 诊断依据

- 当前聊天没有关联到应用终端，终端读取工具返回 `No app terminal session is attached to this thread yet.`，因此未读取到用户运行服务的历史终端输出。
- 对运行中的 `127.0.0.1:8000` 进行了只读查询：健康检查正常，`/api/system/info` 返回数据目录为相对路径 `data`。
- “测试4”项目 ID 为 `b4524dc6-1ef9-4d06-b407-00585c913657`，接口返回素材数为 0；其磁盘 assets 目录已有一张 2,577,652 字节的 PNG。这说明文件写入与数据库记录保存之间发生了失败。
- 使用相同的相对目录配置、独立临时数据库及有效图片运行新增回归测试，上传在 `backend/app/api/routes.py` 的 `stored_path.relative_to(settings.data_dir)` 处失败，抛出 `ValueError: ... is not in the subpath of 'data'`。原始异常见 `test-results/upload-fix/backend-before.log`（2 failed）。

## 失败原因

上传代码将项目目录解析成绝对路径，但设置中的数据根目录仍为相对路径。图片文件已经写入磁盘，随后计算用于数据库保存的相对路径时，两个路径的格式不一致，导致异常和 HTTP 500；数据库事务未提交，因此页面没有已保存素材。前端又没有读取该 500 响应顶层的 `error.message`，只显示笼统的“上传失败”。

## 修改范围

- `backend/app/config.py`：新增设置初始化逻辑，将数据目录统一解析为绝对路径。数据库内的素材路径继续保持相对路径，以支持迁移和备份。设置创建后改变工作目录也不会改变数据保存位置。
- `frontend/src/api/client.ts`：兼容顶层错误、嵌套错误及参数校验错误，非 JSON 的错误响应显示 HTTP 状态码。
- 新增后端相对目录回归测试和前端上传响应测试；未删除已有测试，未更改主工作流、模型调用、API Key、现存项目或素材。
- 原失败留下的磁盘图片保持原样，没有自动删除或将其强行导入数据库。重新上传会生成正常的素材记录。

## 测试结果

全部测试使用 `D:\anaconda\envs\interview-agent\python.exe` 执行 Python 命令；前端使用项目的 npm 脚本。

| 检查 | 实际结果 | 原始日志 |
| --- | --- | --- |
| 后端修复前回归复现 | 2 failed，上传路径异常已复现 | `test-results/upload-fix/backend-before.log` |
| 后端专项：路径、上传、持久化 | 7 passed | `test-results/upload-fix/backend-stage.log` |
| 前端上传表单及错误响应 | 5 passed | `test-results/upload-fix/frontend-stage.log` |
| 完整后端 `-m pytest` | 50 passed，0 failed，0 skipped | `test-results/upload-fix/backend-full.log` |
| 完整前端 | 3 个文件、17 passed，0 failed，0 skipped | `test-results/upload-fix/frontend-full.log` |
| TypeScript 检查及 Vite 构建 | 成功 | `test-results/upload-fix/frontend-build.log` |
| 新构建文件托管、健康检查 | 2 passed | `test-results/upload-fix/serving-smoke.log` |
| 当前运行服务的首页及新脚本只读检查 | 均返回 HTTP 200 | `test-results/upload-fix/live-static-check.log` |

端到端后端回归覆盖：相对数据目录、上传 1 张模特图及 3 张服装图、保存后变为 ready、应用重建后读取 4 个素材及其图片、继续生成演示视频、输出视频可下载。

前端原有 Ant Design 弃用提示、jsdom 伪元素样式能力提示，以及构建文件大小提示仍存在；本次完整测试没有失败或跳过。

## 使用方式

当前已启动的后端仍持有旧设置，需要先在其运行终端按 Ctrl+C，随后从项目根目录执行 `./start.ps1`。浏览器强制刷新后重新选择图片并保存。未自动终止用户的外部终端进程。

测试使用独立临时数据库和图片，演示视频验证使用 mock provider，没有调用真实 Agnes 生成接口或消耗生成额度。
