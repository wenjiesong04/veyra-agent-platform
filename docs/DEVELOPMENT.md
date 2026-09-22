# Veyra Agent Platform — 主开发文档

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
- Desktop：`5173`；Local sidecar：`127.0.0.1:8771`；Community：`127.0.0.1:8772`

验收围绕 `Idea → Build → Run → Observe → Trust → Reuse → Share`。
页面数量、静态演示数据和过期测试计数都不是完成依据。

## 2. 已发布模块（Git 事实）

| 模块 | SHA | 范围 |
| --- | --- | --- |
| Chat-first Builder Phase 1 | `9153617` | Project Chat 修改已有 Agent/Workflow：提案 → 确认 → Draft；不是全 Project 事务 |
| Runtime V1 | `ea94b64` | 事件/回执、审批、Stop、安全 Retry、checkpoint Resume、run_id 历史证据 |
| Resource Library V1 | `ee814e2` | Catalog 真实 readiness → Project pin → Agent lock → Runtime 按 pin 执行 |
| Knowledge V1 | `8351806` | 本地 txt/md ingest → 显式索引 → 绑定检索 → Run 引用证据 → Resource-Library 风格工作台；浏览器闭环在 `560a912` 上验收 |
| Graph Compiler V2 | `8bef91c` | SemanticPlan → 可执行 Agent 图 + Default Canvas Note + Provider schema hardening |
| Typed I/O + Artifact Runtime | `5f8e8a8` | TypedField / ArtifactRef、Project-scoped object store、Runtime modality truth、shared Test UI |
| Agent Composition Slice 1 | uncommitted | Rich Semantic Planning + Resource-aware composition；保留为当前基线 |
| Agent Composition Slice 2 | uncommitted / locally verified | Project-owned Custom Component contract、草稿/版本生命周期与 Studio 动态节点；本地门禁通过，未发布 |
| Agent Composition Slice 3 | uncommitted / locally implemented | Builder Component Proposal、显式确认、Capability reuse、direct `create_component` 与 Agent continuation；全量本地后端门禁及 Desktop 测试/typecheck 通过，未发布 |
| Agent Composition Slice 4 | uncommitted / locally verified | Studio/Workflow 与 Builder proposal 共用 DAG layout；Default Note 居中定位且支持手动固定；本地全量门禁通过，未发布 |
| Agent Composition Slice 5 | uncommitted / locally verified | Studio 与 Builder Workspace 共用 Runtime execution projection；按 Run immutable version 恢复画布；workspace Test Run 隔离；本地全量门禁通过，未发布 |

GitHub Actions Billing 仍是外部阻塞，不把未执行的 CI 写成代码失败或 CI PASS。

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
E2E 或发布验收。Builder Provider 请求、Approval/Condition/Custom Component 浏览器路径
尚未验收；GitHub CI 与 release checkpoint 也未完成。Slice 1–5 仍未 commit/push，属于
本地实现和部分手工验收，不代表已发布。实现边界及剩余验收见 `.backboard/HANDOFF.md` 最新的
**Agent Composition V1 — Slice 5 implementation** checkpoint。

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
| Community | 注册表第一版，差得最多 | **仍然成立。** Desktop 有 Agent/Plugin 注册表；公开 Web 仍用静态 `communityEntries` |
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
`kimi-k3`：`image_input=unsupported`。缺 pdf_parser / pdf_renderer /
image_generation 保持 truthful `missing_capability`。Studio Test、
Workflow Test、Builder Test、Run Detail 共用 `RuntimeInputForm` /
`RuntimeOutputView`。独立 Agent Playground 与 Workflow Builder Compiler
**尚未实现，也不是当前主任务**。 Builder Workspace/Test 位于每次
Builder operation 对应的 Conversation 历史中，不是固定右侧栏。

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

Typed I/O + Artifact Runtime 已发布为 `5f8e8a8`。当前主任务是
**Agent Composition & Capability System V1** + **Canvas Runtime Execution Overlay V1**。
不要创建独立 Playground，不要重做 Conversation Test 布局。

1. Slice 1 Rich Semantic Planning + Resource-aware composition（本地完成，不重做）
2. Slice 2 Custom Component contract + Resource Library lifecycle（本地完成，不重做）
3. Slice 3 Builder Component Proposal + reuse（本地完成，不重做）
4. Slice 4 Graph layout + Note centered placement（本地完成，不重做）
5. Slice 5 Runtime Execution Overlay（Studio 与 Builder Workspace 共用 Run 投影；本地门禁通过，Studio/Runtime 有限手工验收通过；Builder Provider 与复杂审批/分支/组件浏览器验收待完成）

Slice 3 的硬边界：Component 创建永远需要单独的显式确认；Agent 路径在
Component 发布后重新 resolution，并单独 review/confirm Agent Blueprint；直接
`create_component` 不创建 Agent。Slice 4 仅调整画布布局和 `ui.notes` 展示定位，
不改节点、连线、端口或运行语义。Slice 5 从 canonical Run events 投影节点状态和
实际 port 对应的边状态；运行画布固定到 Run 的 immutable Agent version，Builder
Test operation 绑定 workspace，Runtime inspector 只呈现安全 allowlist 字段。整个
Slice 1–5 仍是本地未提交实现；尚未完成正式浏览器端到端、Slice 5 Builder Provider
验收与 release checkpoint，因此不得称为已发布。当前仅记录一笔配置 Provider 的
Runtime smoke；更广泛的真实 sidecar / Builder 能力验收仍缺。

不要重开 Knowledge V1、Resource Library V1、Runtime V1、Builder Phase 1、
Typed I/O，也不要扩展 PDF parser/renderer 或 embedding。不要开始 autonomous loop。
不要把 Conversation Artifact Binding 作为当前主任务。

Builder Phase 2 整个模块完成并发布后，下一个大模块仍是 **Community 分享闭环**：

1. Agent / Workflow 发布 → 导入预览 → 权限/依赖/兼容性 → 转为 Veyra Draft
2. 公开 Community 去掉静态 `communityEntries`，改走真实 API
3. 再扩展 Project/Component/Tool/Skill 和互动能力

不要单独开“重做所有页面”的模块。Community 与数据分析页的友好化放进对应闭环。

## 7. 仍不能宣称完成

- Knowledge 工作台已有一条隔离浏览器闭环证据；其余页面仍没有浏览器 E2E
- 没有 PostgreSQL + 对象存储演练，就不能宣称 Community production ready
- 没有真实外部 Provider，就不能宣称 Runtime 已在生产网络下验证
- Builder 不能一次修改多个对象，也不是全 Project 操作入口
- Builder Phase 2 仍未作为独立 Git 发布标签。Durable Conversation、
  Semantic Plan Compiler V1、Interaction Model V2、ProviderCapabilityProfile、
  Harness Receipt 与 Slice 4 Test Run 已包含在 `8f71a1e`。Agent Graph
  Compiler V2 已发布为 `8bef91c`。Typed I/O + Artifact Runtime 已发布为
  `5f8e8a8`。独立 Playground 不是当前主任务。Agent Composition Slice 1
  尚未作为独立 Git 发布。
- 手写 PDF input Agent 的 Runtime readiness 不会自动变成 `pdf_parser`
  missing；缺 parser 的 truthful 点在 Compiler。Runtime 只把 ArtifactRef
  文件名写入 prompt，不 UTF-8 decode PDF bytes，也不把 bytes 写入 Run JSON
- 旧 Factory session 目前只恢复最新 canvas，不是完整 conversation/workbench
- 公开 Community 目录仍有静态样例，不能当成真实注册表

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
