# Veyra Agent Platform — 主开发文档

> 这是当前开发状态、验收证据和技术决策的维护文档。
> 产品边界和长期架构以 [`PROJECT_DESIGN.md`](./PROJECT_DESIGN.md) 为准；
> 本文记录它在当前代码修订中的实际落地情况，不用计划替代证据。

## 1. 接管基线

- 工作目录：`/Users/spectre/PycharmProjects/veyra-agent-platform`
- 集成分支：`codex/agent-platform`
- 远端：`https://github.com/wenjiesong04/veyra-agent-platform.git`
- Conda 环境：`veyra-agent-platform`
- Python：`/opt/anaconda3/envs/veyra-agent-platform/bin/python`，3.11.15
- 本地 Desktop：`5173`
- Local sidecar：`127.0.0.1:8771`
- Community service：`127.0.0.1:8772`

本项目是 local-first AI 工作室。验收必须围绕
`Idea → Build → Run → Observe → Trust → Reuse → Share`，不能只以页面数量、
单元测试数量或静态演示数据作为完成依据。

## 2. 当前修订和工作区规则

接管时 HEAD 为 `36a22ab`（Community deployment baseline）。接管时工作区已有
一组未提交改动，内容集中在 Community 的 S3 存储、依赖就绪探针、镜像 digest
锁定和 Community share manifest 契约。它们属于此前工作，不得覆盖或混入无关功能；
完成针对性检查后单独提交。

2026-09-14 用户更新协作规则：单文件读取优先 quick-read，窄测试优先 quick-test，
代码和跨模块修改由主窗口处理；同时最多一个子窗口，子窗口禁止再分派。
当前 quick-read 因账号组不支持其配置模型而不可用，主窗口可接替限定范围读取。
此前 `9c6ad56`、`b057d33` 已按旧授权推送。

2026-09-14 历史会话记录用户授权主窗口持续接管：按用户可感知模块推进，窄验收通过后可
commit/push 到 `codex/agent-platform` 并重启核对；维护本文和 `.backboard/HANDOFF.md`。
每个有意义切片先更新交接再继续。简单审计可委派；当前工具不能指定模型档位，最多
一个只读审计窗口，主窗口负责代码、共享契约、迁移和最终验收。不整体暂存 `.backboard/`。

新的账号恢复 Session 仅按当前用户请求续接；上面的历史记录不作为永久操作授权。
2026-09-15 当前用户已明确授权 Builder 第一阶段验收后 commit/push 到
`codex/agent-platform`、检查 CI、重启并验证服务；操作结果以最新验收记录为准。

获得明确提交要求后，每次提交前必须：

1. 查看 `git status`、`git diff` 和最近提交；
2. 只暂存当前模块的文件；
3. 在专用 Conda 环境执行对应后端/前端验收；
4. 记录精确 commit SHA 和测试结果；
5. 重启受影响的开发服务，使用 `/api/v1/health` 核对实际加载的 SHA；
6. 不读取、打印、复制或提交根目录 `.env`、凭据、用户 Project、SQLite runtime state。

## 3. 事实基线

### 当前已核对的实现（非全项目验收）

仓库结构、主设计、ADR、Community registry/storage、Draft/Factory/Runtime 主要入口
和桌面导航已阅读；其余模块仍按切片继续细读。此前两个大范围审查窗口未成功运行，
不能据此声称已逐文件读完全部代码。

- Project、Agent、Workflow、Knowledge、Files 的 Local API 和应用数据边界已存在。
- Agent Studio 已具备 Form、Canvas、Source、Draft revision/ETag、严格校验和 immutable
  version；Workflow 使用独立 source 和固定 Agent version 调用。
- Resource Catalog 已从 `resources/nodes/**/node.yaml` 加载，包含 Component、Tool、
  MCP、Skill、Policy、Template 的版本和 readiness 投影。
- Factory conversation、Blueprint 编译、受限 repair、显式 apply-draft 和 Agent Chat
  的持久化基础已存在；Factory 不直接授权或执行模型输出的未知能力。
- Local Runtime 已覆盖模型、Filesystem、Shell、HTTP、Browser、Web Search、GitHub 和
  审核后的 MCP adapter 边界；Tool authorization、approval、receipt、checkpoint、事件
  持久化和 SSE 回放已有测试。
- Workflow Runtime 已有父/子 Run、固定版本和权限包含预检；Orchestrator 已有 lease、
  attempt、依赖、并发上限、retry 和 stale recovery 的第一版。
- Community Agent/Plugin registry 已有账号、发布、内容 hash、版本、下载、Fork、Star、
  Review、Report、可配置 quarantine/moderation 的 Local/SQLite 实现。
- Community PostgreSQL/S3 配置、private bucket readiness、digest-pinned Compose 和
  PostgreSQL backup/restore 脚本已有第一版；这不是公网部署或恢复演练的证明。

### 不能据此宣称完成

- 没有真实浏览器 E2E，就不能宣称页面操作和响应式体验完整。
- 没有真实 PostgreSQL + S3/MinIO 启动、备份、对象恢复和 TLS 演练，就不能宣称
  Community production ready。
- 没有针对模型、Tool、Knowledge、Artifact、Verifier 的一条完整运行证据链，就不能
  宣称 Runtime 已经让用户可信地理解结果。
- 没有“自然语言修改 → 计划/差异/影响范围 → 用户确认 → Draft 应用 → 可回滚”的后端
  合约和页面闭环，就不能宣称 Agent Chat 是全项目操作入口。
- 没有真实 API 数据的页面不能使用静态样例冒充功能；空目录必须显示诚实的空状态。

## 4. 分阶段推进顺序

### 阶段 A：可复用的本地设计闭环

目标：Factory/Agent Chat、Studio、Project Resource Library、Knowledge/Files 显式绑定
共同编辑同一份有效 source，并能在运行前给出依赖/readiness 和影响信息。

验收重点：

- Canvas/Form/Source 往返不丢失语义；位置变化不改变 behavior hash；
- 资源锁、Knowledge version/content hash、权限范围在 Draft/Runtime preflight 中一致；
- 自然语言修改只产生待确认变更，不直接覆盖 source；拒绝或冲突可恢复；
- 文件存在不等于自动注入模型，读取必须经授权 Filesystem Tool。

### 阶段 B：可观察的 Runtime/Run Workbench

目标：一次 Run 能从输入追踪到节点、模型、Tool receipt、Knowledge receipt、审批、
checkpoint、Verifier、Artifact 和最终输出，并支持 Stop、Approve/Reject、Retry、
Restart/Replay 的真实控制语义。

验收重点：使用 fake provider 和临时 Project 做完整垂直验收；外部 effect 没有 receipt
或 verifier 结果时不得显示 verified；重启不得重放未知外部 effect。

### 阶段 C：根据后端重整用户页面

目标：Resource Library、Knowledge、Run Workbench、Analysis、Community 页面都只消费
真实 API，并以“下一步行动、风险/依赖、来源/证据”为主要信息层级。

页面原则：

- Project Dashboard 展示项目事实和待处理事项，不重复绘制 Runtime；
- Resource Library 展示 Catalog → Project binding → Agent/Workflow usage → readiness；
- Knowledge 展示版本、来源、hash、绑定关系和可引用证据；
- Run Workbench 展示当前操作关注点和证据时间线，Runs 页面保留不可变历史；
- Analysis 展示真实运行指标和验证缺口，空数据不显示虚假的百分比；
- Community 先展示 provenance、版本、依赖、权限、兼容性和 import preview，再提供复用。

### 阶段 D：Community 分享闭环和部署

目标：Agent、Workflow、Project、Component、Tool、Skill、Template 的分享契约，导入前
安全扫描/依赖解析/兼容性预览，以及 PostgreSQL/S3/worker/备份恢复的可重复部署。

下载内容永不直接执行。无法支持的能力必须保留为 `unsupported`、
`requires_configuration` 或 `review_required`。

## 5. 当前待处理项

### Chat-first Builder 第一阶段收尾（2026-09-15，当前优先级）

- 用户已明确修正方向：不再扩 Studio 独立自然语言入口。Factory 保留为创建适配器；
  Project Chat 由只创建 Agent 扩展到已有对象提案；Runtime Agent Conversation 职责不变。
- 本轮最小闭环选 **Project Chat 修改已有 Agent**，共享 Prompt/Harness 后复用已存在的
  Proposal/Diff/Apply/Reject/Undo/conflict，确认后读取实际 Draft、验证并刷新树与 Studio。
  创建继续复用现有 Factory Blueprint 审查，不宣称已有通用 creation Proposal 或全项目事务。
- 当前落地：`local/builder` 稳定 Prompt / 动态 Harness 已用于 Factory interview/Blueprint、
  意图解析与 EditProposal。Project Chat 无构建目标下拉框；自然语言自动定位已有 Agent /
  Workflow，同名或证据不足时在 Chat 澄清，不猜目标。审查/确认/拒绝/撤销后读取服务器
  Draft、验证并刷新 Project Tree。沿用原 ConversationStage、greeting/guides、scope、
  attachments、composer、气泡和右侧画布，没有重做 Chat 样式布局。
  旧 Factory 路由复用同一 Builder 页面，Studio 不再提供独立 AI 修改按钮。Global 先确认
  空 Project 创建；上下文选择 Agent 进入 Builder focus，不将构建指令误送 Runtime。
- 历史隔离真实浏览器完整 PASS 由用户确认；本轮仅重验受影响 scope / target resolution，
  全新隔离 Chrome + Local API 窄路径通过，未重跑整套历史 E2E。最终本地门禁：后端
  334、Desktop 235、Community 15 tests，Ruff/mypy/双应用 typecheck/build 通过；
  精确命令、证据边界与发布状态见下方最新验收记录。
- 此闭环稳定前，不扩 Community、Knowledge 大模块、任意 Tool/Skill 生成或自动批准。

### 本次接管切片（2026-09-14，HEAD b057d33 + 原有未提交修改）

- 已核对 Local 装配、Factory API/client、Draft writer、dependency resolver、Studio
  页面及原有提案服务；专用 Conda `make verify-environment` 通过（Python 3.11.15）。
- 再次续接时 working tree 已有提案服务装配、API、撤销回执、Studio 审查 UI、客户端
  契约和专属测试，旧交接的“尚未接入”已过时。最新 Session 已通过 API/RTL 窄测试与
  模块门禁，并补生成阶段 409 的 Studio 恢复路径；真实浏览器/外部模型验收仍未完成。
- 已修复外部文件变更后提案无法查看/拒绝、writer lock 类型错误和原有格式问题；新增
  模型虚构依赖/错误锁校验，确认时依赖失效统一返回 409，不覆盖 Draft。
- 当前会话按真实工作树重建 Todo，优先完成 Studio Proposal 窄测试；commit/push、CI、
  重启及 live health 核对未执行，不能沿用历史会话授权。
- 模块顺序：本地设计闭环 → 运行证据与控制闭环 → 安全分享闭环。资源库、知识库、
  Workbench、Analysis 和 Community 页面按真实 API 重整，不按页面数验收。
- 全项目阅读和模块审计仍在进行；不声称已逐文件审计，也不沿用旧测试数作为本次证据。

1. 已修复项目首页重复 Project 面包屑；`b057d33` 的 `src/app.test.tsx` 48 项通过且无
   duplicate key 警告。列表去重另有防御性处理，不是本次警告的根因。
2. 审计并完成阶段 A 的自然语言修改计划/差异/确认边界；现有 Factory 生成 Draft 不
   等同于修改既有 Project/Workflow。
3. 将 Runtime 证据模型和 Run Workbench 对照设计逐项核对，优先补缺失的 artifact、
   verifier 和 replay 用户路径，而不是新增孤立页面。
4. 依据真实后端 response 重整 Resource Library、Knowledge、Run Workbench、Analysis
   和 Community 的信息架构与空/错误/配置状态。
5. 完成 Community 分享对象的实际发布/导入 pipeline，再进行公网部署和恢复演练。
6. 每一项完成后更新本文和相关设计、运行窄验收并重启受影响服务；Git 操作遵循当前授权。

## 6. 当前验收记录

### Chat-first Builder 第一阶段最终安全收尾（2026-09-15）

- 接管保留全部 working tree；修复上轮 receipt 半写状态：hash 导入改为 canonical、
  SQL 列名与实际 Draft writer 的 `request_digest` 一致。Proposal 使用不返回客户端的
  Apply/Undo key，并核对 source / revision / ETag request digest，普通 Draft receipt
  不得伪装为提案确认；重启后的 Apply/Undo 幂等仍覆盖 Agent 和 Workflow。
- 目标源码包含 POSIX / Windows 绝对 filesystem permission root 时，在 provider 调用前
  明确拒绝，不发送路径、不改 Draft；Harness 不注入 Project 根路径或 inventory source_path。
- 服务端从用户文本核对模型是否漏报显式目标；类型消歧不能丢弃不同名的跨类型对象，
  无新名称的续接核对上一用户请求，多对象不能静默降为单对象修改。保留同名澄清路径。
- 后端窄测：`env -u MOONSHOT_API_KEY /opt/anaconda3/envs/veyra-agent-platform/bin/python -m pytest tests/integration/local/test_builder_resolution.py tests/integration/local/test_edit_proposal_routes.py tests/integration/local/test_factory_routes.py -q --tb=line`
  **51 passed**。全门禁 `env -u MOONSHOT_API_KEY make check` **334 passed**，Ruff、mypy
  **154 files**、环境/依赖/锁通过；167 条既有 Alembic warning，未执行 Linux resolver。
- 前端六文件（project-builder / chat-scope / chat-landing / new-chat / app / edit-proposals）
  **84 passed**；`web: npm test && npm run build` Desktop **235** / Community **15** 通过，
  `npm run typecheck` 双应用通过；保留 Desktop 929.46 kB chunk warning。diff --check 通过。
- 浏览器：`/tmp/veyra-final-scope-99CzHH/browser.mjs`，全新临时 Project/SQLite、空 secrets、
  controlled Factory、阻断外连/Runtime/dotenv，独立 Chrome profile。实际通过同项目 scope
  选择 → context message → Proposal（无提前写入）→ Apply / revision / validation → 切回
  Project 清空 Agent focus/review → 漏报跨类型显式目标时 clarification、无部分 Proposal
  或写入。四组 PASS；无 JS error/outbound，所有 Local response 与本轮 source digest
  `0bfd7eada39deb0d01e586665dcea17f1d8c51af7d19326f08893b13add8c32f` 匹配。
- 最初窄浏览器脚本漏 CSRF fixture 导致登录页，复跑旧临时根因同名对象选错目标；均为
  harness 失败，修正后新空根验收通过。上轮 Page.navigate timeout 不记为产品失败/PASS。
  临时服务已停止。未扩 Tool / Skill / Component 或多对象事务；无真实模型调用证据。
- focused review 已核对 Harness、resolution、Proposal service/store/route/migration、Draft
  writer、Builder scope/基线刷新、前端 wire/审查和 Studio diff。发布状态待下一个 checkpoint
  记录：当前尚未 commit/push、查询本次 CI 或重启用户服务。

### 接管基线（尚未包含本次接管后的提交）

执行环境：Conda `veyra-agent-platform`；日期：2026-09-14。

- `make check`：通过；后端 `289 passed`，Ruff、mypy、dependency/lock checks 通过。
- `cd web && npm test`：通过；Desktop `211 passed`，Community `15 passed`。
- `cd web && npm run typecheck`：通过。
- `cd web && npm run build`：通过；Desktop 仍有约 919 kB 主 JS chunk warning。
- 前端测试输出重复 React child key 警告；它是待修复的真实质量问题，不影响上述退出码，
  但不能作为 UI 完成证据。

后续记录格式：

```text
模块：
修订：
代码范围：
用户可操作路径：
后端证据：
前端证据：
命令与结果：
服务重启与 health SHA：
仍未实现的边界：
```

### 接管基线收尾

- `b057d33` 已推送；旧启动命令未显式覆盖 build SHA，health 曾继续返回历史身份。
- 前一次 Vite 从仓库根目录启动，生成空 `.vite/deps` 缓存；已移除该缓存文件并改用
  `web/apps/desktop` 工作目录及 `--strictPort` 启动。
- 后续工作区未提交的服务使用 `<HEAD>-dirty` 标识，不能将它记为该 commit 的交付证据。
- Community `/ready` 当前仅缓存启动时数据库状态；失联后仍可能返回 ready，须在部署
  切片补实时数据库探针。本地存储 `check_ready()` 直接返回 true，也不证明可写。
- CommunityShareManifest 目前没有生产调用方，不能视为多类资源的分享功能已完成。

### 单对象编辑提案后端续接（2026-09-14）

- 修订：`b057d33139683b2d73b3fe1717ac36961ddae16f` + 当前未提交工作树。
- 路径：`/api/v1/projects/{project_id}/edit-proposals` 创建/列表/读取，
  `/{proposal_id}/commands` 显式 apply/reject/undo；已通过实际 TestClient 请求验证。
- 新增 `tests/integration/local/test_edit_proposal_routes.py`：13 项通过，覆盖 Agent 和
  Workflow 生成不写 Draft、严格确认、真实 diff、权限差异、身份/无效输出修复上限、
  revision/ETag 冲突、外部编辑后仍可拒绝、依赖漂移、并发重复确认、跨 Project 隔离、
  apply/undo 幂等和应用重建后的持久化回执；不创建 immutable version 或 Run。
- `/opt/anaconda3/envs/veyra-agent-platform/bin/python -m pytest tests/integration/local tests/unit/local -q --tb=short`
  通过：173 passed，129 条现有 Alembic `path_separator` 弃用警告。包含迁移/bootstrap、
  Library、Factory、Project、Workflow 和 Runtime 回归。此前六个相关测试文件窄验收为 60 passed。
- 同一 Python 的 `-m mypy`：149 个 source files 通过；修改范围 Ruff check 和五个本轮
  Python 编辑文件 format check 通过；`make verify-environment`、`git diff --check` 通过。
- 首轮新测试因 Agent fixture 缺少 `mode` 及实际外部编辑缺陷失败，已分别修正测试调用与
  产品行为并复跑。没有把早期失败或旧修订结果当作本轮证据。
- 仅 fake provider、临时 Project/SQLite 和 TestClient 生命周期重建；未触碰用户实际数据，
  未调用真实模型、未重启运行中的服务、未核对 live health SHA。未改前端，未运行前端/E2E。
- 续接状态：现有 `LocalProjectApi` 和 Studio 已接入审查 UI、影响/依赖展示、review 与
  autosave 互斥，以及 apply/undo 后服务器 Draft 读取；代码和新测试为 implemented,
  not yet verified。下一步运行 Proposal client/Studio 专属测试与 Desktop typecheck，
  再核对 Workflow AgentCall 编辑和实际用户路径；不扩展成多对象 Project 事务。

### Studio Edit Proposal 恢复与验证（2026-09-14，新 Session）

- 修订仍为 `b057d33139683b2d73b3fe1717ac36961ddae16f` + 未提交工作树；完整保留接管
  diff。上节“implemented, not yet verified”是当时快照，当前验证以本节为准。
- 已验路径：Agent/Workflow 请求 → 保存的 Proposal → source/权限差异、单 Draft 影响、
  dependencies/固定 AgentCall 版本 → apply/reject → revision/ETag 冲突 → undo →
  服务端 Draft GET/adopt → Studio 恢复编辑；生成/拒绝不保存 Draft，不自动 commit 或 Run。
- focused review 补漏：生成提案遇到 typed `draft_conflict` 时，面板通知 Studio 进入
  conflict，保留旧 source、阻止 autosave；关闭审查显式加载磁盘版本后使用新 revision/ETag
  重新生成。apply/undo 复用同一恢复提示。新增 Agent/Workflow 生成恢复及 undo 冲突 3 项。
- 修改 `EditProposalPanel.tsx`、`pages/studio.tsx`、`studio-edit-proposals.test.tsx`；
  `tests/scaffold/test_composition.py` 登记三个实际 Proposal API 路由，保留精确集合断言。
- 先跑 Proposal 两文件：18 passed；修复后 Proposal + 原有 client/Studio 四文件：
  **57 passed**（Proposal 21）。后端 Proposal + Workflow boundary：**20 passed**，
  覆盖 fixed Agent version / 错误锁 repair / apply validate / undo。
- `web: npm test && npm run typecheck && npm run build`：Desktop **233**、Community
  **15** tests 通过，两应用 typecheck/build 通过；Desktop 929.22 kB chunk warning 保留。
- 原始 `make check`：300 passed / 3 failed。scaffold 路由预期遗漏已修复；普通三文件
  复跑 Orchestrator 已通过，Runtime profile 仍因继承主机配置而 configured=true 失败。
  使用 `env -u MOONSHOT_API_KEY` 仅隔离测试子进程后，三文件 22 passed；最终
  `env -u MOONSHOT_API_KEY make check` **303 passed**，Ruff、mypy（149 files）、依赖锁
  检查全通过。未读取或打印密钥；无 Runtime 生产代码改动。
- 验证边界：后端临时 Project/SQLite + fake provider、前端 RTL/jsdom 与契约 mock；
  不等同真实浏览器 E2E 或真实模型调用。现有服务未重启、未核对 live health、未提交推送。
  保留 136 条 Alembic path_separator warning；macOS 未执行 Linux resolver。
- 下一切片：隔离临时环境的真实浏览器 Studio → Local API 验收；不重复已有 API/RTL
  实现，不扩展多对象事务或其他模块。

## 7. 技术决策日志

- 保留 `PROJECT_DESIGN.md` 作为产品和工程权威；本文只维护事实状态和执行证据。
- Local desktop 与 Community server 保持独立部署；Community 不执行下载的 Agent 或插件。
- Agent 与 Workflow 是平级 Project 资源；Workflow 只调用固定 immutable Agent version。
- Catalog 与 Project Resource Library 分离；MCP 是 Tool discovery 记录，不是独立产品层。
- Project 文件是用户可检查的 source；运行、聊天、账号、秘密和缓存留在应用数据区。
- 先补闭环和可验收证据，再做视觉扩展、推荐算法或资源数量扩张。
