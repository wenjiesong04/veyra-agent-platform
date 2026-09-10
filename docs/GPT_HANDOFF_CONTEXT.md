# Veyra Agent Platform — GPT 交接上下文

> 更新时间：2026-09-10
> 本文是给继续接手 Veyra Agent Platform 的 GPT/Agent 的工作上下文。它不是新的产品需求；如果它与用户的新消息冲突，以用户新消息和 `docs/PROJECT_DESIGN.md` 为准。

## 0. 交接指令

你现在接手的是 Veyra Agent Platform 的架构、产品和实现协作。开始任何修改前：

1. 读取仓库根目录 `AGENTS.md` 和 `docs/PROJECT_DESIGN.md`。
2. 检查当前分支、HEAD、工作区状态、运行中的服务和 Python 导入路径。
3. 以真实代码、真实 API 响应、测试结果和精确 Git SHA 分开判断进度；不要把计划、静态页面、测试通过或 CI 通过单独当成产品交付。
4. 保留用户提供的 `.env`，绝不读取、打印、提交或复制其中的密钥。
5. 只做当前目标所需的窄改动；不要为了“完整”新增大量契约、抽象层或重复测试。
6. 每个实现任务结束时报告：文件范围、测试命令与结果、服务端口、精确 SHA、仍未实现的边界。

## 1. 当前权威仓库和环境

- 权威代码目录：`/Users/spectre/PycharmProjects/veyra-agent-platform`
- GitHub：`https://github.com/wenjiesong04/veyra-agent-platform.git`
- 当前分支：`codex/agent-platform`
- 最新功能代码基线：`8019f41cf4ab8782dd892837ba83d622a7523ee7`；后端 live 基线为 `a65386be506f3c70f0af799decf55134db8c5de1`，已接入 Host Keychain 凭据、MCP 环境绑定、模型凭据解析、Tool 参数映射和 Agent conversation。
- 当前远端分支在推送本提交后应与本地一致。
- Draft PR：仓库中的 `codex/agent-platform → main` Draft PR。
- 专用 Conda 环境：`veyra-agent-platform`
- Python：3.11.15，解释器通常是 `/opt/anaconda3/envs/veyra-agent-platform/bin/python`
- Web：React 19、TypeScript 5.9、Vite 7、npm workspace。
- `.env`：仓库根目录的 gitignored 用户配置；本地 sidecar 在开发启动时可加载它。它不属于项目源文件，也不应进入 SQLite、浏览器存储、日志、Agent source、包或 Git。

### 当前可见服务

这些服务在最后一次验证时都应使用同一个功能提交（node.yaml Catalog）；重启无 `--reload` 的 8771 sidecar 后才会载入本提交：

- Desktop Vite：`http://127.0.0.1:5173/`，唯一的日常主要界面。
- Local API：`http://127.0.0.1:8771/`，本机 Project、Factory、Studio 和 Runtime sidecar。
- Community API：`http://127.0.0.1:8772/`，独立账号/公开社区服务。
- `5174` 只保留给后续公开展示、技术文档、下载和分享站，不是日常操作入口。

最后一次 live 检查：

- Local `/api/v1/health`：`build_sha=a65386be506f3c70f0af799decf55134db8c5de1`、`database_revision=local_0015_agent_conversations`、`database_ready=true`。
- Community `/api/v1/health`：`database_revision=community_0003_account_avatars`，`database_ready=true`。
- Local `/api/v1/factory/status` 和 `/api/v1/runtime/status` 能看到 Kimi K3 配置状态，但不会返回密钥。

注意：Conda 环境的 editable package 曾经指向旧的原项目目录，不能只看 worktree 名称判断服务代码。继续工作时应运行：

```sh
/opt/anaconda3/envs/veyra-agent-platform/bin/python -c 'import veyra_agent_platform; print(veyra_agent_platform.__file__)'
```

## 2. 产品定位和最终边界

Veyra 是一个 local-first Agent 平台：用户拥有真实 Project 目录和 Agent 源文件，能够生成、检查、编辑、运行、验证、版本化，并最终把可靠版本发布到社区。

V1 的目标闭环：

1. 邮箱验证码注册、密码登录、忘记密码、会话管理、昵称和头像。
2. 创建或打开真实 Project；一个 Project 下可以有多个 Agent。
3. Factory 通过对话收集需求，从平台 Resource Catalog 组装 AgentBlueprint Draft。
4. 用户在 Studio 的 Form、Canvas、Source 视图继续编辑。
5. 保存 mutable Draft，提交 immutable Agent version。
6. 在本机 Runtime 运行 Agent，显示节点、工具、审批、Checkpoint、验证和证据。
7. 将可靠版本发布到真实联网 Community。
8. 其他用户浏览、下载、Fork、导入自己的 Project、运行、Star、Review、Report。

V1 不做云端执行用户 Agent。Community 服务只负责账号、目录、发布、审核、下载和作者归属；本地 Desktop 负责 Factory、Studio、文件、Runtime、Orchestrator 和完整控制。

## 3. 用户已经明确的产品决定

### 3.1 Desktop 与 Community 合并界面、后端保持独立

- 用户日常只使用 `5173` Desktop。
- Desktop 侧栏包含：新聊天、运行工作台、资源库、知识库、社区。
- 项目列表留在侧栏，支持展开、置顶、项目操作和 Agent 操作；最近记录只在具体 Agent 上下文中显示。
- Community 在 Desktop 中是一个可操作页面，不要求用户跳到 `5174`。
- `5174` 后续只做公开展示、技术、下载和分享站。

### 3.2 视觉和交互

- 直接沿用旧 Veyra 的视觉语言：图标、图片素材、浅色/深色色调、侧栏、顶部栏、响应式布局、移动端和桌面端适配。
- 新页面右上角保持历史、语言切换和光暗模式位置；中英文结构都必须存在。
- 项目首页采用熟悉的聊天式/工作台式布局，不要把内部路径、保存位置或复杂技术表单暴露成主要体验。
- 点击 Agent 应进入 Agent 编辑/运行上下文；Project 与 Agent 菜单使用轻量、可理解的操作。
- 项目创建是应用管理的存储操作，不等同于“连接项目”；创建时不再要求用户选择一个非空目录，也不应把内部路径当成核心产品概念。
- 不要为了视觉完整伪造运行数据、社区数据或“已验证”状态。

### 3.3 Project 文件模型

项目是用户可见的真实一级实体：

```text
<Project>/
  project.vproject.yaml
  agents/
    <agent-slug>/
      agent.vagent.yaml
      README.md
      tests/
  resources/
  tests/
```

- `project.vproject.yaml` 保存稳定 `project_id`、名称、描述、Agent 列表、默认 Agent、资源策略和 schema version。
- `agent.vagent.yaml` 是 Agent 行为的可编辑真相；SQLite 只维护索引、Draft revision、immutable versions、runs 和 Factory session。
- Run、事件、缓存、凭据、账号令牌和临时文件不进入 Project 目录。
- 新建 Project 默认写到 Veyra 应用数据区；打开已有 Project 才显式索引外部目录。
- Community 下载/导入必须明确目标 Project，并生成新的本地 Agent 身份，保留远端版本和 Fork lineage。
- child-Agent 使用稳定 `parent_agent_id` 引用，文件系统仍保持扁平；当前 Desktop 侧栏支持 Agent 旁的加号和一层子 Agent 展开，不做递归执行。
- Project/Agent 可保存可选、可编辑的非秘密 Runtime API profile；真正的 API key 仍由 `.env`/Keychain 提供。

## 4. 代码目录和责任边界

```text
backend/src/veyra_agent_platform/
  contracts/          共享 Agent、Project、Runtime wire schema 与 canonical hash
  local/              Desktop 本地 API、Project、Factory、Studio backing、Runtime
    api/              FastAPI 路由
    projects/         Project/Agent 目录与生命周期
    library/          Draft、ETag、版本、导入导出
    resources/        Resource Catalog
    factory/          Kimi Factory 对话、Blueprint、解析、编译
    runtime/          Runtime model client、Tool adapter、图执行器
    storage/          SQLite migration、repository、objects
    templates/        平台内置 Agent 模板
  community/          独立账号、头像、邮件、Community 数据库服务

web/
  apps/desktop/       5173 唯一日常 Desktop 界面
  apps/community/     5174 后续公开站/展示下载界面
  packages/ui/         共享视觉、Shell、Surface、Status、Loading/Error
  packages/api-contracts/ 共享 TypeScript route/wire 类型

docs/
  PROJECT_DESIGN.md    当前产品和工程权威设计
  adr/                 已接受的架构决策

resources/nodes/
  <family>/<id>/node.yaml  平台拥有的 Component/Tool/MCP/Skill/Policy/Template 节点包
```

遵守根目录 `AGENTS.md`：不要创建 catch-all `utils.py`、`services.py`、`helpers.ts` 或巨型入口；共享 contracts、依赖锁和 migration head 一次只允许一个明确 writer；不要把旧 Veyra 仓库加入 `PYTHONPATH` 或包路径。

## 5. 当前已经实现并验证的部分

### 5.1 Project/Agent/Studio

- Project managed storage、创建、打开、重索引、编辑名称/描述、置顶、可恢复删除。
- 一个 Project 可以有多个 Agent；支持 blank、template、import。
- Agent 可通过 `parent_agent_id` 形成受限 child-Agent 关系；父子仍各自拥有独立的 Agent 源文件。
- Agent 源文件、README、tests scaffolding 写入 Project 目录。
- Project/Agent 创建和编辑可选填 Runtime API profile；运行时按 Agent override → Project profile → 默认 profile 选择。
- Studio 已有 Canvas、Form、Source 三种视图，共享严格 `AgentSource`；支持节点、连线、字段、图诊断、Draft revision/ETag、冲突恢复和 immutable commit。
- `ProjectSummaryResponse` 包含 `manifest_hash`，每个 Agent 包含 `source_file_hash`；不要重新引入只返回 201 却让前端解析失败的响应。

### 5.2 共享 Agent 合约

当前内置 Component：

- `Start`
- `Agent`
- `Tool`
- `Condition`
- `Transform`
- `HumanApproval`
- `Verifier`
- `Output`

`AgentBlueprint` 是不可信 Factory 输出；服务端必须先解析和验证，再生成 `AgentSource`。当前 Blueprint 的 `required_capabilities` 支持：

- `component_types`
- `tool_refs`
- `skill_refs`
- `policy_refs`

AgentSource 会保存：输入/输出、节点/连线、模型引用、工具引用、权限、secret refs、verification、UI positions 和 dependency lock。Canonical `source_hash`、`behavior_hash`、`lock_hash` 已存在。

### 5.3 Resource Catalog

当前 Catalog 总计 33 个 immutable builtin descriptors，源定义位于 `resources/nodes/<family>/<id>/node.yaml`：

- 10 个 Component
- 9 个 Tool
- 1 个 MCP descriptor
- 6 个 Skill
- 3 个 Policy
- 4 个 Template

状态必须诚实：

- `veyra.tool.filesystem.read@1.0.0`：`ready` + `supported`，现在有真实本地 adapter。
- `veyra.tool.filesystem.write@1.0.0`：`ready` + `supported`，默认 `approval_required`，真实本地 adapter。
- Workspace Shell、HTTP Request：`ready` + `supported`；Shell 和 HTTP 写入默认需要 HumanApproval。
- GitHub Read/Write：`ready` + `supported`，分别提供只读和审批后的仓库 API 调用；Browser Navigate 仍为 `unavailable`。
- `veyra.mcp.call@1.0.0`：仍是通用占位 descriptor；配置服务器后发现的 MCP Tool 会被规范化为 `ready` + `supported`，审核后可进入 Factory/Runtime。
- Agent Component：`requires_configuration` + `runtime_not_configured`，设计可以继续，运行需要模型。
- Skills 是非执行指令资产；Policies 是解析和 Runtime 授权的 overlay；Templates 是可 Fork 的完整 Agent 定义。
- `node.yaml` 由本地 Resource Catalog 校验并计算 content hash；`spec.ui` 只给 Studio 调色板，不进入 Factory snapshot，也不进入 lock hash。Factory 只能组装 `factory_selectable` 节点。特殊节点只作为隔离的声明式缺失能力提案，不会自动生成或执行任意代码。

关键修复：Resource Catalog 的 `required_permissions.tools` 必须使用完整资源 ID，例如 `veyra.tool.filesystem.read`，因为 AgentSource 合约会将 Tool node 的 `uses` 去掉版本后进行精确匹配。短名 `filesystem.read` 会导致项目创建或编译失败。

### 5.4 Factory/Kimi K3

Factory 已从静态禁用页面升级为真实 Project-scoped 对话：

- `GET /api/v1/factory/status`
- `POST /api/v1/projects/{project_id}/factory/sessions`
- `GET /api/v1/projects/{project_id}/factory/sessions/{session_id}`
- `POST .../messages`
- `POST .../generate`
- `POST .../apply-draft`

行为边界：

- 对话、消息和生成状态保存在应用 SQLite `factory_sessions` / `factory_messages`，不进入 Project source。
- Factory 只生成 Draft，不直接运行、发布或授予权限。
- Kimi K3 使用 OpenAI-compatible transport、模型发现、严格 JSON Schema、完整 repair message chain。
- `reasoning_content` 只在一次请求链内使用，不持久化。
- Blueprint 最多三次受限修复；未知能力变成不可执行的 `MissingCapabilityProposal`，不会自动注册或执行模型生成代码。
- 服务端从 Catalog 推导权限、锁和 Resource Plan；不信任模型声明的权限。
- Skills 会编译进 Agent model prompt，精确 Skill hash 进入 lock；Policies 会检查网络、写入、审批和验证要求。
- 用户必须明确确认，服务端才会把 Blueprint 编译为新的 Agent Draft 并交给 Studio。

Factory 默认配置在代码和 `.env.example` 中：

```text
VEYRA_FACTORY_MODEL_BASE_URL=https://api.moonshot.cn/v1
VEYRA_FACTORY_MODEL_ID=kimi-k3
VEYRA_FACTORY_MODEL_API_KEY_ENV=MOONSHOT_API_KEY
VEYRA_FACTORY_REASONING_EFFORT=high
VEYRA_FACTORY_MAX_COMPLETION_TOKENS=16384
```

国际 endpoint 可通过环境配置覆盖；不要硬编码或打印真实密钥。官方 API 行为参考：[Kimi K3 Quickstart](https://platform.kimi.ai/docs/guide/kimi-k3-quickstart) 和 [Chat API](https://platform.kimi.ai/docs/api/chat)。

### 5.5 Agent Runtime

当前 Runtime 已不是“Agent 永远不支持”：

- Runtime model client 位于 `backend/src/veyra_agent_platform/local/runtime/client.py`。
- Runtime profile 位于 `runtime/config.py`，与 Factory provider 分离。
- 开发环境可使用 host process `MOONSHOT_API_KEY`；production/release 会拒绝共享 host key，要求用户提供自己的 Runtime API/profile。
- Agent node 支持 `model.primary`，会向配置的 OpenAI-compatible provider 发起请求。
- Knowledge binding 会按版本和内容 hash 校验，将明确绑定的 Project 文档注入模型上下文，并在 Run 事件中记录 receipt；侧边栏索引本身不等于 Runtime 上下文。
- Desktop Settings 支持把 `model.primary` 和 `github.main` 保存到 macOS Keychain；`MOONSHOT_API_KEY` / `GITHUB_TOKEN` 仍可用于 headless 环境。
- 已验证 string、object、array、number、boolean 的声明输出映射；不接受未声明字段。
- 无 Runtime key 时，Run 以明确的 `runtime_not_configured` 失败，不伪造输出。

### 5.6 Tool Runtime

当前真实 Tool adapter：Filesystem Read/List/Search/Write、Workspace Shell、HTTP Request、GitHub Read/Write，以及审核后的 discovered MCP Tool。

- 执行前先做 authorization：Catalog availability、runtime status、完整 content hash lock、source permission subset、adapter 是否安装。拒绝会记录 `tool.requested`（`permission=denied`）并失败，不会动手。
- Read：Project 内相对 UTF-8 文件路径；输出 `content` 字符串。
- Write：Project 内相对 UTF-8 文件；输出 `{ written: true }`。默认 `approval_required`。无 HumanApproval 路径时 execute 失败 `approval_required`，文件不会出现。
- 两者都拒绝绝对路径、`..` traversal、软链接、`.env`/credentials/密钥类后缀、非普通文件和超过 1 MiB 的内容。
- Run 事件记录 `tool.requested`、`tool.started`、`tool.completed`；receipt 只包含 adapter、相对路径、字节数和输入/输出 digest，不记录文件全文。Write 的 `content` 只进 digest。
- HumanApproval 会把同一 run 置为 `waiting`，持久化 approval request 和 checkpoint。`approve`/`reject` 从下一节点继续同一 run；`stop` → `cancelled`；`retry` → 新 run；`resume` 对审批等待返回 `command_not_applicable`。
- Shell、HTTP、GitHub Read/Write 和 discovered MCP Tool 已可运行；Browser Navigate 仍明确不可执行。MCP 服务器命令、参数和环境绑定保存在应用数据，环境绑定可以指向主机变量或 Keychain secret reference。
- Tool 节点支持 `input_mapping` / `output_mapping`，Runtime 先映射后授权，执行后按映射回写，避免外部 MCP/GitHub 字段名绑死 Agent 输入。

### 5.7 Project child-Agent 与 Runtime profile

- Local migration `local_0009_agent_hierarchy_runtime_profiles` 增加 `agents.parent_agent_id` 和 `runtime_api_profiles`。
- Local migration `local_0010_runtime_control_plane` 增加 `runtime_runs.inputs_json`、`runtime_tool_calls`、`runtime_approval_requests`、`runtime_checkpoints`、`runtime_run_commands`。进程重启只打断 `running`，不会把 `waiting` 审批等待标成 `interrupted`。
- `GET/PATCH /api/v1/projects/{project_id}/runtime-profile` 与
  `GET/PATCH /api/v1/projects/{project_id}/agents/{agent_id}/runtime-profile`
  只保存 provider、base URL、model ID、API-key 环境变量名，不保存原始 key。
- Project 创建/编辑和 Agent 创建/编辑表单均有“可调用 API（选填）”；未配置时保持本地设计能力，运行时返回明确的 `runtime_not_configured`。
- Agent 侧栏每个 Agent 的 More 旁边有加号，直接打开创建子 Agent 对话框，不跳转页面。

### 5.8 账号与社区基础

Community 已有真实账号基础：

- 邮箱验证码注册
- 邮箱/密码登录
- refresh/logout
- 忘记密码与重置
- 会话设备查看和撤销
- Profile 名称修改
- 头像上传、读取和删除
- Argon2id、HMAC/hash OTP、限流、HttpOnly/Secure/SameSite Cookie、CSRF 边界、邮件 outbox/QQ SMTP provider

Community 目前还没有 Agent registry、发布 quarantine、公开版本、下载、Import/Fork、Star、Review、Report 和管理员审核队列。

## 6. 当前 API 入口

### Local API

- `GET /api/v1/health`
- `GET/POST /api/v1/projects`
- `POST /api/v1/projects/open`
- `GET/PATCH/DELETE /api/v1/projects/{project_id}`
- `GET/POST/PATCH/DELETE /api/v1/projects/{project_id}/agents...`
- `GET/PATCH .../draft`
- `POST .../validate`
- `POST .../commit`
- `POST .../draft/reload`
- `GET .../export`
- `GET /api/v1/resources`
- `GET /api/v1/resources/{resource_id}/versions/{version}`
- `GET /api/v1/components`（兼容 Component projection）
- `GET /api/v1/factory/status`
- `POST/GET .../factory/sessions...`
- `GET /api/v1/runtime/status`
- `GET/PATCH /api/v1/projects/{project_id}/runtime-profile`
- `GET/PATCH /api/v1/projects/{project_id}/agents/{agent_id}/runtime-profile`
- `POST .../run`
- `GET .../runs`
- `GET .../runs/{run_id}`
- `POST .../runs/{run_id}/commands`（`approve` | `reject` | `stop` | `resume` | `retry`，需要 `Idempotency-Key`）
- `GET .../runs/{run_id}/events`（replayable SSE，waiting 时保持跟随直到终态）
- `POST /api/v1/system/select-directory`

Local Run 的 POST `/run` 会立即返回 `running`。节点事件会在执行过程中落库，并可通过 SSE 回放/跟随。已有 idempotency、immutable version binding、Tool authorization/receipt、`waiting` 审批暂停、durable `run_command` 和本机 Agent conversation context。完整 token 流尚未实现。`resume` 对审批等待不适用。

### Community API

- `POST /api/v1/auth/verification-codes`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/confirm`
- `GET /api/v1/account/me`
- `GET/PATCH /api/v1/account/profile` / `/api/v1/account/me`
- `POST/DELETE /api/v1/account/avatar`
- `GET/DELETE /api/v1/account/sessions...`
- `GET /api/v1/avatars/{user_id}`

## 7. 当前前端状态

### 已接入真实 API

- Desktop Project sidebar/tree、Project detail、Agent context、Studio。
- Project/Agent 创建和编辑表单支持可选 Runtime API profile；Agent 旁的加号可直接创建 child-Agent。
- Resource Library：组件、Tool/MCP、Skills、Policies、Templates；显示 availability、Runtime 状态、权限和 hash。
- Factory Conversation：需求输入、对话、生成 Blueprint、Resource Plan、missing capability、确认创建 Draft、打开 Studio。
- Studio Test Run：输入表单、真实 Run、结果、节点状态条、事件列表、Runtime key 提示；`waiting` 时显示审批文案和批准/拒绝/停止；可订阅 run event stream。
- Account/auth 页面和 Connected Account package。
- Desktop/Community 共享 UI package，浅色/深色、中英文和响应式 Shell。

### 仍是占位或静态演示

- Root `#/projects` 当前兼容地显示 New Chat；真实 Project 列表主要在侧栏和 Project routes。是否恢复一个独立 Projects dashboard，要以用户后续 UX 决定。
- `#/chat` New Chat 仍是入口提示；具体 Agent 对话在 Agent context 中走 Runtime Chat。
- Agent 详情现在直接进入 Runtime Chat；Factory 只保留在新 Agent/Factory 路径。
- `#/runs` 已读取真实 Agent/Workflow Run API；`#/monitor` 已读取真实本机 Orchestrator/WorkItem API，仍可继续增强实时聚合和 reconcile 视图。
- Desktop `#/community` 仍使用静态 entries；真实 Community registry 尚未实现。
- Agent version detail 页面已接真实 Agent version API，仍可继续增强源码/依赖证据展示。
- 目前没有 Tauri/PyInstaller 完整发行包。

## 8. 已知缺口和不可宣称的内容

当前不能宣称“完整 V1”。未完成项：

1. Tool Runtime 仍缺 Browser Navigate；Filesystem、Shell、HTTP、GitHub Read/Write 和 discovered MCP tools 已接入真实 adapter boundary。
2. POST `/run` 已立即返回 `running`，并通过可回放 SSE 推送节点事件；完整 token 流尚未做。Studio/Agent 对话已有运行节点状态和审批控制面（waiting、approve/reject/stop/retry、checkpoint）；`resume` 对审批等待明确不适用。
3. Agent conversation 的更丰富可恢复能力；当前已支持持久化多轮 model context、会话切换、消息详情和最近 20 次 Run 回放。
4. Orchestrator：WorkItem、依赖、lease、worktree、retry、stall/reconcile。
5. Monitor/Runs 已切换到真实 API；Orchestrator 的 lease、attempt、worktree、retry 和更丰富 reconcile 仍未完成。
6. Community registry：publish/quarantine/hash scan/download/import/Fork/Star/Review/Report/moderation。
7. Tauri/PyInstaller/macOS arm64 包。
8. 新加坡 Caddy、PostgreSQL、MinIO、worker、备份和公网部署。
9. 完整双账号联网 E2E、真实 SMTP/Kimi live lane 和跨服务同 SHA 发布证据。

## 9. 推荐下一步顺序

不要同时铺开所有 V1 页面。建议按用户能看见的闭环推进：

### 已完成：Tool authorization + Run control + node.yaml catalog

1. Tool call 已提升为 authorization/receipt 边界。
2. `filesystem.write` 已落地，默认要求 HumanApproval，限制在 Project workspace。
3. durable `run_commands`、approval request、checkpoint、stop/retry 已落地；审批等待用 approve/reject 继续同一 run。
4. 可回放 SSE、Test Run 节点状态条和异步 POST `/run` 已落地。
5. Resource Catalog 以 `resources/nodes/<family>/<id>/node.yaml` 为唯一事实源；手写 `catalog.v1.json` 和 in-code fallback 已移除。AgentSource 的 Flow 图组件类型没有改。

### 已完成：Catalog 驱动 Studio 调色板

Studio 从 Catalog（含 `spec.ui`）投影节点卡片。Tool 在画布上可以显示成 Read File / Write File，源文件仍是 `component_type: Tool` + `uses`。

### 已完成：Tool Runtime 首批外部能力

Filesystem、Shell、HTTP、GitHub 和 MCP discovered tools 已有 Runtime adapter、权限校验、审批/receipt 或 secret binding；MCP 使用 newline-delimited JSON-RPC，发现结果需审核后才能进入 Factory/Runtime。

### 已完成：Agent conversation

1. Factory conversation 与 Agent conversation 继续分开。
2. Agent conversation 只服务已有 Agent 的输入、Run、历史和证据，不重新生成 Agent source。
3. 复用 Runtime provider boundary；没有用户 API 时只允许设计/查看，明确禁止运行。

Agent Chat 现在从 Agent 详情入口直接进入，支持最近 Run 回放、conversation 列表/切换、新建会话和持久化消息上下文。

### 下一波 B：Orchestrator completion

补齐 WorkItem lease、attempt、retry、stall/reconcile 和更清晰的 Monitor 状态；保持数据来自真实 Local API，不做装饰性大屏。

### 下一波 C：Community registry

先实现 Agent/template 不可变版本的 quarantine、hash/secret/path/symlink 扫描、下载、目标 Project 导入和 Fork lineage，再做 Star/Review/Report/审核。

### 下一波 D：发行与部署

只有本地闭环和 Community registry 有证据后，才做 Tauri/PyInstaller、新加坡部署、备份和公开 5174 站点。

## 10. 验证和启动命令

后端：

```sh
cd /Users/spectre/PycharmProjects/veyra-agent-platform
conda activate veyra-agent-platform
make check
```

前端：

```sh
cd /Users/spectre/PycharmProjects/veyra-agent-platform/web
npm test
npm run typecheck
npm run build
```

开发启动示例（不要把输出中的密钥贴给别人）：

```sh
cd /Users/spectre/PycharmProjects/veyra-agent-platform
VEYRA_BUILD_SHA=61f44989e9992eee94a8034ae4cfb9bda71c5fdf \
  /opt/anaconda3/envs/veyra-agent-platform/bin/python -m uvicorn \
  veyra_agent_platform.local.app:app --host 127.0.0.1 --port 8771

python -m dotenv -f .env run -- env \
  VEYRA_BUILD_SHA=61f44989e9992eee94a8034ae4cfb9bda71c5fdf \
  /opt/anaconda3/envs/veyra-agent-platform/bin/python -m uvicorn \
  veyra_agent_platform.community.app:app --host 127.0.0.1 --port 8772

cd web
npm run dev --workspace=@veyra/desktop
```

最后一次验证结果：

- GitHub Actions Push 和 Pull Request：`8019f41` 均通过；Backend Ruff/mypy、242 个后端用例和迁移门禁通过，Frontend typecheck/tests/build 通过。
- Local live：`8771 /api/v1/health` 返回 `build_sha=a65386b...`、`local_0015_agent_conversations`；`/api/v1/secrets`、`/api/v1/runtime/status`、`/api/v1/factory/status`、`/api/v1/mcp/servers`、Agent conversation routes 可用，未输出任何密钥值。
- Desktop production build 仍有约 611 KB 主 JS chunk warning；不影响构建，但应在功能闭环后用动态分包处理。

## 11. Git 与协作规则

- `main` 是稳定治理基线；`codex/agent-platform` 是唯一集成分支。
- Worker 只改被分配目录、提交 commit、报告测试和 SHA；主控负责复核、整合、推送和重启服务。
- 不要自行 cherry-pick 或 force-push 不明提交；先检查远端和工作区。
- 用户数据、Project 目录、SQLite runtime 状态和 `.env` 都不是可提交内容。
- 精确 SHA 的本地服务、CI、前端构建和 E2E 证据必须分开报告。
- 保持当前 Veyra 产品命名和边界；文档不要把参考产品名称写进实现决策。

## 12. 相关文件

- [主设计文档](./PROJECT_DESIGN.md)
- [贡献者边界](../AGENTS.md)
- [Resource Catalog / Factory ADR](./adr/0003-resource-catalog-and-factory-conversation.md)
- [Runtime provider / Tool adapter ADR](./adr/0004-local-runtime-provider-and-tool-adapter-slice.md)
- [项目进度 Canvas](/Users/spectre/.cursor/projects/Users-spectre-PycharmProjects-veyra-agent-platform/canvases/veyra-agent-platform-progress.canvas.tsx)
