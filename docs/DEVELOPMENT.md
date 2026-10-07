# Veyra Agent Platform — 主开发文档

## 生成质量参考评估与生成器方法修复（2026-10-08）

已读取《提高Agent生成质量》两轮对话，作为不可信参考与当前代码对照；取舍见
[GENERATOR_REFERENCE_REVIEW.md](GENERATOR_REFERENCE_REVIEW.md)。采用后半版的现有
TaskStructure/编译/门禁主线，保留有界语义审查；不新增平行TaskSpec、多模型评分链或
Factory真实副作用自动执行。静态通过、可启动与任务验收不能合并成“产品级”。

本轮修改生成器自身：TaskStructure阶段方法/信息源进入自治loop指令；coverage包含
Workflow Tool锁，读取选中Skill的准确hash正文并把方法提供给修复。只增加相关上下文，
不增加固定模型调用。能力名字生成的Skill保持scaffold，Factory/Workshop批准与启用
入口均不将其伪装ready；真实方法通过现有准确快照流程，幂等发布清除旧pending元数据。
精确Skill选择的resolver接口已有基础，自然语言选择及完整生成路径仍需集成验收。

当前切片相关8个pytest文件 **95 passed**；3源码mypy、相关Ruff、diff check及分析画布
TypeScript检查通过。未新跑真实Provider/浏览器/打包验收，未重新启动服务来宣称本切片
已加载，未commit/push。此前长任务的状态/表格/前端改动保留，不能据本切片测试声称
整个脏工作树全部通过。

## Generator Harness 与普通用户实测（2026-10-05）

生成链已换为真实TaskStructure规划、完整closed schema验证、有界修复、资源能力与typed交接、独立覆盖审查；原生ask_user/reply可在同一固定版本Run暂停/恢复。实测继续修复了context、阻塞终态、registry前端兼容、原生Tool参数、Agent状态契约/安装/查询与并发scope。新增Entity Query和安全Arithmetic资源，不改变旧资源hash、依赖或迁移。结果阅读使用Veyra现有设计系统与指定Skills审查。

真实多轮陈列案例已从浏览器完成生成/提交/运行/选择/改预算/刷新恢复/确认交付，保持一个Run与v1；status为unverified，不是独立语义校验通过。初版合计错误记录为质量问题，新算术工具的真实使用仍待验收。对账与周计划后续真实生成收到HTTP429，不能计为通过。当前产品级结论：尚未证明。代码门禁：后端1142、Desktop661通过；mypy241 sources、Ruff/format/diff、两web typecheck/build通过。最新微调另有schema/state13与reading38定向通过；Desktop构建仍有既有large chunk提示。详细案例、修复与证据边界在[GENERATOR_USER_ACCEPTANCE.md](GENERATOR_USER_ACCEPTANCE.md)，当前检查日志与继续点在HANDOFF。

## Settings / Workflow 运行页与真实校验故障（2026-10-05，本地未提交）

- Settings 改为 Veyra 既有视觉语言中的单内容工作区：我的 API、界面偏好、工具授权、创作助手。服务预设填写地址，自定义协议仍走通用 transport；阿里云专属业务空间地址提供明确引导。保存连接→发现/手动添加模型→显式测试→任务默认值在同一上下文内完成；大量模型支持搜索和分批展示。界面偏好具有实际主题、语言和减少动态效果设置。没有新依赖、React Bits 或 GSAP。
- Workflow App 按 design-taste-frontend 的 preserve/audit 指导重构：紧凑标题与版本、完整说明弹窗、单一任务输入；运行后只显示提交摘要和真实节点状态，图片输入为缩略素材条；成功后结果只显示一次，已完成进度与技术证据按需展开；失败保留步骤和子 Agent 结果入口。历史错误可回到新任务，缺失旧版本不会冒用最新说明。committed version/hash/预检与收费运行授权边界保持。
- 最终 web-design-guidelines 审查修复状态温和播报、焦点返回、重名字段覆盖、缺失版本说明、错误恢复及回链 run_id；真实浏览器另外发现全局标题段落样式截断弹窗全文，已修 CSS 优先级并复验390px/暗色全文与 Escape。隔离模拟验收准备、运行、完成、失败；临时源码/标签页/viewport已清理。
- 真实历史故障：两个子 Agent 均完成，Renderer 的 PNG 与非空对象已经保存；shared required_fields 校验构造包含列表的集合，引发 TypeError，被压成 workflow_execution_failed。已修安全比较，Workflow Verifier仅检查声明输出，与 Agent graph一致，并记录 verifier.result。用真实已保存输出执行修复后的三项check均通过，PNG内容存在；没有重新调用收费模型，也没有改写历史失败记录。
- 证据：Desktop全量630 tests通过；Backend运行/Artifact/Workflow/Agent相关91 tests通过（包含新校验11项和Workflow integration15项）；Ruff、format、两Runtime source mypy、Desktop/Community typecheck/build和diff check通过。Community全量23/24，已有account测试期待Name而页面已用Display name，隔离复跑同样失败，未扩大修改该模块。Earlier image protocol focused88 tests仍属于独立定向证据。
- Live：用户此前重启的8771进程加载了图片API适配；用户主动测试Qwen图片生成成功，模型证据active_probe/supported。当前新Verifier修复尚未由该进程加载，5173后续停止；已请求本轮明确服务重启授权，不能从历史handoff推断。未stage/commit/push、未由代理新增真实图片/Workflow调用。
- 生成质量的未完成边界：完整的三方案/用户选择/修改/状态保留需求，当前确定性生成器降为single_run的分析→出图→校验；companion执行说明只有通用角色brief，Renderer未消费Analyzer结果，生成validation不验证需求覆盖。修复执行校验不代表复杂自然语言生成已经可靠，也不代表用户原助手需求完整实现；后续必须修Planner与需求保真门禁，不能靠增加业务关键词或修改历史版本掩盖。

> 当前实现状态、验收证据和模块优先级。
> 产品边界以 [`PROJECT_DESIGN.md`](./PROJECT_DESIGN.md) 为准；长期 AI 职责见
> [`AI_DEVELOPMENT_BRIEF.md`](./AI_DEVELOPMENT_BRIEF.md)。
> 本文记录代码里已经落地的事实，不用计划、旧 Session 或历史测试数字替代证据。

## 1. 环境

- 工作目录：`/Users/spectre/PycharmProjects/veyra-agent-platform`
- 集成分支：`codex/agent-platform`
- 远端：`https://github.com/wenjiesong04/veyra-agent-platform.git`
- Conda：`veyra-agent-platform`
- Python：`/opt/anaconda3/envs/veyra-agent-platform/bin/python`（3.11.15）
- Desktop：`5173`；Public Showcase：`5174`；Local API：`127.0.0.1:8771`；Community API：`127.0.0.1:8772`

验收围绕 `Idea → Build → Run → Observe → Trust → Reuse → Share`。
页面数量、静态演示数据和过期测试计数都不是完成依据。

## 当前实现（2026-10-04，Model Capability Registry 与 Workflow 使用页）

- Provider connection 与 Model Profile 分离；16 项 tri-state capability/evidence、目录发现、手动 ID、能力默认、确定性 ModelResolver 已落地。未知不满足 required，图片理解不等同图片生成。
- Builder 按 actor/role 派生实际 Provider 协议需要的模型能力；模型缺口留在 Model Registry，Draft 可审核/Apply 并标 Needs Setup。当前平台 JSON-action loop 不强制要求 Provider 原生 tools/JSON mode。
- Agent/Workflow preflight 与实际调用共用当前能力证据标准，检查连接、Profile 与 digest/revision；支持 metadata/adapter 和 active probe，错误显式绑定及 stale evidence fail closed。
- Settings 和运行页可配置模型。原页配置窗口支持添加 API、手动模型、显式费用确认后的验证、绑定及自动检查；不丢失本次任务输入。当前主动探测覆盖 text generation / structured output / image input / image generation。
- Workflow 使用页按 taste-skill 的既有项目审计收敛：紧凑配置条，主输入区单一边界，明确运行 CTA，流程/历史渐进展开；修复历史重试、预检过期响应、390px CTA 与版本控件裁切。
- 门禁：Backend `env -u PYTHONPATH make check` **982 passed**（依赖/format/lint/mypy 通过）；Desktop **72 files / 574 passed**、typecheck/build 通过；`git diff --check` clean。真实登录态页面与只读明暗/390px 验收通过；未在浏览器启动 Workflow 或调用真实 Provider。
- Live：用户在原启动环境重启后，8771 新进程加载最终代码；health `ok`、schema `local_0036_model_capabilities`、database_ready=true，Builder configured=true。真实 Workflow committed 预检 version/hash 匹配；当前只剩图片生成能力未验证，需要用户补配置。未 stage/commit/push，未由代理调用真实 Provider。
- 详细 A–R 报告见 [Model Capability Registry V1](MODEL_CAPABILITY_REGISTRY_V1_REPORT.md)。以下日期条目保留历史证据，不覆盖本条当前边界。

## 当前修复（2026-10-02，Builder 实时跟进与 Workflow 映射校验）

- Builder 新对话在慢速解析前先通过 SSE 发送已持久化的初始快照；Desktop 收到每帧快照立即更新并取得 conversation ID，让 1 秒持久化轮询能在最终流结束前工作。进入 Runtime 模型绑定等待时，无需刷新才看到选择面板。中文等待提示也已本地化。
- Desktop 的运行模型面板改为清晰的 Provider / 模型选择表单，使用可读的等待状态与本地密钥说明；`create_workflow` 的 Runtime 绑定等待也能显示该面板。项目切换时不再暂时展示上一项目的聊天。`unsupported` 与一般失败的创建请求不再保留假进度工作台，`unsupported` Activity 明确标为未创建。
- Workflow Studio 的 AgentCall 校验现在按后端契约分别检查 Agent 字段 slug（允许连字符）和 Workflow 变量 ID（允许下划线）。用户示例中的合法 `model-known → model_known` 不再被误报；错误提示不再写死无关的 `request → prompt` 示例。
- 验证：Builder Desktop 定向 4 文件 / 99 tests、Workflow Studio 定向 2 文件 / 51 tests；Backend Builder conversation 文件 34 tests；Desktop typecheck/build 与 `git diff --check` 通过。实际浏览器看到旧 `unsupported` 对话不再留假工作台、运行模型面板宽屏与窄屏布局、示例 Workflow 红条消失且测试入口恢复。获用户本轮授权后已重启 Local API `8771`，health `ok`、数据库就绪且 revision 为 `local_0034_project_entities`。没有对真实 Project 再发一次 Builder 请求做端到端流式复验。
- Workflow App（`#/projects/:projectId/workflows/:workflowId/run`）是 Workflow 的独立使用窗口：只运行明确提交的 Workflow 版本（`source=committed` + `version_id`），预检结果必须与所选版本的 `version_id`、`source_hash` 一致才可启动。Studio 测试运行仍使用 Draft。迁移 `local_0035_workflow_versions` 新增 `workflow_versions.committed`，旧快照需重新提交才会出现在 App 中。需要审批的 Workflow Tool 在预检与运行时都会被拒绝，直到有经过验证的 Workflow Tool 审批关卡。

## 当前产品边界（2026-09-29，Builder Generation Architecture V2）

Builder 主链不再是「用户说 Agent → Start→Model→Output → 把逻辑塞进 instructions」。生成先得到 `TaskStructure` 与 `ExecutionBoundary`，再做 `ProductShapeDecision`，再编译 `ExecutionPlan`，再走既有 CapabilityRequirement → ResourceResolver → Composer → Proposal → Apply。

```text
User Request
→ TaskStructure / ExecutionBoundary
→ ProductShapeDecision
→ ExecutionPlan
→ CapabilityRequirement
→ ResourceResolver / Resource Factory
→ Composite Proposal
→ Composite Apply
→ Agent loop 和/或 typed Workflow
```

- 产品模型未改：Agent = 自主 model/tool loop；Workflow = typed deterministic DAG。
- `classify_builder_target` 只记录 `user_requested_surface` 偏好。用户说「帮我做一个 Agent」不会锁死 `PURE_AGENT`。
- Shape：`PURE_AGENT` / `WORKFLOW` / `AGENT_WORKFLOW` / `MULTI_AGENT_WORKFLOW` / `UNSUPPORTED`。判断用结构边界，不用 gift/research/translation/software engineer 职业分支。
- HumanApproval 分两类：业务节点 vs Runtime Tool permission。HumanInput 复用 `HumanApproval.review="input"` + Workflow `reply` / checkpoint，不新造 pause engine。
- Persistent State 是窄的 Project Entity Store V1：migration `local_0034_project_entities`（`project_entities` / `entity_records` / `entity_events`）+ catalog `entity.read` / `entity.write`。不是通用数据库产品。
- Verifier 进入 Workflow DAG。缺 `image_generation` 时 Proposal 标 `missing_required`，Apply 拒绝，不假装 vision 能出图。
- Planner 默认确定性结构抽取；若注入 Provider，最多 3 次 schema repair，失败 `planner_invalid`，不回退关键词启发式。
- Proposal UI 展示 Product Shape、阶段、Execution Plan、Resources/bind、业务审批 vs 工具审批、缺失能力。操作：审查并创建草稿 / 修改方案 / 取消。
- Apply 复合路径：companion Draft → commit → Workflow AgentCall pin `agent_id@version_id`；失败 rollback。
- Local head：`local_0034_project_entities`（`entity_records(project_id, entity_type)` 与 `entity_events(entity_id)` 索引；`entity_events → entity_records` ON DELETE CASCADE）。`EntityStore.write` 拒绝跨 Project / 跨 entity type 覆写同一 `entity_id`（`entity_scope_conflict`）。
- Workflow Tool 节点：mapping key 必须是连字符 slug，所以 `entity_id` 由 Runtime 从 values 默认传给 entity 工具；无 `result` 时默认 payload 是 values 快照（避免自引用 checkpoint 失败）。
- Factory `generate()` 不再要求 Platform Builder Provider（V2 编译是确定性的）；interview / capability probe / planner repair 仍按需检查。Runtime Provider 要求未放宽（`runtime_not_configured`）。
- 8771 已安全重启并加载 0034：live DB 自动备份 `.pre-migration` 后 0033→0034，Projects/Agents/Versions/Conversations/Runs 行数不变。未重启 5173/5174/8772。未 commit / push。

验证（V2 Closeout，2026-09-30）：`env -u PYTHONPATH make check` **947 passed** + ruff format/check + mypy 通过（sandbox 内）。原 `test_plugin_registry` PermissionError 根因是 Community test fixture 未注入 `registry_storage_root`，回落到用户 Application Support；已在 fixture 中注入 tmp 根并断言。Desktop `npm test` **68 files / 536 passed**；typecheck/build 通过；`git diff --check` 干净。Live Entity Store smoke（临时 Project，已清理）通过。Browser E2E unavailable。未调用真实外部 Provider。

## 当前产品边界（2026-09-28，V1 Release Candidate Cleanup）

本轮不增加产品能力。把已完成的 V1 主链整理成可审查的 Release Candidate：dirty tree 分类、Fixture 隔离回归、对话标题不再泄漏 UUID、Agent App 主交互面可用、migration 0027–0033 线性 head 校验、文档诚实记录 V1 限制。

- 产品模型不变：Agent = loop；Workflow = typed DAG。
- Local DB head：`local_0033_agent_app_versions`。
- Agent App 对话 `title` 是用户可见文案；`conversation_id` 只作内部 ID。UUID / 空 title 显示 `New conversation` 或首条用户消息摘要。
- `/projects/:id/agents/:aid` = App；`/design` = Studio；`/run?run_id=` = Run Detail。树点击进 Studio；Open App / Edit in Studio / Back to Agent 是产品入口。
- 自动化测试必须用临时 DB + 隔离 `project_storage_root`。不删除无法证明归属的真实用户 Project。
- 测试分层：unit（`tests/unit`）/ integration（`tests/integration`）/ acceptance（`tests/integration/local/test_complex_agent_acceptance.py` 是 V1 核心产品链回归）。
- 未实现且不是 RC blocker：loop 出图、真实浏览器自动化、完整 Policy、vector RAG、MCP 产品化、任意可执行 Tool 生成、Community marketplace、音视频。

验证：`env -u PYTHONPATH make check` **915 passed**（ruff/mypy 通过）；Desktop `npm test` **68 files / 519 passed**；typecheck/build 通过；`git diff --check` 干净。8771 已安全重启：`pid=46045` `status=ok` `database_ready=true` `database_revision=local_0033_agent_app_versions` `build_sha=0ad7a3e0…-dirty`。未重启 5173/5174/8772。未 commit / push。Browser E2E unavailable。Real Provider 未执行。

## 当前产品边界（2026-09-28，Complex Agent Product Acceptance）

本轮不增加新的大能力。证明 User Request → Specification → Resolver →（缺能力时 Factory）→ Composer → Apply → Commit → Agent App → AgentLoopRuntime 能作为一条产品链跑通三类不同 Agent，并修掉阻断闭环的问题。

- Research Analyst：自然语言请求得到 web_search / knowledge / research_planning / evidence_synthesis；Resolver 选 Web Search、Research Brief、Evidence Ledger、Project Knowledge；Apply pin/lock；Commit 后 App conversation 跑 scripted Web Search（无公网）+ Knowledge marker + 第二 turn 历史。
- Software Engineer：workspace search/read/write + shell；临时 Project 内真实写文件、真实 pytest；observation 驱动第二次修复；write/shell 按 Catalog approval；reject 无 side effect。无领域 hardcode。
- Packaging Analysis：image_understanding + Project Knowledge + Skill；hybrid App、synthetic PNG 以 `data:image/png;base64,` 进入 Model；第二 turn 保留 Artifact；`image_generation` 仍 missing/unsupported。
- Factory Skill：`comparative_risk_method` missing → Draft → validate → approve → publish → Resolver retry → Commit → App → `skill.loaded`。
- Composer 把 `needs_configuration` 工具写入 lock/bindings，committed GitHub Agent 在 App preflight 返回 422 `needs_configuration`，不创建 Run。
- 本轮 generate 是 Specification-seeded HTTP Factory chain + scripted interview completions，不是真实 Builder Provider。
- 无新 migration：`local_0033_agent_app_versions` 足够。无领域 `if research_agent` 分支。

验证：`env -u PYTHONPATH make check` **909 passed**；Desktop **67 files / 515 passed**；typecheck/build 通过；`git diff --check` 干净。Browser E2E unavailable。Real Provider acceptance was not performed.

## 当前产品边界（2026-09-28，Agent Run App V1）

Studio Test Run 执行当前 Draft；Agent App 只执行 committed immutable Agent version。未 Commit 时 App 显示 empty state，不偷偷跑 Draft。Conversation 在创建时 pin `agent_version_id`；新对话默认最新 committed version。`interaction_mode` 为 `auto|chat|form|hybrid`，只决定产品交互面，不改变 Runtime tool 语义。旧 Agent 缺省 `auto`。App 复用 RuntimeInputForm / RuntimeOutputView / useLiveRun / SSE；审批摘要由 Server 根据 tool id 与校验后的 args 生成；Run 前 preflight Runtime model 与 resource configuration。image Artifact / document 走既有 multimodal 抽取链。本轮不宣称 loop 出图。

验证：`env -u PYTHONPATH make check` **901 passed**；Desktop **67 files / 515 passed**；typecheck/build 通过；`git diff --check` 干净。Browser acceptance unavailable。

## 当前产品边界（2026-09-28，Resource Factory V1）

Resolver 确认 `missing_required` 后进入正式 Factory seam。`ResourceFactoryStrategy` 分类为 `generatable` / `requires_user_configuration` / `requires_external_integration` / `unsupported`。可生成的只有 Skill instruction 与对已有 adapter 的 declarative Tool Wrapper（`http.request`、filesystem read/search/list）。Draft 先隔离，校验后用户确认才发布为不可变 Catalog overlay；Resolver 通过 Catalog metadata 重新发现，Composer 再 pin/lock。不静默发布，不发明任意代码 executor，不为 `image_generation` 造假资源。

验证：`env -u PYTHONPATH make check` **890 passed**；Desktop **65 files / 498 passed**；typecheck/build 通过；`git diff --check` 干净。Browser acceptance unavailable。

## 当前产品边界（2026-09-28，Resource Resolver & Agent Composer）

create_agent 主链是 Capability Requirement → Resource Resolver → ResourcePlan → Agent Composer。Resolver 只从 Catalog/Project snapshot 选资源；不再用 `_CAPABILITY_TOOLS` 或领域关键词把 capability 映射成 tool ID。Proposal 保存 ResourcePlan snapshot，Apply pin 该 snapshot 的 content_hash。缺失 required capability 显示 `missing`，不生成假资源。Policy 绑定仍是 `runtime_support=partial`。旧 graph Template 不进入 loop composition。

验证：`env -u PYTHONPATH make check` **854 passed**；Desktop **65 files / 497 passed**；typecheck/build 通过；`git diff --check` 干净。Browser acceptance unavailable。

## 当前产品边界（2026-09-28，Loop Agent Resource Truth）

Agent / Workflow 产品模型不变。本轮只把 loop Agent 的资源链做成可执行事实：

```
Catalog resource
+ availability
+ Project pin
+ Agent lock hash
+ Agent permission
+ Runtime adapter
+ required configuration
```

缺 pin 时 Runtime fail-closed（`resource_unbound`），Apply 不会静默换成更新版本（`resource_identity_conflict` / `resource_binding_conflict`）。Skill 是 instruction resource，不是 Tool。Knowledge V1 仍是 txt/md 有界检索。image Artifact 进入 ModelRequest Image part；document/pdf 进入有界抽取文本。

本轮不做 Resource Resolver、Resource Factory、新 Run App、Workflow Builder、真实 Provider、浏览器自动化。

验证：`env -u PYTHONPATH make check` **831 passed**；Desktop **65 files / 497 passed**；typecheck/build 通过；`git diff --check` 干净。8771 需重启后加载此代码。Browser acceptance unavailable。

## 当前产品边界（2026-09-27）

以 `0ad7a3e0b2a11ccf9186f23dab40628375509c73` 的本机闭环为准。那一版的生成、Chat
和其余本机页面是正常的。之后未提交的 Cloud data plane（Cloud Project、Conversation、
File、Credential、Cloud Run，以及把 `8772` 换成 Cloud Host）不再作为产品。

- `5173` 和 `8771` 是本机软件。Builder、Chat、Studio、Runtime 只走 Local API。
- `5174` 是公开展示，加上 `#/community`、登录和账号。不提供云端工作区。
- `8772` 继续做 Community 账号和 Registry，启动模块是
  `veyra_agent_platform.community.app:app`，不是 `veyra_agent_platform.cloud.app:app`。
- 桌面端不再把 Project 或 Builder 对话自动同步到云端。侧边栏「最近」读本机
  `GET /api/v1/builder/activity`。

## 当前产品模型（Agent ≠ Workflow）

Veyra 是 Agent + Workflow 的 AI 工作室。两者在 Project 中平级，contract、Builder、
Runtime、Studio、Source、Run 语义分开；共享 Provider / Tools / Knowledge / Files /
Credentials / Runs / Events / Receipts / Resource Library。

- **Agent**：自主能力单元。Builder `create_agent` 编译 `execution_kind=loop` 的
  AgentSource（说明、工具绑定、知识、typed I/O、`max_turns`）。Runtime 是
  model↔tool loop，不是 DAG scheduler。Studio Canvas 是能力图。
- **Workflow**：显式 typed 图。Builder `create_workflow` 编译 WorkflowSource
  （Start / AgentCall / Tool / Condition / Transform / HumanApproval / Verifier /
  Output、`data_edges`）。AgentCall 必须锁定已提交 Agent version。上一轮 typed
  dataflow、DataflowStore、quality、structural simulation 归 Workflow 基础设施；
  Artifact / 多模态类型仍可被 Agent 与 Workflow 共用。
- 历史 Start→Model→Condition→Approval 图作为 `execution_kind=graph` 保留，可打开、
  不可静默迁移。简单 Start→Model→Output 可转为 loop Agent；明显编排图应转为
  Workflow。
- 本轮不做 Community marketplace、RAG、Loop/Parallel/Schedule/Webhook 节点、
  audio/video Runtime、浏览器自动化。

## 2. 已发布模块（Git 事实）

| 模块 | SHA | 范围 |
| --- | --- | --- |
| Chat-first Builder Phase 1 | `9153617` | Project Chat 修改已有 Agent/Workflow：提案 → 确认 → Draft；不是全 Project 事务 |
| Runtime V1 | `ea94b64` | 事件/回执、审批、Stop、安全 Retry、checkpoint Resume、run_id 历史证据 |
| Resource Library V1 | `ee814e2` | Catalog 真实 readiness → Project pin → Agent lock → Runtime 按 pin 执行 |
| Knowledge V1 | `8351806` | 本地 txt/md ingest → 显式索引 → 绑定检索 → Run 引用证据 → Resource-Library 风格工作台；浏览器闭环在 `560a912` 上验收 |
| Graph Compiler V2 | `8bef91c` | SemanticPlan → 可执行 Agent 图 + Default Canvas Note + Provider schema hardening |
| Typed I/O + Artifact Runtime | `5f8e8a8` | TypedField / ArtifactRef、Project-scoped object store、Runtime modality truth、shared Test UI |
| Agent Composition & Capability System V1 + Canvas Runtime Execution Overlay V1 | `0ad7a3e` | Slice 1–5 已随该提交发布；Alpha/Beta branch 与 approval overlay 已有隔离 fixture 手工浏览器证据。此前获准的真实 Builder Proposal 曾语义失败；Branch Semantics 修复后未再次调用真实 Provider，因此 Builder real-provider acceptance 仍未通过/未复验 |

GitHub Actions Billing 仍是外部阻塞，不把未执行的 CI 写成代码失败或 CI PASS。

以下 Slice 2–5 测试数字和未发布状态是 2026-09-22 的历史 checkpoint；它们已被上表的 Git 事实与后续验收取代。不要再把 Agent Composition V1 写成 uncommitted。

Slice 2 先前基线：后端 687 tests、Desktop 436 tests、Community 15 tests，以及
当时记录的 typecheck/build；这些数字不代表 Slice 3 精确修订的验收。

Slice 3 当前证据（2026-09-22）：`env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`
通过（后端 693 tests、Ruff format/check、mypy、dependency/lock checks）；
`npm test --workspace=@veyra/desktop` 通过（55 files / 439 tests），Desktop
typecheck 通过；Builder/Component/Resource/client/Studio 聚焦测试 107 passed；
`git diff --check` clean。尚无真实浏览器 E2E、真实 Provider/sidecar 验收或
release checkpoint；未 commit/push，因此这是本地实现与门禁通过，不代表发布完成。
实现边界及剩余验收见 `.backboard/HANDOFF.md` 最新的
**Agent Composition V1 — Slice 3** checkpoint。

Slice 4 当前证据（2026-09-22）：Conda `veyra-agent-platform` 下
`env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check` 通过（后端 **695 passed**、
Ruff format/check、mypy、dependency/lock checks）；Web 全量测试通过（Desktop
56 files / 450 tests，Community 3 files / 15 tests），两应用 typecheck 与
production build 通过。Desktop build 有既存的大 chunk 提示。`git diff --check`
最终核对通过。没有真实浏览器 E2E、Provider/sidecar 验收、GitHub CI 或 release
checkpoint；这是 Slice 4 阶段的历史门禁记录；Slice 1–4 未提交/推送，Slice 5 当前进度见下文。
Slice 4 细节与证据见 `.backboard/HANDOFF.md` 的
**Agent Composition V1 — Slice 4** checkpoint。

Slice 5 当前证据（2026-09-22）：Conda `veyra-agent-platform` 下
`env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check` 通过（后端 **695 passed**、
Ruff format/check、mypy、dependency/lock checks）；Web 全量测试通过（Desktop
59 files / 463 tests，Community 3 files / 15 tests），两应用 typecheck 与
production build 通过；Slice 5 聚焦 Desktop 测试 **133 passed**。Desktop Vite
报告主 JS chunk 超过 500 KB。另完成有限的 Chrome 手工 UI/Runtime 验收：Run 画布按
immutable version 恢复；一次合成输入的 Runtime Test Run 经配置 Provider 执行成功，
输出可见且刷新可恢复，Run 状态为 `unverified`（无 verifier 证据）。这不是正式浏览器
E2E 或发布验收。此处“Slice 1–5 未 commit/push”和浏览器验收待完成均为当时历史状态，
已由后续 `0ad7a3e` 发布与 2026-09-23 Alpha/Beta 手工浏览器验收取代。真实 Builder
Provider 的旧 Proposal 语义失败仍是当前验收缺口。

## 3. Knowledge V1（本轮收口）

本轮把未提交的 Knowledge 切片收成一个可发布模块，并按 Desktop 现有资源库风格做了友好工作台。

闭环：

`本地 UTF-8 txt/md 上传 → 真实 ingest/parse 状态 → 显式索引 → Agent 绑定且不静默升级 → 本地词汇检索 → Run 引用证据 → 使用中删除保护`

诚实边界：

- 不是 PDF/DOCX/OCR，不是 embedding/向量库，不是逐句 citation
- 文件在 Project 中不会自动进入模型
- 未索引、hash 漂移或跨 Project 引用会在调模型前失败
- Run 证据是实际进入 context 的 chunk locator，不是答案归因

工作台：

- 列表以状态徽章和下一步动作为主，hash 放在详情事实区
- 上传是主入口；空白“创建知识”仍保留为次要能力
- 详情区分未索引 / 已索引 / 需重建 / 失败，并提示下一步
- Run Detail 展开片段时核对历史 hash；来源链接打开当前资料

### 本轮验收（2026-09-16，专用 Conda，隔离测试环境密钥）

```text
模块：Knowledge V1
修订：`83518068937271c4a0372674284782b56500e47c`（`8351806`）
代码范围：Knowledge ingest/index/retrieval/evidence、Project API、Desktop 知识工作台
用户可操作路径：上传 → 构建索引 → 绑定 Agent → Run 查看引用 → 使用中无法删除
后端证据：env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check → 452 passed；
          Ruff format/check passed；mypy 157 files；dependency/lock checks passed
前端证据：web npm test → Desktop 309 passed，Community 15 passed；
          npm run typecheck / npm run build 通过（Desktop 主 chunk 约 958 kB warning 保留）
仍未实现：PDF/Office、历史全文仓库、Community 知识依赖重建、真实浏览器 E2E、真实 Provider
```

首次 `make check` 在沙箱里因无法写入
`~/Library/Application Support/Veyra Agent Platform/.../community/registry` 失败；
在未沙箱环境复跑后 plugin registry 用例通过。这不是产品回归。

### 发布验收（2026-09-17，`560a912`，隔离浏览器 E2E 补齐）

`8351806` 收口时未跑浏览器 E2E。本轮在**同一修订**上补完模块门禁和真实浏览器闭环，
Knowledge V1 由此记为 released。

```text
模块：Knowledge V1 = complete / released
修订：`560a912609c1b2e658a2b62b3ad22d9212bfbb20`（代码与 `8351806` 一致，`560a912` 仅文档）
Focused review：按 24 项边界逐条核对 Knowledge diff，未发现真实 bug，未改产品代码
后端门禁：env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check → 452 passed；
        Ruff format/check、mypy、dependency/lock checks 通过
前端门禁：web npm test → Desktop 309 passed（41 文件），Community 15 passed；
        npm run typecheck 通过；npm run build 通过（Desktop 主 chunk warning 保留）
浏览器 E2E：Chrome + playwright-core，隔离栈 27 checks / 0 failed
```

E2E 隔离方式（harness 在仓库外的临时目录，不入库）：临时 SQLite、临时 Project 根
`/private/tmp/.../projects`、loopback 脚本 provider `127.0.0.1:8899`，以及临时 Community
库中的一次性账号。脚本内断言 `root_path` 与 `runtime/status.model_base_url`，确保没有
触碰真实工作区、也没有调用外部模型。

真实浏览器覆盖的闭环：

- 上传 `knowledge.txt` → `ingested / parsed / not_indexed`，徽章 `Not indexed`
- 点击 Build index → `ingested / parsed / indexed`，`chunk_count = 1`
- Studio 绑定 → Draft 记录 `knowledge_refs` 且 `lock` 固定 source hash
- Validate & commit → 一个不可变版本携带 Knowledge pin
- Run（脚本 provider）→ `Chunk index 0 · Lines 1–1 · Rank 1 · Score 5`，证据带 reference
  与运行时 source hash；脚本 provider 收到的 prompt 只含绑定片段
- 展开片段 → 显示 `ORBIT-731`
- 按精确 `run_id` 刷新 → 不新建 Run（1 → 1），证据逐字节不变
- 空检索 → Run 合法，显示 `No relevant Knowledge chunks retrieved.`，无伪造引用
- 显式改内容 → 索引转 `stale` / 徽章 `Needs rebuild`；旧 Run 证据身份不变；
  旧片段预览被 422 拒绝（`Historical source changed`），不泄漏新 marker
- 使用中删除 → 409 `knowledge_in_use`，Knowledge 仍在 Project 中

未验收边界不变：PDF/Office、embedding/向量检索、reranker、GraphRAG、逐句归因、
历史 Knowledge artifact 仓库、真实外部 Provider、Community 知识依赖重建。
GitHub Actions billing 是外部阻塞，本轮未 rerun CI，也不当作本地发布阻塞。

## 4. 对照原六模块判断（已核对）

旧 Codex 总结里的测试数字（Python 289 / Desktop 211 / Community 15）和“六个模块都未完成闭环”已经过时，不得再当当前门禁。

| 模块 | 旧结论 | 当前事实 |
| --- | --- | --- |
| Canvas / Studio | 可演示，编辑闭环未完成 | 手动 Canvas/Form/Source 仍在；自然语言改单个 Agent/Workflow 已由 Builder Phase 1 承担。Component 完整编辑和视觉收尾仍弱 |
| Resource Library | 目录有了，日常工作台未完成 | V1 已发布：Catalog → Project → Agent → Runtime。没有历史 artifact 仓库 |
| Agent Chat | 只能生成新 Agent | Builder Phase 1 可改已有对象。Phase 2 Slice 1/2（未提交）已把 Knowledge 与 Project `filesystem.read` 从模型猜测改为服务端确定性绑定。仍不是整个 Project 的自然语言入口 |
| Runtime | 能跑，还看不清 | V1 已发布：审批/Stop/Retry/Resume 与持久证据。Canvas 节点级实时态和真实外部 Provider 仍缺 |
| Knowledge | 只有绑定，不是知识库 | V1 本轮收口：上传、索引、检索、引用。仍无 PDF/RAG |
| Community | 注册表第一版，差得最多 | Agent Directory 已走真实注册表 API；本轮补入 Published/Starred 真实列表和横向四意图导航。Following 后端关系/Feed 仍未实现，Agent/Plugin lane 之外的资源类型不伪装为可用 |
| 数据分析页 | 未点名完成 | 已读真实 Run 计数，不是友好分析工作台 |

三个跨模块闭环：

1. 设计闭环：V1 可用（Chat 改结构 + 资源绑定 + 知识绑定）。
2. 执行闭环：Runtime V1 + Knowledge 引用已齐；不是真实外部 soak。
3. 分享闭环：仍是最大缺口。

## 5. Builder Phase 2

Git 事实：Slice 1–4 与 ProviderCapabilityProfile / Harness Receipt 已包含在
`8f71a1e`。Agent Graph Compiler V2 + Default Canvas Note + SemanticPlan V2
Provider Hardening 已发布为 `8bef91c`。Phase 2 模块整体仍未做最终
Playwright CASE 1–3 release gate。

已落地：

- 自然语言 Knowledge 绑定：服务端解析、歧义追问、`knowledge_refs` + `source.lock`
  由服务端计算，Proposal 展示索引就绪状态
- 自然语言“让这个 Agent 可以读取项目文件”：只处理已 Project-bound 的
  `filesystem.read`，Proposal 展示 `bound_content_hash` / readiness / 最小权限；
  不自动 Add Catalog、不静默升级 stale、不自动授权、不自动 Test Run
- Apply 后 validation failure 是业务结果：typed Builder issue cards、仅对
  服务器已知 pin / 缺权限 / Knowledge hash 生成一条 EditProposal 修复；
  `resource_unbound` 与 `requires_configuration` 只解释不假修

证据见 `.backboard/HANDOFF.md` Slice 1 / Slice 2 / Slice 3 checkpoint；窄测试与
静态检查已过，全量 `make check` 与浏览器 E2E 留到模块收尾。

**Builder Phase 2 Slice 3（Apply 后 validation repair，历史切片编号）= complete**
（未发布；这不是 Agent Composition V1 的 Slice 3）。

闭环：Apply → backend validation → typed Builder feedback → deterministic
repair proposal → confirmation → repair apply → revalidation。

**Factory structured generation compatibility = resolved**（未发布）。

Root cause：kimi-k3 接受 `response_format.type=json_schema` + `strict=true`，
但完整 AgentBlueprint schema 不是 Moonshot MFJS。真实 400 是
`invalid_request_error`：`enum` 缺 `type`；随后 `$ref`→`oneOf` 被 Walle
误判无限递归。`const` 也不是 MFJS 关键字。

修复：`local/factory/structured_schema.py` 做 provider-compatible projection
（enum 补 type、`oneOf`→`anyOf`、`const`→enum、inline `$ref`）。完全空的
`verification` 可默认成 `{required:false, checks:[]}`。该投影保留为
compatibility bridge，不再是默认 Provider 合同。

**Builder durable conversation = complete**（未发布）。

用户消息在 resolve / Factory / 模型调用前写入 `builder_conversations` /
`builder_messages` / `builder_operations`。失败是历史事实；Retry 新建
`retry_of` 操作，不改写旧失败。左侧「最近」只投影 Builder Conversation
（聊天记录），不含 Runtime Run。右上「历史」仍是 Runtime Run History。

**AgentSemanticPlanV1 + SemanticPlanCompiler = complete**（未发布）。

默认 Factory generate：NL → Intent → AgentSemanticPlanV1 →
SemanticPlanCompiler → canonical AgentBlueprint → validation → review →
Confirm 后才 Apply。Compiler 复用 Slice 1/2 resolver，不猜、不 Catalog
auto-add。完整 AgentBlueprint 不再是默认 Provider-facing contract。

**Builder Interaction Model V2 = complete**（`aba074d`）。

Chat 不再把 Builder 生命周期渲染成系统气泡。`builder_operation_events`
是 server-owned 进度；Activity 一个 operation 一块，完成默认折叠。
Workbench 按真实阶段打开（理解 → 语义计划 → 编译 → 审查），Proposal
留在右侧，不作为 Chat 消息。Apply 使用 Semantic Plan `suggested_name`；
CJK slug 走现有 `agent-{hash}` 合同。Recent 两阶段标题：第一条 user
message 持久化后写 deterministic provisional title；semantic plan 成功
且标题仍是 provisional 时才升级为 `suggested_name`。失败会话不再叫
`Chat`。Create 与 Edit 共用 Conversation → Activity → Workbench →
Confirm → Result。`target_kind` 预留 agent | workflow。

Live Moonshot CASE 1（`New project`，「创建一个中英文翻译 Agent。」）：
generate → waiting → confirm → apply → 一次 result 通过。Agent 名
`中英文翻译 Agent`，slug `agent-0f68d95b`。HTTP 429 是 provider rate
limit，不是 V2 缺陷。CASE 2/3 走同一条真实 Builder path 的
scripted/local provider 验收。

完整 Playwright CASE 1–3 浏览器验收未在本环境执行（无 Playwright）。
产品证据是 live Moonshot CASE 1 + scripted CASE 2/3 + Desktop focused
tests。真正 browser acceptance 留到 Builder Phase 2 最终 release gate。

**ProviderCapabilityProfile = complete**（本 checkpoint）。

Profile 只回答「这个 Provider + Model + Endpoint 支持怎样的模型请求
协议」，不定义 Veyra Agent 语义。Canonical 仍是 AgentSemanticPlanV1 →
SemanticPlanCompiler → AgentBlueprint。`/models` 只证明模型可见，不是
structured-output 能力。

身份：`provider_id` + `model` + `endpoint_kind` + `base_url` fingerprint
（无 query / 无密钥）+ `probe_version`。缓存命中则普通 Builder generate
只读 profile，不 probe。显式 `POST /api/v1/factory/capability-probe`
用固定 `{ok: boolean}` synthetic schema；401/403/429/5xx/unknown 4xx
不降级 capability，429 记 `inconclusive` 而不是 unsupported。

Factory generate：probe 已知则 strict → 允许的 json_object；否则沿用
Moonshot static_known / 其它主机 fail-closed json_object。schema /
response_format 不兼容才允许一次 json_object fallback。结果仍走
AgentSemanticPlanV1 校验，再编译为 canonical AgentBlueprint。

Settings 只显示很轻的能力摘要 + Recheck。Builder Activity 不刷
profile 技术细节。

一次有界 live Moonshot probe（`api.moonshot.cn` / `kimi-k3`）：
`strict_json_schema_support=supported`，`status=known`，`source=probe`。
不是 429，不是 inconclusive，不是 unsupported。未创建 Agent。

**Builder Harness Receipt = complete**（本 checkpoint）。

一次真实模型调用一条 `BuilderHarnessReceipt`：先 persist
`prepared`，请求后再 finalize `success`/`failed`。失败也保留证据。
Receipt 只存安全 metadata（Harness / Policy / Contract / structured
mode / included+excluded categories / 有界 snapshot hash / 当时
ProviderProfile 摘要）。不存 prompt、Knowledge/File 正文、密钥、
Authorization、provider body、hidden reasoning。

五者不同：

```text
Conversation Message  ≠  BuilderOperationEvent  ≠  BuilderHarnessReceipt
≠  Proposal  ≠  Runtime Run
```

Activity 折叠「构建详情」展示人类可读 Provider / Contract / Mode；
hash 只在 Technical details。Chat 不刷 Receipt。无模型调用的
operation 不报 “No receipt found”。历史 Receipt 在 Recheck 后不变。
API 只走 Project-scoped conversation/operation。

明确未完成：Builder Phase 2 最终 release gate、Catalog → Project
mutation from Chat。

**Builder Phase 2 Slice 4 = complete**（已包含在 `8f71a1e`）。

闭环：

`Build → Validate → Explicit Test Run → Observe → Explain → optional
Repair Proposal → Confirm → Apply → Validate → explicit Run again`

Builder 只关联 `run_id` + 有界 `RunObservation`。Runtime V1 仍是
Run / events / evidence / approvals 的唯一 store。Test Agent 必须用户
显式点击；Apply / Repair 后不自动 Run。未配置 Runtime model 返回
`runtime_not_configured`，不把 Builder Kimi 绑给 Agent。

Builder Model ≠ Agent Runtime Model。当前 live 两者碰巧都是 Moonshot
`kimi-k3`：Factory 是 Builder；host default Runtime profile 是 Agent
执行模型。UI 不得把 Builder Kimi 标成 Agent Runtime，除非该 Agent 的
有效 Runtime 确实是 Kimi。

### 本轮基线（2026-09-22，`8f71a1e baseline verified`）

Git HEAD：`8f71a1e15481cddeb45830eb2482992fa4c20d8e`。

首次 `make check` 在该修订上因两处已提交 Ruff format 失败（decorator
折行、f-string 引号）。授权只修这两处后，完整 `make check` 通过：

```text
Backend pytest: 596 passed
Ruff format/check: passed
mypy: passed（175 files）
git diff --check: clean
```

先前同修订上的前端门禁：Desktop 409 passed、Community 15 passed、
web typecheck / build passed。这是 Compiler V2 开始前的 verified baseline。
不要再把 HEAD 写成 `4e3c2e6`，也不要把 Slice 4 写成未提交。

**Agent Graph Compiler V2 + Default Canvas Note + SemanticPlan V2
Provider Hardening = complete / released**（`8bef91c`）。

正式锁定：

- Agent = 可独立执行的能力内部图：Start / Model / Tool / Condition /
  Transform / HumanApproval / Verifier / Output
- Workflow = 多个 immutable Agent version 的编排；AgentCall 只属于 Workflow
- Knowledge 仍是 binding，不是计算节点
- `ui.notes` 默认存在、不是必填、不进 `behavior_hash`、用户可删
- `ui.labels` 只用于画布语义标题；Inspector 仍显示 component type

`AgentSemanticPlanV1` 保留 `steps: string[]`。可选 `step_intents` 描述
职责、operation kind、depends_on。Provider-facing schema 不包含
`branches`；Condition / Approval / Verifier 的额外 port 由 Compiler
确定性展开。模型不输出 node/edge id、resource hash、permission、
source.lock、canvas 坐标。

如果 `step_intents` 已表达 approval / condition / verification /
transform，生成失败不得静默退回 Start → 单 Model → Output。

Compiler V2：无 `step_intents` 且只有一个 summary step 时仍编译简单
Start → Model → Output；多个 summary steps 编译为顺序 Model 节点。
有真实职责边界时才生成多 Model / Tool / Transform / Condition /
HumanApproval / Verifier。不 hallucinate Tool，不 Catalog auto-install，
不 silent upgrade，不 permission overgrant。Verifier 只映射
`output.not_empty`；不能映射时编译为 Model + warning，不造假 Verifier。
默认 Note 由 SemanticPlan 确定性生成，不再额外调模型。

Live CASE C 根因（真实 Moonshot / kimi-k3）：Provider schema 曾包含
嵌套 `branches.then`，而 MFJS 投影会剥掉名为 `then` 的 property，导致
连续三次 `missing field(s): then` → `factory_generation_invalid`。
已去掉 Provider-facing `branches`，并做 bounded repair / 拒绝静默 V1。
验收：CASE A Start→Model→Output；CASE B 三个 Model；CASE C
Start→Model→HumanApproval→Model→Output（风险项检查不能映射
`output.not_empty`，保持 truthful）；CASE E 真实 `condition` intent。
裸 CASE C 文本可能被 resolver 判成 `create_kind=workflow`；加上
「做一个 Agent」后进入 SemanticPlan。未 Confirm / Apply。

**Typed I/O + Artifact Runtime = released**（本 checkpoint commit）。

Canonical contract：`TypedField` 兼容旧 compact `text: string`；binary 值为
Project-scoped `ArtifactRef`，复用 `objects/sha256/<digest>`。Runtime Model
modalities 与 Builder `ProviderCapabilityProfile` 分开。当前 Moonshot
`kimi-k3` 以及其它用户绑定 Runtime 模型：`image_input=supported`。仅已知
纯文本 Moonshot 模型（`kimi-k2`、`moonshot-v1-8k`、`moonshot-v1-32k`）保持
`image_input=unsupported`。PDF/document/Office/file 抽取纯文本进 prompt，
bytes 不进 Run JSON。audio/video adapter 仍未启用。缺 pdf_parser /
pdf_renderer / image_generation Tool 保持 Compiler 侧 truthful
`missing_capability`。Studio Test、Workflow Test、Builder Test、Run Detail
共用 `RuntimeInputForm` / `RuntimeOutputView`。独立 Agent Playground 与
Workflow Builder Compiler **尚未实现，也不是当前主任务**。 Builder
Workspace/Test 位于每次 Builder operation 对应的 Conversation 历史中，不是
固定右侧栏。

Release gate（2026-09-22，真实 `.env`，非 temp DB / 非 fake provider）：

```text
backend：env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check → 675 passed
Ruff format：312 files；Ruff check passed；mypy 184 files；git diff --check clean
Desktop vitest：53 files / 430 passed；Community vitest：3 files / 15 passed
Desktop/Community typecheck passed
Desktop production build：2025 modules，1.40s
Community production build：1722 modules，656ms
```

Live Local API（dirty SHA `8bef91c-typed-io-dirty`，head `local_0025_project_artifacts`）：
text Agent Run 得到 translation；string+number → object 保留 summary/score/report；
image Run 前 422 `runtime_model_incompatible`；Artifact upload/metadata/download
Project 隔离、MIME mismatch、超限拒绝；PDF bytes 不进入 Run JSON。
Authenticated Desktop UI 仍需登录，仓库内无 Playwright；Chrome + playwright-core
停在 `#/login`。Compiler 对 image/pdf 的 typed semantics 由 unit tests 覆盖。
Moonshot Builder 在本轮 Runtime 验收后返回 `factory_rate_limited`（HTTP 429）。

## 6. 下一步

当前切片是 **5174 Product Boundary Alignment + Showcase V1**，不是新的 Community 或 Registry 开发：

1. 将 5174 固定为匿名产品 Showcase；核心页面不依赖 8772。
2. 由 5173 保留 Community 发现、发布、收藏与导入工作流；8772 保留 Registry 服务。
3. 诚实展示源码构建入口与发行状态；没有公开且验证过的安装包时不提供假的下载按钮。
4. 用 5174 focused tests、typecheck/build、全仓门禁和手工浏览器检查收口，并同步产品边界与当前状态文档。

完成本切片后停止，不开始 Community 多资源分享、Following/Feed、Production Community、Desktop Distribution、Builder Provider 复验或 Custom Component lifecycle 验收；这些保留为后续独立排序。

## 7. 仍不能宣称完成

- Knowledge 工作台已有一条隔离浏览器闭环证据；其余页面仍没有浏览器 E2E
- 没有 PostgreSQL + 对象存储演练，就不能宣称 Community production ready
- 没有真实外部 Provider，就不能宣称 Runtime 已在生产网络下验证
- Builder 不能一次修改多个对象，也不是全 Project 操作入口
- Builder Phase 2 仍未作为独立 Git 发布标签。Durable Conversation、
  Semantic Plan Compiler V1、Interaction Model V2、ProviderCapabilityProfile、
  Harness Receipt 与 Slice 4 Test Run 已包含在 `8f71a1e`。Agent Graph
  Compiler V2 已发布为 `8bef91c`。Typed I/O + Artifact Runtime 已发布为
  `5f8e8a8`。独立 Playground 不是当前主任务。Agent Composition V1 已包含在
  当前 HEAD `0ad7a3e`；这不代表真实 Builder Provider 在 Branch Semantics 修复后已复验成功。
- 手写 PDF/document/file input Agent 的 Runtime readiness 不会自动变成
  `pdf_parser` missing；缺专用 parser Tool 的 truthful 点在 Compiler。
  Runtime 抽取有界纯文本写入 prompt，不把 PDF/Office bytes、host path 或
  `artifact://` 写入 Run JSON。audio/video adapter 仍未启用；文件夹不是
  ArtifactRef 种类
- 旧 Factory session 目前只恢复最新 canvas，不是完整 conversation/workbench
- Community directory 已改为真实 API；生产 PostgreSQL/S3 备份恢复演练仍未完成

## 8. 提交规则

获得明确提交要求后：

1. 查看 `git status`、`git diff` 和最近提交
2. 只暂存当前模块文件；不暂存 `.env`、凭据、`.backboard/sessions`、`.backboard/settings.json`
3. 在专用 Conda 环境跑对应验收
4. 记录精确 commit SHA
5. 重启受影响服务并用 `/api/v1/health` 核 SHA
6. 历史交接中的授权不是永久许可

## 9. 技术决策

- `PROJECT_DESIGN.md` 是产品和工程权威；本文只维护事实状态
- Local 与 Community 独立部署；Community 不执行下载的 Agent 或插件
- Agent 与 Workflow 平级；Workflow 只调用固定 immutable Agent version
- Catalog 与 Project Resource Library 分离；MCP 是 Tool discovery，不是独立产品层
- Project 文件是用户可检查的 source；运行、聊天、账号、秘密和缓存留在应用数据区
- Knowledge 绑定固定 source hash；内容变化必须显式重建索引并重新绑定
- 先补可验收闭环，再做视觉扩展、推荐算法或资源数量扩张

## 10. Agent Composition release acceptance update（2026-09-22）

- 用户明确授权的唯一 Builder 合成请求已发送一次；Provider 没有返回 429。Provider
  生成的 Proposal 含一个 `Condition` 和两个 `HumanApproval` 节点，但 Condition 仅判断
  request 是否为空，两个审批与两个 Transform 又被串成一条路径；输出仅为通用 `result`
  对象，Transform 返回原始 request，没有满足 urgent/routine 分支语义或
  `{priority, summary}` 输出契约。Proposal Note 对分支与输出的描述和实际图不一致。
  这是语义降级，未 Confirm / Apply；无 Custom Component、外部 Tool 或权限提案。没有为
  验收再次调用 Provider，也没有把 Provider 原始响应写入文档。
- Builder Provider receipts 显示请求自动携带 Project/Agent、Workflow、Knowledge
  metadata、Project resource bindings、Catalog capabilities、Project file metadata、
  Project config；Interview/Semantic Plan 阶段还含当前对话消息。receipts 标记未包含
  Knowledge/file 正文、credentials、secrets、真实 Runtime events、隐藏推理和原始
  Provider response bodies。此项是对自动上下文范围的披露，不把它误写成完全零上下文请求。
- 用户截图中的 Custom Components `Not Found` 已复核：运行中的 `127.0.0.1:8771` health
  为 `build_sha=5f8e8a8`、DB revision `local_0025_project_artifacts`，组件列表 endpoint
  返回 HTTP 404；当前 dirty 源码已注册相同 endpoint。隔离 TestClient + 临时 SQLite 的
  生命周期集成测试通过，证明当前源代码路由正常，但不能替代 live sidecar/browser 证据。
- Custom Components 面板在列表 API 出错时原先仍允许编辑/保存，造成“表单可用但请求
  必然失败”的误导。现已将加载/错误期间的编辑、保存、校验、发布和生命周期操作锁定；
  404 显示服务/API 不可用提示，成功重试后恢复。Focused Desktop panel tests **3 passed**，
  对应 Backend isolated lifecycle integration test **1 passed**，Desktop typecheck passed。
- `8771` 未在本 checkpoint 重启：发布流程要求先有合理完成的 Slice/acceptance 与提交，
  而 Builder semantic acceptance 尚未通过。正式服务重启、live Custom Components 浏览器
  acceptance、Condition/Approval/Component Proposal 完整浏览器路径、release commit/push
  仍未完成；不得将上述隔离测试称为 Browser E2E 或发布验收通过。

## 11. Local API restart + Custom Components read/UI smoke（2026-09-22）

- 用户单独授权后，只重启 `8771`。从仓库根目录使用 Conda Python、显式指向当前
  `backend/src`，启动命令为：
  在仓库根目录的 Conda 环境执行 `env PYTHONPATH=backend/src VEYRA_BUILD_SHA=5f8e8a8-dirty python -m uvicorn veyra_agent_platform.local.app:app --host 127.0.0.1 --port 8771`。
  应用按正常启动流程读取现有 host config；没有查看、打印或改写 `.env` 值，也没有调用 Provider。
- 重启 health：`service=local`、`build_sha=5f8e8a8-dirty`、
  `database_revision=local_0026_builder_semantic_plan`、`database_ready=true`。进程打开的是
  已有 user-data Local SQLite，而非临时 DB； Project root 由正常 Local config 提供。
  startup 将 schema 从 `local_0025_project_artifacts` 升级到 `local_0026_builder_semantic_plan`；
  此 migration 仅给 `factory_sessions` 加一个 nullable `semantic_plan_json` 列，迁移 helper
  按设计保留 pre-migration SQLite copy，没有修改 Project 资源/文件记录。
- 当前 test Project 的只读 `GET /api/v1/projects/{project_id}/custom-components` 返回
  HTTP **200**、Project identity 匹配、`components=[]`。未创建、保存、校验、发布或删除
  Custom Component；没有真实 Project 资源 mutation。
- 手工浏览器复核：重启前实际错误态是 404 + “组件列表不可用”，新建和编辑/保存控件被锁；
  重启后错误提示消失，显示“还没有自定义组件”，New Component、草稿表单和 typed I/O
  JSON 可编辑；实现类型可切换至 `transform`，实现模板随之更新。随后刷新页面清除未保存
  表单状态，再次确认 API 组件数仍为 0。此为真实页面手工 smoke，不是自动化 E2E。
- 没有识别到可确认隔离的既有 Project，因此未做 Draft → Validate → Publish lifecycle
  浏览器 smoke。空白新建表单的 Publish 控件现已 disabled；保存/发布路径不在真实 test
  Project 上执行。
- 本次只重启 `8771`；`5173`、`5174`、`8772` 未重启。当前 `5173`、`5174` HTTP 200；
  `8772` health ready、build SHA 仍为 `5f8e8a8`。Builder Proposal semantic acceptance
  仍 failed；未 Confirm/Apply、未重新调用 Provider，Agent Composition V1 仍不可标记完成。

## 12. Builder Branch Semantics & Output Wiring hardening（2026-09-23）

- 根因已定位在 `AgentSemanticPlan -> semantic_compiler -> canonical graph`：旧
  `step_intents` 只有 `depends_on`，没有通用的 Condition branch declaration、branch-local
  identity 或 deterministic multi-output mapping；Compiler 因而按拓扑顺序把 sibling branch
  steps 线性化，Transform 又只保留第一个 output field。
- SemanticPlan 现支持最小通用 branch contract：Condition 必须声明两个 `{key,label}`
  semantic branches；branch-local step 声明 `branch_condition` + `branch_key`，依赖只能
  留在自己的 branch；Transform 可声明 `output_mapping`，目标必须是 declared output field，
  值只能是 deterministic literal 或 `{{input_field}}` 引用。Provider 不生成 node/edge/port
  IDs；Compiler 将两个 semantic branch 按声明顺序确定性投影为 Runtime `true`/`false`，并
  在 `ui.branch_labels` / Note 中保留业务 labels。当前 V1 Runtime contract 仍是双分支；
  多于两个分支会 fail closed，不静默折叠。
- Compiler 现在生成真实 DAG：Condition 分别连接 branch-local roots；每条 branch 的
  Approval 只连接本 branch 的 downstream；branch Transform 映射全部 declared outputs，
  多 branch 可汇入同一个 Output；共享 successor 只在真实依赖存在时合并。Sibling branch
  不再被 ordered steps 串联。Note 由 compiled graph branch truth 生成，不再直接复述 Provider
  描述；branch labels 同时可投影为 Canvas edge label。
- SemanticPlan repair/prompt/MFJS projection 已同步扩展并保留 `branches`、`branch_condition`、
  `branch_key`、`output_mapping`；非 Condition 的 malformed `branches` 只会带诊断地丢弃，
  Condition branch cardinality/identity 错误会拒绝；semantic compile topology error 返回
  `semantic_compile_failed` 路径，不能 ready/success。没有真实 Provider 重试或新 Provider 调用。
- Runtime deterministic integration fixture 已覆盖两条任意命名 branch：True 只进入 Alpha
  Approval/Transform，False 只进入 Beta Approval/Transform；未选 branch 没有 `node.started`，
  同一 Output 保留两个 typed fields。Desktop overlay 既有 projection tests 覆盖 canonical
  Condition edge、unselected idle、Approval waiting 和 approved successor。
- 修复 Custom Components 空白表单 Publish 状态：没有 persisted `component_id`、草稿尚未
  Validate、或 API error 时 Publish disabled；Save Draft 后仍需 Validate 成功才可 Publish。
  新增/更新草稿会清除 validation gate。没有新增 migration；SemanticPlan/Blueprint/Source
  contract 是同一 schema version 的 additive extension。
- Focused evidence：Backend semantic/compiler/factory/runtime/contracts **169 passed**；
  Desktop focused **36 passed**；Desktop typecheck passed；Ruff format/check passed；生产
  touched modules mypy **8 files, no issues**。首次对既有测试文件直接跑 mypy 暴露仓库原有
  test typing debt，未将其混入生产模块结果。未运行 full `make check`，未重启任何服务，未
  调用真实 Builder Provider，未 Confirm/Apply，未修改真实 Project 数据。

## 13. Live 8771 deterministic browser acceptance（2026-09-23）

- 按用户授权只重启 `8771`，命令使用当前 working tree 的 `backend/src`、真实 Local DB
  和正常 Project root：`VEYRA_BUILD_SHA=5f8e8a8-dirty`。health HTTP **200**，
  `database_ready=true`，revision `local_0026_builder_semantic_plan`。没有读取/打印 `.env`
  secret；5173、5174、8772 未重启，未调用 Builder Provider。
- 在真实 Local DB 创建了隔离 Project `Browser Branch Fixture - 2026-09-23`
  (`project_id=01a0ca52-c8d1-7582-a773-7b4f3d6bf2c8`) 和 deterministic Agent
  (`agent_id=01a0ca52-c8d1-763d-876f-9fd2c7e8514f`)。fixture 只使用 `mode=alpha|beta`，
  不包含旧的 urgent/routine 语义；没有修改既有 `test` Project 或已有 Agent。该隔离
  Project 和两个验收 Run 保留，未执行删除操作。
- Manual browser CASE A Alpha：Run `01a0ca53-a2bf-7b24-957a-86dcd8c8a0f8` 先到
  `approval_alpha` waiting；`approval_beta` 未开始。Approve 后同一 Run 继续，
  `transform_alpha`、Output completed，`transform_beta` 未开始；Run Detail 显示
  `{branch: "alpha", summary: "Alpha summary for alpha"}`。
- Manual browser CASE B Beta：Run `01a0ca54-c517-787b-bd8d-d4034403f38c` 先到
  `approval_beta` waiting；`approval_alpha` 未开始。Approve 后同一 Run 继续，
  `transform_beta`、Output completed，`transform_alpha` 未开始；Run Detail 显示
  `{branch: "beta", summary: "Beta summary for beta"}`。
- Execution Overlay 手工确认：running/waiting/completed 节点、选中 branch edge、未选 branch
  edge 与 Runtime events 一致；两次截图均未出现两条 branch 同时高亮。Alpha/Beta 完成后
  刷新 `design?run_id=...`，对应 immutable Run 状态和节点状态恢复。事件日志显示同一 Run
  的 `approval.requested/resolved`、branch Transform 和 Output completion。
- Canvas edge label 实际显示 `Alpha` / `Beta`；Note 实际描述两条 branch 各自经过 Approval
  与 Transform 后进入双字段 Output，与 graph truth 一致。以上是 manual browser acceptance，
  不是 jsdom/unit 或 integration test。
- 同一隔离 Project Resource Library 空白组件页手工确认：空白新建表单中 Save Draft enabled，
  Validate disabled，Publish disabled；未输入、未保存、未校验、未发布任何 Component。
- 这是 live API + fixture/browser 证据，不是完整 release acceptance：真实 Provider、正式
  test Project 不变、Custom Component lifecycle browser smoke、full gate、commit/push 仍未做。

## Community Sharing UI and navigation refresh（2026-09-23，本地未发布）

- Community 页面改为四个水平意图入口：Discover / Published / Starred / Following。Desktop 继续
  使用 Veyra 全局侧栏；独立 Community Web 也采用同一组顶部导航。Discover 读取真实 Agent Registry，
  搜索走 API，排序只用真实发布时间、Star 数和 Review 评分；没有伪造 Featured、下载量或导入量。
- Published 与 Starred 新增认证 API：`GET /api/v1/registry/mine/agents`、
  `GET /api/v1/registry/starred`。它们复用现有 immutable version 与 version-bound Star 表；
  Published 显示 published/quarantined/rejected 真实状态，不显示不存在的 Community draft。
- Following 导航和页面可见，但明确显示未开放：当前服务还没有 creator-follow 关系或 release feed。
  未添加示例创作者、假动态或伪收藏。Discover 当前仍只展示 Agent；现有 Plugin Pack 发布仍在 Publish 区，
  但 Plugin Pack 浏览/导入详情、Workflow/Component/独立 Tool/Skill 市场都未伪装成已实现。
- Agent 发布在本机先生成规范化 package preview，再由用户显式确认才上传；host Secret 引用和机器路径
  在 UI 禁止，并由 Community 后端二次硬拒绝。导入分析带目标 Project 的只读依赖报告；确认前不改 Project，
  确认时重算并检查 source hash 与依赖快照，漂移返回 conflict。成功后只创建新的本地 Agent Draft，不运行、不授权、不安装依赖。
- 手工浏览器检查了 5174 Community Discover 的真实 API 空目录与 Following 未开放状态；当前公开目录实际为
  0 个版本。该检查不等于自动浏览器 E2E，也没有登录真实账户、Star、Publish 或 Import 用户资源。
- 全量门禁：Conda `make check`：**703 passed**，Ruff format/check、dependency lock、mypy（187 source files）通过；
  Web Desktop **471 passed**、Community **18 passed**，两端 typecheck 与 production build 通过。
  Desktop build 仍有大 chunk 提示，Alembic 测试有既有 `path_separator` deprecation warning。
- 没有重启服务：5173/5174 当前由本地 Vite 工作树热更新；8771/8772 health 仍为 200、build
  `0ad7a3e`，Local revision `local_0026_builder_semantic_plan`、Community revision
  `community_0008_plugin_registry`。因此 Published/Starred API 与新的目标 Project 导入分析尚未进入 live API，
  需要单独授权重启对应服务后才能做 live browser acceptance。
- 未 stage、commit 或 push。原有 `shell.tsx`、`shell.css`、`app.test.tsx`、scroll-driven UI 修改、
  `.backboard/sessions/`、`.backboard/settings.json` 与 `$DB` 均保留。

## Community Sharing V1 live API reload + read-only browser acceptance（2026-09-23，历史 checkpoint）

- 只重启 Local API `8771` 与 Community API `8772`；没有重启 `5173` / `5174`。使用项目根目录
  的专用 Conda Python 3.11.15、当前 `backend/src` 和正常应用配置；只显式设置 dirty build marker，
  未设置 temp DB、E2E Project root、fake provider 或 loopback provider。Community 按仓库已有
  `python -m dotenv -f .env run -- env ... uvicorn` 启动；没有输出、查看或改写 `.env` secret。
- 两个 API health 均 HTTP 200、`database_ready=true`、`schema_version=health.v1`，build marker
  均为 `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`；Local revision 为
  `local_0026_builder_semantic_plan`，Community revision 为 `community_0008_plugin_registry`。
  OpenAPI 3.1.0 已加载 Local Agent import analyze/read/apply 和 Project Agent import；Community
  已加载真实 publish/list/detail/version/download/star/unstar/moderation 路由，以及认证
  `GET /api/v1/registry/mine/agents` 和 `GET /api/v1/registry/starred`。
- 只读 API 检查：匿名公开 Agent Registry 返回 HTTP 200、0 releases；Published 与 Starred
  endpoints 返回 HTTP 401 `authentication_required`。没有创建、修改或删除账号、release、Star、
  Project、Agent、Run 或 Component，也没有生成假目录数据。
- Manual browser acceptance（独立 Community Web，非 Playwright/jsdom）：5174 Discover 显示真实
  `0 releases` / 空态；搜索输入可用；Recently published、Most starred、Top rated 可切换。
  Published 与 Starred 显示真实 Sign in 边界；Following 显示 `Creator following is not available yet`、
  无 Following API，并明确 Star 是收藏 immutable release、Following 是订阅 creator。浅色与深色页面
  均未见明显破版。Desktop `5173/#/community/published` 因隔离浏览器未登录而按设计跳转 Login。
  两个 Vite 服务保持 HTTP 200，未重启。以上是手工浏览器状态检查，不是自动化 E2E。
- 真实 Publish / Published authenticated listing / Star / Unstar / Agent detail / Import Preview、
  Preview 零变更复核、Import as Draft 与 Studio 打开尚未完成：认证注册会请求投递邮箱验证码；本轮没有
  指定的隔离测试账号或邮箱，因此没有触发验证码投递或创建账号，也没有借用用户账号。当前公开目录
  仍为 0 releases；Community Sharing V1 release acceptance 被隔离账号/邮箱授权阻塞，不能标记 complete。
- Conda 后端完整 `make check`：703 passed；Ruff format/check、依赖锁检查、mypy 187 source files
  通过。Web `npm test`：Desktop 471 passed、Community 18 passed；两端 typecheck/build 通过。Desktop
  build 仍有既有 >500 KB chunk warning；pytest 保留 Alembic `path_separator` deprecation warnings。
  `git diff --check` clean。
- Git HEAD 仍为 `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；无 staged files；未 commit/push。
  用户独立 shell/sidebar-scroll/UI 改动、`.backboard/`、`$DB` 均保留。

## 5174 Product Boundary Alignment + Showcase V1（2026-09-23）

- 当前产品职责：5173 Desktop 是主要工作台与 Community 交互面；8771 是 Local API；8772 是独立账号/immutable Registry 服务；5174 是匿名 Public Showcase。Registry 是服务能力，不是 5174 的网站身份。历史上 `web/apps/community` 临时发展成独立 Registry UI，本 Slice 将入口改为 Showcase；目录/package 重命名与旧页面 dead-code cleanup deferred。
- 5174 展示 Product、How it works、Local-first/Safety、Share、Getting Started/Docs、Download/Build；不显示 Published/Starred/Following、Account、Publish、Import 管理工作流。
- 5174 的 main entry 不导入 Community API/Auth/Registry 页面；Vite `5174` 不代理 `/api` 到 `8772`。`ShowcaseApp` 首屏是静态产品内容，`8772` 离线仍 HTTP 200；unit tests 断言首屏没有 `fetch`，旧管理 hash 刷新后转到 `#home`。
- 内容边界：产品示意明确标记非真实 Run；没有假指标、客户或 Community 资源。没有可验证的公开 DMG/下载 URL，页面明确提示暂无公开安装包并链接到真实仓库构建文档；GitHub 文档链接可能需要仓库权限。无数据库 migration、无 Registry/API/schema/data 改动、无 Builder Provider 调用、无 Project 数据 mutation。
- Manual browser acceptance（Chrome 真实 5174；8772 未监听）：首页/全部 section 可见；Legacy `#/community/published` 直接打开并刷新后归一到 `#home`，没有管理 UI；中文/英文、light/dark 可切换；200% 浏览器缩放后响应式 Header 显示折叠菜单。实际截图确认展示示意有明确非实时标识。用户接管 Chrome 后未继续点击窄屏菜单；该菜单状态由 Showcase unit test 覆盖，未把这项写成 mobile-device E2E。
- Focused/Full validation：`npm run test --workspace=@veyra/community` **22 passed**；全 Web `npm test` Desktop **472 passed**、Community **22 passed**；两端 typecheck/build 通过。Desktop build 有既有约 1.16 MB chunk warning；Community Showcase JS bundle **230.93 KB**。Conda `make check` **703 passed**，Ruff format/check、dependency/lock checks、mypy 187 files 通过；pytest 有既有 Alembic `path_separator` deprecation warnings。
- 新增 ADR `0006-public-showcase-and-community-boundary.md`。README、AI brief、PROJECT_DESIGN、DEVELOPMENT、HANDOFF/GPT historical note 已同步四服务职责。no stage/commit/push；`git diff --check` clean（以本 checkpoint 最终核验为准）。
- Browser acceptance 时 8772 确实离线，5174 root 仍 HTTP 200；旧 Registry hash 刷新后没有管理 UI。完成离线验收后按用户先前选择恢复四服务：5173/5174 HTTP 200；8771/8772 health HTTP 200、`database_ready=true`，Local `local_0026_builder_semantic_plan`、Community `community_0008_plugin_registry`，均为 `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`。启动前数据库已在 schema head，因此无 migration。
- 工作区仍在 `codex/agent-platform` / HEAD `0ad7a3e0b2a11ccf9186f23dab40628375509c73`，本 Slice 未暂存/提交/推送；既有 Community Sharing、shell/sidebar/scroll UI、`.backboard` 状态和 `$DB` 保持。

## Builder Real Provider Re-Acceptance + Custom Component isolated lifecycle（2026-09-24）

- Builder 使用隔离 Project `Veyra Builder Acceptance 20260923-1530Z`。仅提交一条合成用户级请求；
  Provider 身份为 Moonshot `kimi-k3`，意图解析与一次 Semantic Plan + 两次有界 repair 的 receipts
  均为成功响应（`json_object` / strict JSON Schema，MFJS）。最终 Builder operation 失败于
  `semantic_generation`：`factory_generation_invalid`，Semantic Plan 在三次产品内尝试后仍无效；
  不是 429。没有 reviewable Proposal / proposal_id，因此没有可审的实际 graph；未点 Retry、未
  Confirm/Apply、未创建组件、未 Run。没有保存 raw Provider response、secret 或日志。
- Custom Component 浏览器验收使用隔离 Project `Veyra Component Acceptance 20260923-1545Z`。
  空表单 Save Draft 可用、Validate/Publish disabled；保存 Draft 后 Validate enabled；Validate 返回
  `ready` 后 Publish 创建不可变 `1.0.0`。随后编辑并保存新 Draft，旧版 description 与 SHA-256
  `e7de5249088a601226431f3e8946ad22a6b226b4226717e8f0996200fd67a2bc` 未改变。
- Resource Library 显示绑定的 `Acceptance Echo`；Studio Palette 在存在未发布 Draft 时只显示已发布
  `1.0.0` 与同一哈希。隔离 Agent Draft 的 `CustomComponent` node 保存成功：`uses` 精确固定到
  `01a0cef2-ec07-7379-b55c-8eb581150d0e@1.0.0`，lock 与 Project 绑定哈希一致，输入/输出映射为
  `text <- request`、`result -> result`，Agent 没有额外 Tool 权限。Canvas、Form、Source 的引用、
  hash 与映射一致；Canvas 无 blocking graph diagnostics（Validate & Commit 按钮未点击）。Local API
  validate 为 `valid=true`、component dependency `ready`。该 `runtime_ready` 是 dependency scope，
  不是一次实际 Run；未执行 Run 或模型调用。
- 浏览器复核为 **manual browser acceptance**，不是 Playwright/jsdom E2E。确定性后端 focused tests
  **37 passed**；Ruff、format、touched production modules mypy 通过（后端全仓与 Web 全量门禁待本轮
  后续运行）。发现并修正了 `CustomComponent.uses` 被 Draft 保存/依赖检查误按 Tool manifest binding
  查找的问题；现在分别核对 Project-owned published component reference/hash 与 Tool manifest pins。
- 仅重启 `8771` 使修复进入 live API；health HTTP 200，`database_ready=true`，build
  `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`，DB revision `local_0026_builder_semantic_plan`。
  `5173` / `5174` / `8772` 未重启；检查仍分别为 HTTP 200 / HTTP 200 / health 200 ready。无 migration、
  temp DB、E2E root 或 fake provider。两 Projects 都是本轮验收 fixture；用户既有 Project/Agent 未改。
- 未 stage、commit 或 push。Slice 仍未 complete：Builder real-provider semantic acceptance failed；
  两个隔离验收 Project 与组件/Agent fixture 保留以供复核。最终门禁：Conda `make check` **704 passed**，
  Ruff format/check、dependency lock、mypy **187 source files** 通过；Web Desktop **472 passed**、
  Community **22 passed**，两端 typecheck/build 通过。保留 Alembic `path_separator` warnings、jsdom
  Canvas `getContext` stderr 和 Desktop >500 KB chunk warning；`git diff --check` clean。

## Builder Semantic Generation Failure RCA + Offline Hardening（2026-09-24）

- 本 Slice 没有第二次真实 Provider 请求、服务重启、Run、Apply、migration、stage、commit 或 push。
  继续使用 `codex/agent-platform` / HEAD `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；工作树原先
  已含 Community/Showcase、Sidebar/scroll、Custom Component 与 Branch Semantics 等未提交变更，均保留。
- 只读 Builder identity：Project `01a0cee5-90fb-78f4-99ab-e42e9a6365c9`；conversation
  `01a0ceeb-5dfb-7f5a-9944-2320254d181c`；operation
  `01a0ceeb-5dfb-71b8-a4f7-06a1542144f6`；Factory session
  `01a0ceeb-cabd-7e1e-bc58-df67cdeb51fc`。没有修改该 Project/Agent 或清理 acceptance 数据。
- 原 turn 共 5 个 receipt：`resolve_intent`、`interview`、`semantic_plan`、两次
  `semantic_plan_repair` 均记录成功响应；后三次都使用 `strict_json_schema` / `mfjs`。
  structured-response 请求成功；应用代码在 `json.loads` 后走 Python SemanticPlan contract 与 semantic
  checks，并没有另跑 Draft 2020-12 JSON Schema response validator。事件进入 `semantic_plan.completed`
  与 `builder.capabilities.started`，证明三次均越过 JSON parse、Python contract 和 branch/obligation
  validation，之后才在 compiler 失败。Receipt 没保存初始/repair 的完整内容，也没有记录可重取的 HTTP
  数字状态码；本记录不补造这些内容。
- Attempt 1（`semantic_plan`）：JSON/contract/branch validation pass；Compiler 报
  `semantic_compile_failed`，Transform `normalize_result` 引用未声明输入 `advice_priority`。
  Repair 1（`semantic_plan_repair`）：同层失败，`normalize_result` 引用改成了仍未声明的
  `urgent_priority`。Repair 2：同层失败，`normalize_urgent` 又引用 `advice_priority`。三次 Provider
  调用都成功，失败不是 429/auth/network，也不是 MFJS 400；最终是
  `factory_generation_invalid` / `semantic_generation`，无 `proposal_id`、canonical Blueprint/Proposal、
  Agent Draft、Run 或 Component。
- 数据库只保留了最终 attempt 的 `semantic_plan_json`。其安全结构为：Agent input `request:string`；
  top-level outputs `priority:string`、`summary:string`；Condition 声明两个分支；每支有 branch-local
  HumanApproval 与 Model，再各有 Transform 把 `{{advice_priority}}` / `{{advice_summary}}` 映射到顶层
  输出。分支 identity、审批 placement 与 dependency contract 都通过解析；失败点是 Transform 借用了
  Provider 定义的 step-local Model 字段，而 compiler/runtime 的变量域只有 Agent 顶层 inputs/outputs。
  该错误不是 outputs 名称不存在，而是 mapping source 不在 Agent input contract。
- 历史 Repair prompt 的精确字符串未持久化。按当时实现，它包括原 compiler diagnostic 和截断至 1200
  字符的 `step_intents` schema 片段；通用说明只说 mapping 可引用 `{{input_field}}`，没有列出当前允许的
  Agent input/output 名称，也没说 step `inputs/outputs` 不代表普通 Model→Transform dataflow。诊断文本虽含
  未知字段名，但没有 machine `code/path/expected/allowed_inputs`。Provider 因此把 source token 从
  `advice_priority` 改成 `urgent_priority` 再改回；receipt 不足以比较其它原始字段变化。
- 根因分类：首个失败层是 **Compiler boundary**（不是 JSON、MFJS projection 或 branch validator）。
  辅因是 SemanticPlan 允许普通 step 夹带 `inputs/outputs`，但未定义 inter-step 数据流；prompt/schema
  结构容易让 Provider 把它误用为数据传递；旧 repair 缺少字段白名单与可修复操作说明。另发现现有 contract
  有一处相反边界过窄：可复用 Component planner 明确支持 reusable `model` / `transform` / `capability`，
  因此保留这些 kind 的 `reusable_capability=true` typed I/O；普通非 reusable step I/O 才拒绝。
- MFJS 排除结果：原 receipts 为 `mfjs` profile + strict JSON Schema；branch、nested branch item、
  branch references、outputs、depends_on、output_mapping 与 nested typed fields 均保留在 projection。
  失败前 canonical schema hash 与当时 receipt 的 schema hash 一致。没有证据支持 MFJS 删字段/压扁 array
  是根因；没有强制退回 `json_object`。本轮 schema description 改后 hash 自然会变化，历史 hash 不用来
  表示当前工作树 hash。
- 离线修复：普通 Transform 只能从 Agent inputs/literals 映射到声明 outputs；step `inputs/outputs`
  仅属于 reusable capability contract。Model prompt明确列出完整顶层 output contract，包含首字段与类型。
  Repair 将收到精确 Agent field names；compiler 错误包含 machine `code`、`path`、expected 与 allowed
  input。只有合法的 input/literal Transform 才形成“必须保留”的 transform obligation；非法的 mapping-only
  step 可被移除并由其 Model 直接生成顶层字段，不能因此丢掉真实用户职责。Sibling branches 仍不能串联。
- 脱敏回归 fixture：[`agent-semantic-plan-real-provider-failure.json`](../contracts/fixtures/invalid/agent-semantic-plan-real-provider-failure.json)。它来自数据库中唯一保存的最终 plan shape，去掉自由文本与身份信息；初始响应和 repair 1 的 raw structure 不可用，因此没有伪称 fixture 覆盖那些原文。测试另派生一个移除非法 step-local I/O 的形状，以重现原 compiler unknown-input 故障。
- 自动回归覆盖：真实失败 fixture 的 contract/compiler 两级诊断；MFJS provider-visible schema nested branch/output 字段；scripted Builder turn `invalid → invalid → valid` 并进入未 Apply 的 reviewable neutral `valid/invalid` graph；repair exhaustion 三次后仍 `factory_generation_invalid` 且无 Proposal/Agent mutation；同 branch dependency 接受、cross-sibling reject；两个与三个顶层 output names 保留；branch-local Approval 和 truthful Note；reusable Transform Component proposal continuation 与 Custom Component focused regression。
- Offline graph 摘要：`Start → Condition`；`true → Approval(valid) → Model(valid) → Output`；
  `false → Approval(invalid) → Model(invalid) → Output`。两支各自输出 `{status, summary}`；Approval
  不串联；Note/edge label 来自成功编译图的 `Valid` / `Invalid`。失败 plan 的 compiler result 没有 Blueprint，
  所以不会产出误导 Note。该测试是 scripted integration，不是真实 Provider 验收或 Browser E2E。
- 本 Slice 修改/增加：SemanticPlan contract/parser、Builder create prompt 与 model output prompt、
  repair diagnostics/obligation filter、semantic compiler structured path diagnostic、canonical schema，
  脱敏 fixture 与 hardening/compiler/conversation regression tests；PROJECT_DESIGN 修正过期 branch contract
  描述。本轮没有 Community/Showcase/API/UI 功能变更。
- Focused backend: **156 passed**，覆盖 SemanticPlan/MFJS/Factory/Builder/Compiler/Proposal/Custom Component。
  Full Conda `env -u PYTHONPATH -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`: **713 passed**；Ruff
  format/check、dependency lock、mypy **187 source files** passed。Web `npm test`: Desktop **472 passed**、
  Community **22 passed**；Desktop/Community typecheck 与 production build 均通过。保留已有 Alembic
  `path_separator` deprecation、jsdom Canvas `getContext` stderr、Desktop >500 KB chunk warning。
  `git diff --check` clean；没有新 migration，也没有真实 Provider call。
- 结论：这是 Offline Hardening 成功，不代表 Builder real-provider acceptance 通过。下一步仍需单独授权
  **Builder Real Provider Re-Acceptance #2**；在那之前不称 Builder accepted / V1 complete，不重启服务，不发布。

## Builder Real Provider Re-Acceptance #2（2026-09-24，本次结果 FAIL）

- 开始时仍为 `codex/agent-platform` / HEAD `0ad7a3e0b2a11ccf9186f23dab40628375509c73`，working tree dirty、无 staged files。旧失败 Conversation `01a0ceeb-5dfb-7f5a-9944-2320254d181c`、Operation `01a0ceeb-5dfb-71b8-a4f7-06a1542144f6`、Factory session `01a0ceeb-cabd-7e1e-bc58-df67cdeb51fc` 未 retry、未修改；原 Project 保留。
- 新一轮复用隔离 Project `01a0cee5-90fb-78f4-99ab-e42e9a6365c9`，开始前 Agent=0、Workflow=0、Custom Component=0、Project-owned resource binding=0、Runtime Run=0、Workflow Run=0；仅有先前那条失败 Builder Conversation。Project 未新建，也未改动。
- 仅发送一次获准的真实 Builder turn；新 Conversation `01a0d1a6-3580-71d9-84d4-550407c34ef7`、Operation `01a0d1a6-3580-721b-b709-57c59c0a17e3`、Factory session `01a0d1a6-72d7-713a-b749-ca0df9c9eaf7`。Local API HTTP **200**；Intent/Interview/Semantic Plan 三条 receipts 均 success；唯一 Semantic Plan attempt=1、repair=0，`strict_json_schema` / `mfjs`；没有额外 Provider probe 或第二次 Builder turn。
- Provider 生成了 review 状态 Blueprint，operation=`waiting`、Factory session=`review` / `ready=true`，并发出 `builder.proposal.ready`。但 operation 的 `proposal_id=null`，事件 facts 也没有 `proposal_id`；只有 Factory session 中的 Blueprint candidate，不是本验收要求的带 ID canonical Proposal。因此第一个 release success gate 未达到，不能标记 PASS。
- 最终 Semantic Plan（从本机 DB 只读并输出脱敏结构）：input `request:string`；outputs `priority:string`、`summary:string`；Condition `classify_priority` 有 `urgent/routine` 两 branch；每支各有 branch-local HumanApproval 与 Model；没有 step-local intermediate I/O、没有 external capability。Approval 拓扑正确：`Condition true → approve_urgent → advise_urgent`，`false → approve_routine → advise_routine`；sibling branches 不互相依赖；不是线性假分支，也没有退回单 Model。
- 新发现的确定性编译问题：Semantic Plan 的 Condition `purpose` 是自然语言“按 request 内容分类 urgent/routine”；compiler 静默 fallback 编译成 `request != ""`。这实际区分的是空/非空，不是 urgent/routine，Note 却声称根据内容区分两类。故 branch labels、审批 placement 虽真实，Condition semantic truth 与 Note truth **不通过**。top-level output contract 保留两个字段；两个 branch Model 的 system prompt 均包含 `priority (string)`、`summary (string)` 和完整 JSON contract。Output node 的 `output_name=priority` 是节点标签字段，Runtime Output 执行时通过 `_prepare_outputs` 校验完整 `source.outputs`；本轮按要求没有 Run，故不声称有实际执行值证明。
- 新脱敏 fixture：`contracts/fixtures/invalid/agent-semantic-plan-condition-fallback-reacceptance-2.json`。只复现语义计划结构，不保存 provider raw response、凭据或完整 reasoning。最小修复：编译器不再把无法解析的自然语言 Condition 猜成非空测试；只接受 Runtime 支持的显式比较表达式并验证其字段属于 Agent input，否则返回 `condition_expression_required` / `condition_input_not_declared` 与路径，fail closed。Prompt/schema 已说明此边界。未修改 Builder proposal persistence、UI、Community 或其他功能。
- 浏览器：本地 Desktop `5173` 起初因 Vite 未运行显示 connection refused；启动 `5173` 后可加载登录页。登录错误提示根因是 Community auth service `8772` 当时未启动；启动 8772 后该错误消失，但当前登录表单没有账号/密码，显示必填提示。本轮没有读取、输入或传输凭据，因此 **5173 UI Proposal review/Canvas browser acceptance unavailable (unauthenticated)**；按附件授权使用 API + persisted canonical Factory Blueprint 检查，并将 UI 层明确留为缺口。
- 项目副作用核对：turn 前后 Agent=0、Workflow=0、Custom Component=0、Runtime Run=0、Workflow Run=0、Project-owned resource binding=0；没有 Apply/Confirm、Run、外部 Tool/HTTP 动作、资源创建或 migration。旧 Conversation 仍是原 `factory_generation_invalid` 失败状态；新 Conversation/Factory Blueprint/receipts 留存。
- 四服务按本轮要求已全部启动：5173/5174 HTTP 200；8771 health 200、`database_ready=true`、`local_0026_builder_semantic_plan`；8772 health 200、`database_ready=true`、`community_0008_plugin_registry`；build 均为 `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`。8771 使用当前 Conda Python 与仓库 `backend/src`；8772 使用仓库配置，无 temp DB/root/fake provider；`.env` 未被人工读取或打印。代码修正后只重启过 8771 以加载 latest working tree；无 schema migration。
- 修复后验证：SemanticPlan/Compiler/Factory/Builder/Proposal/Custom Component focused **158 passed**。最终 `env -u PYTHONPATH -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check` **714 passed**，Ruff、依赖锁、mypy 187 个源文件通过；Web Desktop **472 passed**、Community **22 passed**，双端 typecheck/build 通过。warning 保留：Alembic `path_separator`、jsdom Canvas `getContext`、Desktop 大 chunk。
- 总结：**Builder Real Provider Re-Acceptance #2 = FAIL**（无 `proposal_id` canonical Proposal；Condition 语义错误；UI 登录层未验收）。未再次调用 Provider。Agent Composition V1 仍不能进入 Release Audit/标记 accepted；需下一轮先处理 proposal identity/persistence 与可表达的自然语言分类语义，再单独授权 Re-Acceptance #3。

## Condition Semantic Contract + Canonical Proposal Identity Hardening（2026-09-24，本地 dirty slice）

- 本 Slice 延续 `0ad7a3e` 工作树，不是 Re-Acceptance #3；没有调用真实 Provider、没有 Confirm/Apply/Run、没有重启服务、没有 stage/commit/push。
- 当前 Runtime Condition grammar 已审计并集中到共享 contract：`field == literal` / `field != literal`，literal 仅 string/boolean/integer。运行时有 per-run values，但没有可供 Builder 任意命名的正式 typed intermediate namespace；没有引入 `eval`、脚本、隐式 Model classifier 或新的 generic dataflow engine。
- `AgentSemanticPlan` 新增 additive `condition_expression`。`purpose` 只做人类意图，compiler 只读取 `condition_expression`；缺失、未知输入、非法 operator 或注入语法分别 fail closed，不能降级成 `field != ""`。Canonical Canvas Note 只记录已验证的 executable expression 与 branch labels。
- Factory semantic repair sanitizer、Builder prompt、Python contract、JSON Schema、MFJS projection parity 与 Runtime parser 已同步；保留 `agent-semantic-plan-condition-fallback-reacceptance-2.json` 作为失败 fixture，并新增 Condition parser/adversarial tests。
- Factory review candidate 现在 materialize 为现有 `edit_proposals` store 中的 `proposal_kind=create_agent` canonical snapshot，保存 candidate source/Blueprint/resource plan/semantic plan/provenance；`builder_operations.proposal_id` 与 `builder.proposal.ready` facts 在同一事务写入。`local_0027_builder_creation_proposals` 为 operation 关联和唯一性增加窄 migration；重复 materialization 复用同一 ID。
- Builder `records` 不再接受客户端伪造或跨 operation 的 proposal_id；Proposal 必须属于当前 operation 或其真实 focus target。Confirm/Apply 仍保留在后续独立边界，当前 Slice 不执行创建 Agent。
- Focused Builder/Condition/Proposal/Custom Component suite：**129 passed**；完整 `env -u PYTHONPATH -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`：**720 passed**，Ruff、依赖锁、mypy **188 source files** 通过；Web Desktop **472**、Community **22**，typecheck/build 通过；`git diff --check` clean。
- 当前仍不能宣称 Builder accepted / Agent Composition V1 complete。下一步是用户单独授权的 Builder Real Provider Re-Acceptance #3，继续 proposal-only、隔离 Project、无 Confirm/Apply/Run。

## Canonical create_agent Proposal Confirm / Apply identity closure（2026-09-24，本地 dirty slice）

- 本 Slice 只闭合已有 Builder `create_agent` 的 Confirm / Apply 边界；没有进入新模块，没有调用真实 Provider、没有执行真实 Project 的 Run、没有重启服务、没有 stage/commit/push。
- Builder review 生成的 `candidate_source`、Blueprint、resource plan、semantic plan、identity 和 hash provenance 继续写入现有 `edit_proposals` 的 `proposal_kind=create_agent` 快照。新增的 Builder Agent Proposal command 校验 Project、conversation、operation、proposal 四重归属；Confirm 只按 `proposal_id` 取持久化快照。
- Apply 不再从可变 `factory_sessions.blueprint_json` 重新 compile。它重新解析并校验 Proposal 的 `AgentSource`、source/behavior/lock hashes 和当前 Project dependency readiness，然后以 preserve-identity 模式安装完全相同的 Agent source；Factory session 只作为 review/workbench 状态，成功后标记 completed。
- Apply 具备明确的重复语义：相同候选 Agent 已存在且 source 完全相同则复用 applied result；重复 Builder Apply 不新增 Agent、不重复终态事件或 result。Rejected、错误 operation、跨 Project、身份冲突和篡改快照均 fail closed。旧的直接 Factory `apply-draft` endpoint 保留为兼容路径，但 Builder canonical create-agent UI 已切换到 Proposal command。
- 新增回归覆盖：Factory session 漂移不改变最终 source；canonical Apply 幂等；Reject 后 Apply 返回 409；Proposal hash/snapshot 被篡改时不安装。既有 Custom Component proposal lifecycle tests 保持通过。
- 验证：canonical Builder conversation focused **32 passed**；完整 Conda `env -u PYTHONPATH -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check` **724 passed**，Ruff、dependency/lock checks、mypy **188 source files** 通过；Web Desktop **472 passed**、Community **22 passed**，双端 typecheck/build 通过；`git diff --check` clean。保留既有 Alembic `path_separator`、jsdom Canvas stderr 与 Desktop >500 KB chunk warning。

## Provider Credentials & Runtime Binding V1/V2（2026-09-25，本地 dirty slice）

- Platform Builder Provider 与 User Runtime Provider 继续严格分域。Platform secret 由部署/服务器配置管理；Local Runtime 不读取 Platform `model.primary` 或 `MOONSHOT_API_KEY` 作为隐式 fallback。
- `local_0028_provider_credentials_runtime_bindings` 建立 metadata 与 binding；`local_0029_provider_credential_scope` 增加 `credential_scope`。当前 Local API 只接受 `device`，`cloud` 只是未来契约 seam，不代表 Cloud Vault 已实现。
- `provider_credentials` 只保存 provider type、label、base URL、状态、scope、masked hint、capabilities、时间和 opaque `secret_ref`。真实 API key 由 `SecretStore` 交给跨平台系统 credential backend：macOS Keychain、Windows Credential Manager、Linux Secret Service/KWallet；不进入 SQLite、AgentSource、Project YAML、Proposal、Builder event、Run evidence、导出或 Community payload。
- Metadata 存在但 device secret 缺失时，API 明确返回 `secret_state=missing`、`readiness=needs_reentry`；系统 credential backend 不可用时返回 `readiness=unavailable`，不会伪装为可用，也不会降级到明文文件或 process-memory store。
- Local Credential API 与 Runtime binding API 保持不变形状并增加 scope/readiness metadata。Runtime resolver 仍按 Agent binding → Project binding → User default → missing；只有 readiness 为 `ready` 的 credential 可以进入 Runtime。
- Phase A 已用合成 `127.0.0.1:8790` Mock 完成正式 Replace、系统 credential store 写入、8771 停止/重启和 resolver-after-restart 验收；真实 Moonshot Runtime 未使用。
- Phase B Applied Agent Runtime Closure 已完成：确认既有 Request Review Agent active；正式 Validate/Commit 生成 immutable version；修复 output `status-2` 残留为 `status`，并修复同名 input/output 的 Runtime JSON 解析。approved 与 pending 两条本地 Mock Run 均按条件只执行对应 branch，结果和事件证据正确；Studio UI 复核确认 Catalog Model `requires_configuration` 与 Instance Runtime Binding 分离。
- 最终验证：backend full `make check` **733 passed**、mypy **190 source files**；Desktop **475 passed**、Community **22 passed**；Desktop typecheck/build 通过；真实 Studio Browser acceptance 通过；`git diff --check` clean。保留既有 jsdom Canvas stderr 与 Desktop large-chunk warning。

## Project Sync Foundation #1（2026-09-25）

- 产品模型已从两个独立的 Local Project / Cloud Project 收敛为一个 Logical
  Project：Local Working Copy 先创建，登录且 Cloud 可用时用完全相同的
  project_id 建立 Cloud Replica。首页没有新增 Cloud Project 卡片、页面或
  Sidebar 分类，现有 Create Project 是唯一用户入口。
- Cloud Host 仍运行在 8772，复用 Community Account/session/CSRF 和数据库
  lineage；新增 community_0010_project_sync_revision，cloud_projects.revision
  从 1 开始单调递增。8772 不导入 Local app、Local Project directory 或
  DeviceSecretStore。
- Local 新增 local_0030_project_sync_state 和 project_sync_states。它只保存
  state、Cloud revision、metadata hashes、pending operation、remote metadata
  和冲突诊断；不保存 Cookie、secret、credential ID、Keychain ref 或 local path。
- 本轮只同步 Project metadata（identity/name/description/lifecycle/schema），不
  同步 Agent、Workflow、Knowledge、Files、Runs、Chat、Provider Credential 或
  Runtime Binding。Desktop ProjectSyncCoordinator 负责 8771/8772 协调，Local
  API 不读取 Cloud Cookie。
- Cloud 协议是 explicit-ID ensure、pull、expected-revision push；同用户重复
  ensure 幂等，跨用户 claim 返回 404，stale revision 返回 409 sync_conflict，
  不使用 silent last-write-wins。Cloud 不可用时 Local 创建仍成功并进入
  pending_upload，页面重载/恢复后可 retry。
- 本轮没有实现 Project Artifact Sync、Cloud Files、Cloud Chat、Cloud Credential
  Vault、Cloud Runtime，也没有恢复上一轮独立 Cloud Project UI。
- 最终门禁：backend make check **741 passed**、Ruff format/check、依赖锁、mypy
  **201 source files**；Desktop **479 passed**、Community **22 passed**；两端
  typecheck/build 通过；Project Sync Coordinator focused **4 passed**、Local
  sync integration **2 passed**；git diff --check clean。保留既有 Alembic
  path_separator、jsdom Canvas stderr 和 Desktop large-chunk warnings。

## Cloud Files & Library Foundation #1（2026-09-25，已完成）

- 新增 Cloud File domain 与 `community_0012_cloud_files` forward-only migration：
  `cloud_files` 保存账号私有 metadata，`cloud_project_file_references` 保存
  Project 引用。没有修改已应用的 `community_0011`，Local DB 不新增文件表。
- 新增窄 `BlobStore` contract 与开发/self-host `FilesystemBlobStore`。文件 bytes
  在服务器 Cloud data root 的临时对象中流式写入，完成 size/SHA-256 和 upload limit
  校验后原子 finalize；数据库只保存 metadata 和 server-generated storage key。
  storage key/root 不返回前端；当前没有安装 S3 SDK，未来 S3/MinIO/R2 只通过该 seam
  替换。
- Cloud API 已支持 authenticated list/upload/get/stream-download/delete，以及
  Project File attach/detach/list。所有 operation owner-scoped；跨账号返回非披露
  404；有引用时 Library delete 返回 `file_in_use`；detach 不删除 blob；无引用删除
  同时删除 metadata/blob。上传不扫描 Local Project，也不接受 base64 JSON 整文件。
- Local 只增加安全 materialize foundation：Cloud 下载字节必须显式指定目标，限制在
  Project `assets/` 或 `knowledge/`，拒绝绝对路径、`..`、symlink，并校验预期 hash/size。
  Knowledge 增加可选 `cloud_file` source reference；仍不自动下载、不自动 index。
- Web/Desktop 共用 `CloudFile*`、`ProjectFileReference` contracts 和 connected-account
  client；本轮没有新增页面、Sidebar、Files 大 UI、Knowledge 重做或 Community UI。
- 真实本机验收：Chrome 已确认账号仍可用、现有 Artifact Project 页面和 Sidebar 正常；
  Cloud File bytes 使用授权测试账号的 isolated acceptance harness 上传。首次上传、
  metadata、list、download、SHA/size、Project attach/list 通过；重启 8772 后
  metadata/blob/download 仍通过；随后 detach、delete、Project archive 清理成功，
  blob count 为 0。Harness 不是纯 UI upload E2E，浏览器部分只验证现有页面路径和回归。
- 真实服务：8771 Local `local_0031_project_artifact_sync_state`、8772 Cloud
  `community_0012_cloud_files`；Cloud `/api/v1/ready` 返回 `ready=true`。
- 本 Slice 最终验证：backend `make check` **754 passed**、399 warnings，Ruff/format/
  dependency lock PASS，mypy **216 source files**；Desktop **484 passed**（64 test
  files）、Community **22 passed**（3 test files）；两端 typecheck/build PASS；
  `git diff --check` PASS。保留既有 Alembic `path_separator`、jsdom Canvas stderr
  和 Desktop large-chunk warning。
- Real Platform Provider、Real Runtime Provider、Agent Run、Cloud Chat、Cloud Runtime、
  Cloud Credential Vault、PDF/OCR/vector RAG、public sharing、S3 production deployment
  均未执行或未实现。

## Existing Chat Server Authority & Cross-Client Persistence #1（2026-09-25，已完成）

- 审计确认当前现有 Chat 是 Project Builder Chat：Desktop Chat UI → Local API →
  `BuilderConversationService` → `BuilderConversationStore` → Local SQLite 的
  `builder_conversations` / `builder_messages` / `builder_operations`。本轮没有创建
  第二套 Chat UI，也没有重写 Builder、Proposal 或 Apply。
- Cloud/Community 新增 `community_0013_conversations` forward-only migration，建立
  account-owned `conversations`、`conversation_messages`、`conversation_operations`、
  `conversation_operation_events`。Cloud Host head 已从 `community_0012_cloud_files`
  正向升级；Local head 保持 `local_0031_project_artifact_sync_state`。
- Server API 支持 Conversation list/create/get、Message append、import、rename、
  archive、restore。Conversation 使用 owner_user_id、可选 Project/Agent relation、
  revision 和 server sequence；Message 支持稳定 message_id、append 幂等、ordering、
  operation/proposal/event refs。跨账号读写和跨账号 Project 绑定返回非披露 404。
- Message attachment 只接受当前账号的 Cloud File ID；Message JSON 不携带 bytes、Local
  path、credential、secret 或 storage key。Cloud File authority 仍是上一 Slice 的
  `/api/v1/cloud/files`。
- Desktop 新增薄 `ConversationMigrationCoordinator`：首次有账号 session 时读取
  现有 Local Builder activity/snapshot，以原 conversation_id、message_id、operation_id、
  proposal_id 和 event_id 幂等 import 到 Server；不删除 Local 旧数据。Recent 优先读
  Server Conversation list，Server endpoint 不可用时保留明确的 Local cache fallback。
  现有 Builder 页面继续通过 Local Host 执行本机 Project 操作，Server 只成为账号 Chat
  persistence authority；没有长期的 Local↔Cloud Chat 双主同步产品。
- 真实 API cross-client acceptance：Desktop A 创建 C1、写入 M1；Web B 读取同一 C1/M1
  并写入 M2；A 重新读取 M1/M2；Cloud File F1 作为 attachment ref 在 B 端可见且可通过
  Cloud File endpoint 下载。8772 重启后 Conversation、Messages、Project relation 和
  attachment ref 仍存在，随后已清理 isolated Project/Conversation/File。未发送真实
  Provider 请求。
- 本 Slice focused：Cloud Conversation **4 passed**、Desktop migration coordinator
  **2 passed**；最终 backend `make check` **758 passed**、399 warnings，mypy **221
  source files**；Desktop **486 passed**（65 files）、Community **22 passed**；两端
  typecheck/build PASS；`git diff --check` PASS。保留既有 Alembic `path_separator`、
  jsdom Canvas stderr 和 Desktop large-chunk warning。
- Browser boundary：没有发送 Chat 消息或 Provider 请求；本轮尝试用真实 Chrome 打开
  现有 Chat 页面时，Chrome debugger connection 不可用，因此没有把页面检查伪称为通过。
  cross-client 数据证据来自 authenticated API acceptance harness；没有新增 UI 页面或
  Sidebar。

## Project Artifact Sync #2（2026-09-25，已完成）

- 在 Logical Project / 同一 project_id 上增加统一 Project Artifact envelope，当前
  kind 为 agent、agent_version、workflow、custom_component、knowledge_metadata。
  Cloud 使用 community_0011_project_artifacts；Local 使用
  local_0031_project_artifact_sync_state。旧的 0010/0030 migration 没有修改。
- Cloud Artifact API 提供 owner-scoped manifest、get、expected-revision put；
  mutable Artifact 独立 revision，immutable Agent version 允许同 hash 幂等重传，
  同 ID 不同 hash 返回 integrity conflict。payload 递归拒绝 API key、credential、
  secret、Keychain、absolute path、local URI 和 device-only 字段。
- Local Artifact API 负责 discovery、portable payload、materialize 和 per-artifact
  sync state。Agent/Workflow/Knowledge pull 继续走现有 domain contract 与 Project
  canonical writer；Custom Component 只安装当前真实定义，design_only 不会被升级。
  Knowledge 只同步 metadata/hash，另一设备得到 metadata_only，不可假装可检索。
- Desktop 已有 ProjectArtifactSyncCoordinator，负责 dependency order、delta/no-op、
  push/pull/conflict/pending；本轮没有增加页面或 Sidebar UI。Cloud Files、raw Knowledge、
  Runs、Chat、Credential、Runtime 仍不在范围内。
- 本轮 focused：Cloud/Local Artifact 与 Project Sync **31 passed**；Desktop Artifact
  Coordinator **5 passed**、既有 Project Sync **4 passed**；Local second-device
  materialization **3 passed**。最终 backend `make check` **746 passed**、mypy
  **208 source files**、Ruff/format/依赖锁 PASS；Desktop **482 passed**、Community
  **22 passed**；typecheck/build PASS；git diff --check PASS。保留既有 Alembic
  path_separator、jsdom Canvas stderr 和 Desktop large-chunk warnings。

## Server Execution Plane V1（2026-09-25）

- Cloud migration 已从 `community_0013_conversations` forward-only 升级到
  `community_0014_server_credentials` 与 `community_0015_cloud_runs`；真实 8772
  当前为 `community_0015_cloud_runs`，8771 为 `local_0031_project_artifact_sync_state`。
- Cloud Credential Vault 已完成 owner-scoped CRUD、no-generation validation、replace、
  enable/disable/default 和 Project/Agent binding。SQLite 只保存 metadata 与 AES-GCM
  ciphertext；production 必须配置 `VEYRA_CLOUD_CREDENTIAL_MASTER_KEY`，本机 development
  使用独立权限受限 master-key 文件。Settings Provider card 登录后优先走 Cloud API，
  没有 Cloud bridge 时保留 Local fallback；页面布局未重做。
- Cloud Runtime 只加载 exact immutable `agent_version`，校验 source/behavior/lock hashes；
  支持 Start/Model/Transform/Condition/Verifier/Output/HumanApproval。Tool 在 Cloud
  fail closed 为 `local_host_required`，Cloud File input 必须 owner/project scoped。
- Builder `create_agent` 的 waiting operation 仍由 Local Conversation durable 保存；选择
  Cloud credential 时先写入 Cloud Project `primary_model` binding，再以显式
  `credential_scope=cloud` 恢复同一个 operation，不把 Cloud secret 或 Platform key 交给
  Local Runtime。没有 Credential 时只显示添加/选择卡，不阻断普通 Chat。
- Cloud Run API 支持 create/get/list、durable events、SSE + `Last-Event-ID`、approval/
  reject、stop、retry child lineage、checkpoint resume 和 restart recovery。Run evidence
  只保存 provider/model、`credential_type=user`、alias 等安全 metadata。
- Focused execution **8 passed**；Cloud suite **27 passed**；最终 backend **767 passed / 399
  warnings**，Ruff/format/dependency lock、mypy **234 source files** 通过。Desktop **487
  passed / 66 files**，Community **23 passed / 4 files**；两端 typecheck/build PASS；
  Desktop build JS 1,202.14 kB、Web build JS 343.75 kB；Desktop large-chunk warning、jsdom Canvas stderr 和 Alembic
  `path_separator` warning 保留。
- 真实本机 mock acceptance：8771、8772、5173 均健康；Cloud mock Transform Run、SSE、
  8772 restart persistence、cleanup 通过。Real Provider acceptance：**NOT RUN**；真实
  Agent Model Run：**NOT RUN**。jsdom/API harness 不冒称真实 Browser acceptance。
- 5174 已从纯 Showcase 入口收口为 Web Workspace：登录、Projects、Cloud Conversation、
  Cloud Files、Cloud Runs、Community、Account、Cloud Credential Settings 使用同一 Server
  API；`#/showcase` 保留公开展示。Web 明确不提供 Local Working Copy、Finder、Git、Shell、
  MCP、Local Runtime 或 Device Credential。

## V1 Product Closure deployment/packaging audit（2026-09-25）

- Production Cloud deployment now starts `veyra_agent_platform.cloud.app:app` through
  `VEYRA_HOST_KIND=cloud`; the same authenticated Cloud Host exposes Account, Registry,
  Projects, Artifacts, Files, Conversations, Credentials, and Runs. Production requires
  PostgreSQL, S3-compatible object storage, `VEYRA_CLOUD_CREDENTIAL_MASTER_KEY`, auth HMAC,
  public origin, and explicit non-wildcard allowed origins. Secure cookies remain enabled in
  production; localhost development keeps its existing cookie behavior.
- Cloud Files support an S3-compatible adapter reusing the repository's signed S3 client seam;
  FilesystemBlobStore remains development/self-host only. `/api/v1/ready` now checks DB head,
  object storage, and Cloud credential cipher readiness. Backup/restore scripts document DB,
  blob-store, and master-key handling without writing secrets into the repository.
- Fresh Local and Cloud SQLite migrations from empty databases passed; copied current Local and
  Cloud databases upgraded to current heads. PostgreSQL migration SQL generation passed;
  live PostgreSQL integration: **NOT RUN** because Docker is unavailable in this environment.
- Desktop package static smoke: **PASS** (`static_contract=ok`). macOS arm64 package build:
  **NOT RUN** because Rust/Cargo tooling is unavailable in this environment. Signing and
  notarization: **SIGNING NOT RUN — Apple Developer credentials unavailable**.
- Golden-path API evidence: Build/Proposal/immutable Version foundations remain covered by the
  existing Local tests; mock Cloud Run path passed; Community Publisher A → Discover → Star →
  Download → Local Import Preview → no Project mutation before Confirm → Local Draft → Local
  mock-free Transform Run passed in an isolated two-account API harness. Web/Desktop shared
  Project/Conversation/Run IDs passed in an authenticated cross-client harness. Browser E2E:
  **NOT RUN**; Chrome debugger was unavailable, so API/jsdom evidence is not called Browser E2E.

## Community information architecture and visual refresh（2026-09-26，本地工作树）

- Community Desktop 首页从“注册表卡片列表”调整为开发者社区入口：深色社区 Hero、真实作品发现流、版本检查路径、收藏/发布下一步和讨论区预留；仍只读取真实 Registry / Star / Review 数据，不添加假帖子、假热度或假推荐。
- `#/community/mine` 调整为创作者工作台：发布 Agent 是主任务，发布前 Source/哈希/依赖/权限检查作为侧栏，真实已发布版本作为辅助列表；Plugin Pack 降级为可展开的第二层发布通道，避免空状态占据整块首屏。
- 保留原有发布预览、显式确认、导入预览、Star、版本详情、路由和 moderation 行为。页内“浏览作品/开始发布”使用真正的平滑滚动，不写入路由 hash。
- 讨论区当前仅展示产品方向和已可用的版本评价边界；creator follow、帖子、Feed、讨论 API 仍未实现，不能标记为社交社区闭环完成。
- 验证：Desktop 全量 `npm test --workspace=@veyra/desktop` **488 passed**；Web 全量 Desktop **488** + Community **23 passed**；Web typecheck 与 desktop/community production build 通过；保留 Desktop 既有大 chunk warning 与 jsdom Canvas stderr。
- 代码范围：`web/apps/desktop/src/pages/community.tsx`、`web/apps/desktop/src/features/community/community.css`、`web/packages/connected-account/src/styles.css`；未 stage、commit 或 push。

## Community flagship visual refinement（2026-09-26，本地工作树）

- 按四个真实页面截图继续收敛：Discover 的 Hero 改为轻量产品头部，Published 改为可扫描的版本记录行，Starred 增加独立标题/说明/正常空态，Mine 的创作者 Hero 和发布区减少营销式留白。
- 视觉系统保留 Veyra 的 teal/indigo token、深浅色和中文/英文，新增 GitHub 式底线导航、细边框记录、轻量 hover/淡入/轨道浮动动画；`prefers-reduced-motion` 关闭动画。
- 仍不添加假帖子、假数据、假热度或未实现资源类型；所有内容继续来自真实 Community Registry / Star / Review / publish/import flows。
- 验证：Desktop 全量 **488 passed**；Desktop typecheck；Web Desktop/Community production build 通过；既存 Desktop 大 chunk warning 与 jsdom Canvas stderr 保留；实际 Chrome 检查 Discover / Published / Starred / Mine。
- 本轮未 stage、commit 或 push。

## Community catalog view switch（2026-09-26，本地工作树）

- Discover / Starred 增加卡片 / 按行两种显示方式，默认卡片模式，偏好保存到浏览器本地；两种模式复用相同的真实 Registry 数据、Star 和版本详情路由。
- 列表模式使用紧凑 release row，适合快速扫描作者、版本、节点和操作；卡片模式保留推荐目录的视觉浏览体验。
- 修复当前工作树中重复的 `section === "mine"` 数据加载分支，使 Desktop typecheck 恢复通过。
- 验证：Community 页面定向测试 **3 passed**；Desktop 全量 **488 passed**；Desktop typecheck、Desktop production build 通过；Chrome 实际点击卡片/列表按钮并恢复默认卡片模式。
- 本轮未 stage、commit 或 push。

## Community reference design implementation（2026-09-26，本地工作树）

- 按用户提供的图 2 视觉稿落地 Community：Discover 增加 Community 标题区、几何装饰、搜索、资源类型胶囊、推荐区和 Agent graph preview；Published 增加四项状态统计、状态筛选胶囊和表格列；Starred 增加搜索/排序；Mine 改为 Creator Center，包含资源类型入口、四项统计、最近发布和草稿边界。
- 图 1 的卡片/列表切换保留在 Discover / Starred，列表模式复用同一真实 Registry 数据并以紧凑 release row 呈现；没有添加图片字段、假资源、假评分或假讨论。
- Workflow / Skill / Tool / Plugin Pack 在 Discover 中显示为真实能力边界：当前未开放的目录入口保持 disabled，并给出原因；Plugin Pack 的真实发布通道保留在 Creator Center。
- 验证：Desktop 全量 **488 passed**；`app.test.tsx` **59 passed**；Community 页面定向 **3 passed**；Web build（Desktop + Community）与 Desktop typecheck 通过；Chrome 实际检查四个社区页面、浅色/暗色与网格/列表切换。
- 本轮未 stage、commit 或 push。

## Community creator workspace correction（2026-09-27，本地工作树）

- `#/community/mine` 重组为 Creator workspace：状态概览只使用真实 Published / In review / Rejected / Star 数据；发布类型、来源选择、检查与确认统一在一块 Release Studio 背景内；不存在持久后端的 Community Draft 指标和草稿面板已移除。
- 页面按设计路线显示 Agent、Project、Workflow、Plugin Pack、Template、Component/Tool/standalone Skill。只有当前已有真实 Registry API 的 Agent 与 Plugin Pack 可操作；Project 只标明本地 export 已存在、Community 发布接口待接入，其余保持 planned，未增加假 API 或假发布结果。
- Discover / Published 的 version-bound Star 显示现在都由账户 `GET /api/v1/registry/starred` 集合恢复，修复同一 release 在 Discover 显示已收藏、Published 显示未收藏的问题；Starred 列表仍是自身权威状态。
- 验证：Desktop 全量 **66 files / 490 tests passed**；Community + App 定向 **64 passed**；Desktop typecheck、production build 与 `git diff --check` 通过。实际浏览器检查 Mine 浅色/暗色/窄 viewport、Agent/Plugin Pack 切换，以及 Discover/Published 同一 release 都显示已收藏。未执行发布、上传或 Star mutation。

## Connected Account workspace redesign（2026-09-27，本地工作树）

- `#/account` 改为账号身份摘要、公开资料、会话安全三层布局；保留头像、display name、handle、邮箱、资料保存、会话撤销和退出账号的原行为。
- 按原 Connected Account / Community 设计补入真实社区身份入口：Creator workspace、Published releases、Starred resources，以及已启用的 immutable publish、save/review、Fork lineage 能力；组织、计费和 private backup 仍是 later，不在页面伪装成可用。
- 本机边界以可见清单说明：Project / Agent / Workflow source、Run / approval / receipt、Secret values / host credentials 不因登录自动上传或按账号隔离，只有显式 Publish/Sync 才离开设备。
- 设备展示不再回显长 User-Agent；根据实际 user agent 归一浏览器/平台名称，同时保留有意义的显式 `device_name`。桌面端会话列表固定高度滚动，窄屏使用自然页面滚动。
- 页面明确 Community 只保存身份和发布元数据，Project / Agent / Run 仍在本机；退出登录不会删除本地 Project 或 Community release。未改后端契约或执行账号 mutation。
- 验证：Desktop 全量 **66 files / 490 tests passed**；Account/App 定向 **59 passed**；Desktop typecheck、production build 与 `git diff --check` 通过。实际浏览器以当前真实账号、Community route cards 和 17 个会话检查浅色、暗色与窄 viewport。保留既有大 chunk warning 与 jsdom Canvas stderr。
