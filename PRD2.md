# PRD2：Agnes 双模型电商换装视频工作流

## 1. 文档状态与依据

- 版本：v2.0 设计待确认；日期：2026-09-30。
- 项目根目录：`D:\VibeCoding Project Record\2.Interview_TestQuestion_Project`。
- 本轮仅创建此设计文档。须收到用户后续开发指令才实施，不修改现有代码、数据库、素材或运行配置。
- 第一优先依据：用户指定的 `agnes_use_method/picture-to-vedio.txt`，严格采用三张换装图、两段首尾帧过渡视频、本地合成的路线。
- API 依据：同目录 `agnes_picture_model.md`、`agnes_vedio_model.md`、`agnes_quick_use.md`、`agnes_overview.md`。使用本地文档快照，不将其中的营销描述视为效果保证。
- 继承 `PRD.md` 的本地运行、电商工作台、LangGraph、媒体落盘、备份恢复和原题画面质量要求。本文件覆盖其 SiliconFlow 接入计划及单视频生成流程；不改变其余未冲突要求。
- 用户指定模型：Agnes Image 2.0 Flash、Agnes Video 2.5 Flash。不再采用硅基流动，不额外引入聊天模型。
- 随附文档描述两模型当前免费，其中视频为限时免费；该描述不是永久免费承诺，真实运行前以账号实际可用性和供应商最新规则为准。

## 2. 已有实现与中断位置

用户已实际完成上传模特图、三张服装图和 Mock 视频流程。继续使用已有项目，不重新搭建。

当前技术栈为 React、TypeScript、Vite、Ant Design、TanStack Query；后端为 FastAPI、SQLAlchemy、SQLite；LangGraph 使用本地 SQLite checkpoint；媒体通过本地文件和 ZIP 管理。

上次中断已写入部分 SiliconFlow 配置、Provider 请求逻辑，以及 runner 的图片路径传递和轮询配置。它不是已验收的真实生成实现：前端仍默认提交 mock，Provider 状态接口仍为旧逻辑，也没有三图两视频的编排。本次不回退或覆盖这些文件，开发时有针对性地替换，保留已有素材、历史任务及有效测试。

上一轮已报告后端 12 项、前端 1 项和静态检查通过；这些是历史结果，不代表中断后的代码或 V2 已通过测试。V2 开始时必须重新建立基线。

## 3. V2 目标和范围

输入：一张已授权全身模特图、三张服装商品图、三个商品名称和确定的展示顺序。

输出：三张模特换装图、两段原始过渡视频、一条约 5 秒的 9:16 成片，以及封面和执行记录。所有媒体必须保存到本机，断网后仍可查看已下载结果。

必须完成：

1. Agnes 图像多图编辑接口和视频首尾帧接口。
2. Mock 与 Agnes 模式可选择，实际提交模式与界面一致。
3. 分步进度、中间产物预览、错误说明、恢复和重试。
4. 本地视频标准化、拼接、调速、封面和媒体完整性检查。
5. 旧数据迁移及 V2 中间产物的备份恢复。
6. 本地配置占位符、启动说明、分阶段测试与最后完整测试。

暂不做：在线部署、多用户、分布式任务系统、第三个模型、音频参考、参考视频、配乐、自动购买额度、自动切换其他或付费模型。在线演示地址仍是最终交付诉求，部署方案另行处理。

## 4. 固定业务流程

```text
模特原图 + 服装1 → Agnes Image → 换装图1
模特原图 + 服装2 → Agnes Image → 换装图2
模特原图 + 服装3 → Agnes Image → 换装图3
换装图1 + 换装图2 → Agnes Video keyframe → 视频段1
换装图2 + 换装图3 → Agnes Video keyframe → 视频段2
视频段1 + 视频段2 → 本地标准化、拼接、调速 → 约5秒竖屏视频
```

三次换装均使用同一张原始模特图，不以上一张生成图继续换装，减少身份累计漂移。换装图2必须是两个视频任务共用的同一份结果。默认串行执行三次生图和两次视频任务，便于追踪和限流；无需增加并发框架。

换装提示词明确第一张输入是人物、第二张是商品；只替换衣服，保持脸部、发型、姿态、身材、镜头、背景和光线；准确保留商品颜色、版型、纹理、图案、标识及关键设计，不额外加饰品。商品名称只作为数据，不作为控制指令。

视频提示词明确从首帧服装自然转换至尾帧服装，固定镜头，限制大动作和遮挡，保持身份与环境，不添加额外人物和衣服。提示词使用本地模板，不调用额外文本模型。

### 4.1 时长和合成决策

随附视频文档规定 `seconds` 为字符串 `"4"`–`"12"`，不能向服务端提交 2.5 秒。V2 默认两段各请求 `"4"`，完整保留 A→B 和 B→C 过程，再以实际解码时长为依据统一调速至 5 秒。

例如实际共 8 秒，则播放速度约为 1.6 倍。不得直接截取前 5 秒而丢失第三套服装。默认不加交叉溶解，避免重影与衣服混合；默认去掉音轨。标准输出为 MP4、H.264、yuv420p、720×1280、30 fps、faststart，时长验收 4.8–5.2 秒。

优先使用现有 imageio-ffmpeg 提供的 FFmpeg，启动时检查可用性；通过参数数组调用，不拼接 shell 字符串。不同尺寸视频等比缩放并补边，不拉伸身体、不默认裁掉头脚。保留两段原视频供检查。封面默认使用第一张换装图。

## 5. Agnes API 合同

继续使用已有 `httpx`，无需为了 OpenAI 风格接口增加 OpenAI SDK。使用明确的 JSON 请求保留 Agnes 文档要求的嵌套字段，避免 SDK 将 `extra_body` 展开到顶层。兼容认证和风格不等于所有路径、参数和返回值相同。

### 5.1 图片生成

- POST `https://apihub.agnes-ai.com/v1/images/generations`。
- 认证：`Authorization: Bearer <AGNES_API_KEY>`；JSON 内容类型。
- 模型：`agnes-image-2.0-flash`。
- 每次只传模特与当前服装两张图，使用本地图片编码的 Data URI。
- `extra_body.image` 是数组；`extra_body.response_format` 为 `url`；不使用顶层 `response_format`、顶层 `image` 或 `tags`。
- 文档参数表与说明位置不完全一致，以明确警告、图生图示例和检查清单中的嵌套结构为准，并编写请求合同测试。

```json
{
  "model": "agnes-image-2.0-flash",
  "prompt": "第一张是模特，第二张是服装商品。将指定服装穿到模特身上……",
  "size": "768x1024",
  "extra_body": {
    "image": ["data:image/png;base64,MODEL_DATA", "data:image/png;base64,CLOTHING_DATA"],
    "response_format": "url"
  }
}
```

设计默认采用随附文档列出的竖向尺寸 `768x1024`；这不是 9:16，不把未证实支持的 `720x1280` 当作生图参数。提示词要求全身及安全边距，视频阶段明确设 9:16，最后本地统一画幅。若真实联调证实生图支持 9:16，可修改配置并记录，不改用其他模型。

优先解析 `data[0].url`，立即下载并验证图片，同时保存用于下一步的供应商 URL。若只返回 `b64_json`，保存本地图片，但不能直接将 Base64 当作视频首尾帧 URL。

### 5.2 首尾帧视频

创建：POST `https://apihub.agnes-ai.com/v1/videos`。

```json
{
  "model": "agnes-video-2.5-flash",
  "prompt": "保持同一模特、背景与光线，从首帧服装自然转换到尾帧服装……",
  "mode": "keyframe",
  "seconds": "4",
  "size": "720P",
  "aspect_ratio": "9:16",
  "n": 1,
  "first_frame": "https://供应商返回的换装图1地址",
  "last_frame": "https://供应商返回的换装图2地址"
}
```

第二段依次使用换装图2和3。不传 `images`、`audios`、`videos`，不以 reference/text 模式替代 TXT 要求的 keyframe。

创建后保存 `video_id`，并分别保存返回的 `id`、`task_id`（如有），不假设它们可互换。

轮询：GET `https://apihub.agnes-ai.com/agnesapi`，查询参数为 `video_id` 和 `model_name=agnes-video-2.5-flash`。此接口不在 `/v1` 下，单独配置查询 URL，不能构造为 `/v1/agnesapi`。

默认每 2 秒轮询，以顶层 `status`、`progress` 为准，忽略 `internal_status/internal_progress`。`completed` 后解析顶层 `url`、立即下载本地并检查可解码性；`failed` 记录脱敏错误。其他未明确状态仅在受限期限内等待，记录诊断，不误判成功。

### 5.3 公网媒体地址与本地保存

视频首尾帧要求 Agnes 可公开访问的 URL。`D:\...`、localhost、127.0.0.1 和本地 `/api/...` 地址均不能直接提交。生图接口支持 Data URI，不代表视频接口支持。

默认直接复用 Agnes 生图 URL，不引入对象存储或公网部署；每张图片同时下载到本地。供应商 URL 供生成使用，本地文件供预览、交付和备份使用。

若 URL 已过期或接口仅返回 Base64，则进入明确的“首尾帧 URL 不可用”状态。可以显式重新生成受影响换装图并使其下游视频失效；不能偷偷上传到第三方、假定存在供应商上传接口或假装恢复后 URL 永久有效。

## 6. 配置与密钥占位符

以下是下一轮开发要落地的位置，本轮不创建或修改这些配置。

- 项目根目录 `.env.example`：公开模板，始终只含占位符。
- 项目根目录 `.env`：用户实际填写位置；如已有文件须保留并按需补充，绝不覆盖已有密钥。
- `backend/app/config.py`：只从环境或根目录 `.env` 读取；环境变量优先；秘密字段不出现在 repr、日志、API 响应、SQLite 或 checkpoint。
- 两个模型默认共用 `AGNES_API_KEY`，不在前端、Python 源码或数据库内硬编码真实密钥。

```dotenv
AGNES_API_KEY=YOUR_AGNES_API_KEY_HERE
AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
AGNES_VIDEO_STATUS_URL=https://apihub.agnes-ai.com/agnesapi
AGNES_IMAGE_MODEL=agnes-image-2.0-flash
AGNES_VIDEO_MODEL=agnes-video-2.5-flash
AGNES_IMAGE_SIZE=768x1024
AGNES_VIDEO_SIZE=720P
AGNES_VIDEO_ASPECT_RATIO=9:16
AGNES_SEGMENT_SECONDS=4
AGNES_IMAGE_TIMEOUT_SECONDS=360
AGNES_POLL_INTERVAL_SECONDS=2
AGNES_VIDEO_TIMEOUT_SECONDS=1200
```

空值及占位值视为未配置，在提交任务前提示。通过显式 dotenv 加载或启动脚本 `--env-file` 实现读取，不声称仅创建 `.env` 就能被现有代码自动识别。固定两个模型 ID，禁止失败时自动换模型。

供应商状态区分“配置存在”和“真实调用已验证”，填入 Key 不等于认证成功。开发完成后在交付说明中再次给出 `.env` 绝对路径和具体字段。

## 7. 后端与 LangGraph 改造

保留 FastAPI、SQLAlchemy、LangGraph 和本地队列规模。新增 Agnes 图像/视频适配器和本地合成服务；业务层处理顺序、重试和状态，Provider 处理 Agnes 请求及响应映射。

```text
validate_config_and_assets
 → snapshot_inputs_and_prepare_prompts
 → generate_outfit_1 → generate_outfit_2 → generate_outfit_3
 → submit_transition_1 → poll_transition_1 → download_transition_1
 → submit_transition_2 → poll_transition_2 → download_transition_2
 → compose_video → validate_output → save_output → finish
```

任务创建时冻结素材 ID、文件校验值、商品名称、顺序、提示词模板版本、模型及参数。按 `clothing_order` 执行，严格校验三项互不重复且属于当前项目。任务期间替换素材不得改变正在运行任务，输入文件采用任务快照或引用保护。

持久化每个子任务结果，不把三张图与两段视频塞入单一 `provider_job_id`。checkpoint 不存二进制、Base64 或密钥。父任务仅在最终文件验证完成后 succeeded，供应商完成不等于全流程完成。

失败恢复：已保存图像和视频通过哈希确认后复用；已有 video_id 的任务优先继续查询/下载。修改某张换装图时，只失效依赖它的过渡段和最终输出。生成 POST 超时可能已被供应商接收，记录“提交结果未知”，不自动重复提交；查询和下载可以有限重试。401/403和参数错误直接提示，429/临时5xx采用退避与总期限。

本地取消阻止后续步骤和成功状态回写。文档未提供远端取消接口，不承诺停止供应商已提交任务。重启后将未完成任务呈现为可恢复状态，用户显式恢复，禁止因为打开页面重复提交。默认同一项目仅允许一项活动任务。

错误码至少包括：KEY_NOT_CONFIGURED、AGNES_AUTH_FAILED、AGNES_RATE_LIMITED、IMAGE_GENERATION_FAILED、FRAME_URL_UNAVAILABLE、VIDEO_SUBMIT_UNKNOWN、VIDEO_GENERATION_FAILED、PROVIDER_TIMEOUT、MEDIA_DOWNLOAD_FAILED、COMPOSE_FAILED、OUTPUT_INVALID。

## 8. 数据库与文件关系

保留 projects、assets、generation_jobs、workflow_runs、video_outputs、backup_records、app_settings。通过显式迁移新增字段和表，迁移前备份，不能删除旧数据库重建。

| 对象 | V2 新增或调整 |
|---|---|
| generation_jobs | workflow_version=v2、输入快照/顺序、参数快照、恢复来源任务 ID；保留旧字段供历史读取 |
| generation_steps（新增） | id、job_id、step_key、attempt、status、provider、model、video_id、task_id、进度、输入摘要、脱敏错误、起止时间；步骤和尝试号唯一 |
| generated_artifacts（新增） | id、job_id、step_id、kind、slot_index、relative_path、mime、sha256、size、width、height、duration、remote_url（可空）、created_at |
| video_outputs | 保持最终成片接口，实际测量分辨率与时长，不写默认值冒充测量 |

关系：一个 project 有多个 job；一个 job 有多个 step；step 产生 artifact；job 产生 final output。artifact 类型包括 input_snapshot、outfit_image、transition_video、cover。逻辑删除或替换不得破坏活动任务输入。

```text
data/projects/{project_id}/
  assets/                         # 保留原始素材
  jobs/{job_id}/
    input_snapshot/               # 冻结输入
    manifest.json                 # 版本、顺序、模型、参数、文件哈希
    outfits/look-01.png ... look-03.png
    segments/transition-01.mp4、transition-02.mp4
    work/                         # 可重建的临时合成文件
  outputs/{job_id}/final.mp4、cover.png
```

媒体先写临时文件，校验后原子替换再登记数据库，避免中断后半文件被当作成功。remote_url只作服务端任务数据，不依赖它提供历史预览；可能含签名的 URL 不输出到普通日志。

## 9. 页面与接口变化

保持电商工作台布局，补充以下交互：

- 系统设置：Mock/Agnes、两个固定模型名称、密钥是否配置、实际连通性验证状态和填写路径；不回显 Key。
- 创建任务：明确所选 Provider，显示三套顺序以及“3 次换装图 + 2 次过渡视频 + 本地合成”；未配置禁止提交 Agnes。
- 项目详情/任务页：三张换装图预览、两段过渡视频预览、最终视频；执行中显示当前第几张/第几段及节点耗时。
- 日志与进度在执行中持续刷新，完成/失败/取消后停止；单段100%不导致父任务100%。
- 恢复/重试说明哪些产物将复用，哪些需要重新生成；展示提交结果未知与URL过期，不自动重复发起。
- 历史 Mock、旧 SiliconFlow 记录保持可读；新任务选项只允许 mock/agnes，旧 SiliconFlow 不允许再提交或重试到该供应商。

复用现有 `/api` 响应封装和项目/素材/输出接口：

| 接口 | 修改内容 |
|---|---|
| POST `/api/projects/{project_id}/jobs` | provider=mock/agnes；冻结顺序与输入；返回业务任务 ID |
| GET `/api/jobs/{job_id}` | 增加 workflow_version、子步骤摘要、可恢复标识 |
| GET `/api/jobs/{job_id}/steps` | 新增：三张图和两段视频的状态/尝试/进度 |
| GET `/api/jobs/{job_id}/artifacts` | 新增：中间产物列表与本地预览 URL |
| GET `/api/artifacts/{artifact_id}/file` | 新增：从受控本地路径获取中间产物 |
| POST `/api/jobs/{job_id}/resume` | 新增：恢复已有外部任务与未完成步骤 |
| POST `/api/jobs/{job_id}/retry` | 保留：创建关联重试记录，复用校验通过的步骤，不无条件重新调用全部模型 |
| POST `/api/jobs/{job_id}/cancel` | 明确为本地取消，防止后台状态覆盖 |
| GET `/api/providers` | 返回 mock/agnes 及两个模型的能力与配置状态 |
| POST `/api/providers/agnes/validate` | 只做本地配置验证；没有文档依据时不编造远端认证检查接口 |
| PATCH `/api/settings` | 保存非敏感模式设置，实际任务读取一致；禁止保存 Key |

真实 API 验证使用后续用户配置后的生成任务，不在“保存设置”时隐式消耗生成次数。前端和后端均展示错误，避免无反应的按钮。

## 10. 备份、恢复与打包

V2 备份包括业务 SQLite、一致的 checkpoint、原始素材、输入快照、三张换装图、两段视频、成片、封面和 manifest。排除 work 临时文件、密钥、环境文件、node_modules。项目源码包包含 `.env.example` 而不包含真实 `.env`。

采用 SQLite 一致性快照或暂停写入，不在写库时直接复制数据库文件。恢复前校验ZIP路径、文件数、哈希、版本、数据库完整性，并在临时目录完成检查；恢复期间禁止运行生成任务，保留回滚备份。

V1 备份恢复后执行迁移，历史结果仍可播放。V2 恢复后无需网络即可预览已落盘内容；恢复活动任务需重新配置 Key，远端 URL/任务是否仍有效单独判断。不把恢复本地文件等同于恢复云端资源。

Git可管理源码版本，但不能代替数据 ZIP 备份。本轮不创建仓库，也不修改既有素材。

## 11. 分阶段开发与有效测试

所有 Python 操作仅使用 `D:\anaconda\envs\interview-agent\python.exe`。开始实施先执行并记录：

```powershell
& "D:\anaconda\envs\interview-agent\python.exe" -c "import sys; print(sys.executable); print(sys.version)"
```

依赖先读现有 requirements，不切换解释器。每阶段先实现、补测试、运行；失败定位修复并重跑，通过才进入下一阶段。保留日志，不删测试、不skip、不放宽断言规避失败。供应商变更导致旧 SiliconFlow 专属测试不再适用时，保留历史证据并替换为等价 Agnes 合同测试，不能减少对错误行为的覆盖。

| 阶段 | 开发内容 | 必须验证 |
|---|---|---|
| 0 | 清点中断修改、PRD、数据与依赖，备份并建立基线 | 现有测试真实运行；记录失败，不把旧报告当新结果 |
| 1 | 配置、占位符、数据迁移、输入快照、移除新任务 SiliconFlow 路径 | 环境优先级、占位拒绝、秘密脱敏、迁移保留旧项目及文件 |
| 2 | Agnes 图像适配器、3次多图调用、图片落盘 | 捕获真实请求形状，核验每套服装输入不同且模特相同；URL/Base64解析、坏图、超时、401/429 |
| 3 | 两个 keyframe 视频任务及轮询、下载 | 核验1→2与2→3，独立video_id、查询不带/v1、model_name、顶层状态优先；缺URL/失败/恢复不重复提交 |
| 4 | 本地合成和封面 | 用可识别测试视频实际合成并解码，检查A/B/C顺序、720×1280、30fps、4.8–5.2秒、可播放、坏片失败 |
| 5 | LangGraph整合、取消、恢复、有限重试 | 注入每阶段故障；中间成果复用、取消不回写成功、重启恢复、未知提交不自动重复 |
| 6 | 工作台模式选择和中间预览/状态/错误 | 用户选择Agnes实际提交Agnes；设置重载一致；任务页刷新和异常显示；浏览器前后端联调 |
| 7 | ZIP备份、V1兼容、README、启动脚本 | 在独立数据目录恢复并比较所有产物哈希；断网播放；无密钥进入备份或源码包 |
| 8 | 完整回归与真实样例验收 | 全量pytest、前端测试、构建、静态资源、真实双模型流程和人工画面审查 |

自动测试通过 HTTP stub/MockTransport 隔离网络；必须测试业务合同、故障和文件可用性，不只是校验函数调用次数。Mock保留离线演示能力，V2新增步骤可用本地测试素材模拟，明确标记演示，不能假装模型生成。

最终命令：

```powershell
# 项目根目录
& "D:\anaconda\envs\interview-agent\python.exe" -m pytest
# frontend目录
npm.cmd test -- --run
npm.cmd run build
# 项目根目录
node frontend/test-static.mjs
```

本轮为文档设计，不运行测试、不安装依赖、不发出任何生成请求。后续占位符状态只能完成离线及合同验收，不能声称真实生成已验证；用户填入 Key 后再完成真实联调。

## 12. 验收标准

1. 不损失已有项目、原图、历史视频和可用备份；从现有工作区升级。
2. 一个成功真实任务按正常无重试路径调用三次 `agnes-image-2.0-flash` 和两次 `agnes-video-2.5-flash`；不调用硅基流动或第三模型。
3. 三次生图的每次输入为原模特+对应商品，服装展示顺序与冻结顺序完全一致。
4. 两段首尾帧输入准确为1→2、2→3，使用keyframe、720P、9:16和合法字符串时长。
5. 三张换装图、两段视频、最终视频与封面都有独立本地文件及元数据；刷新页面和重启后仍可展示。
6. 最终成片可解码、可播放、可下载，720×1280、约5秒；不能通过截掉第三套满足时长。
7. 人工核验三套服装均清晰可识别、模特身份/发型/身材/背景/光线基本一致；颜色、版型、纹理、图案和关键设计准确；无明显闪烁、穿模、肢体异常或漂移。
8. 第7项属于真实生成质量验收，不用HTTP成功或自动单测替代；若效果不合格，记录问题并调整提示词或重生，不降低原题标准。
9. 错误、取消、超时和恢复均可观察，不重复提交已知外部任务，不假称远端取消成功。
10. ZIP恢复后完整复现本地成果，密钥不进入日志、前端、数据库、checkpoint或备份。
11. 所有阶段及全量自动测试通过；报告明确区分离线测试、真实API验证、人工质量验收。

## 13. 待确认设计决策与实施边界

本方案默认：单Key共用；三张图串行、两段视频串行；各段4秒后整体调速至5秒；优先生图URL直传首尾帧；不增加对象存储；自动流程不中途强制人工确认，但提供产物预览与失败重试。

真实联调仍需确认：账号是否能调用指定免费模型、生图实际支持的尺寸、返回URL能否被视频服务访问及有效期、模型是否能达到服装/身份质量要求。这些为验证项，不作未经证实的实现保证。

OpenAI风格兼容可复用HTTP基础设施，但本项目从单视频变为三图两视频，需要修改状态编排、数据关系、合成、前端和备份，因此按上述阶段实施而非仅替换Base URL。

本文件提交用户检查。用户下达第二版开发指令后，才修改代码、创建密钥模板和运行测试。
