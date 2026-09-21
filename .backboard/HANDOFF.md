# Veyra Development Handoff

## Current checkpoint（2026-09-20，Builder Phase 2 Slice 4 = complete）

- Branch：`codex/agent-platform` → `origin/codex/agent-platform`
- HEAD：`4e3c2e6`（ProviderCapabilityProfile + Harness Receipt 已发布）
- Slice 4 working tree dirty：`4e3c2e6-slice4-dirty`（**未 commit / 未 push**）
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`
- 不要重开 Interaction Model V2 / Durable Conversation /
  AgentSemanticPlanV1 / SemanticPlanCompiler / ProviderCapabilityProfile /
  Harness Receipt / Slice 4
- 暂停：autonomous Run、Community redesign、behavioral eval / LLM judge
- 下一步：Builder Phase 2 最终 release gate（含 Playwright CASE 1–3）

### 窄审计（实现前核对的真实连接点）

1. Runtime start-run：`POST /api/v1/projects/{project}/agents/{agent}/run` →
   `RuntimeService.run()`。Builder `start_test_run` 直接复用，不另建 Run store。
2. Version boundary：`run()` 校验当前 Draft `source_file_hash`，按 fingerprint
   复用或创建 **immutable Agent version**，Run 绑 `version_id`。不是匿名可变 Draft。
3. Studio Test Run：同一 `run()` + Live Run / Run Detail。Builder 不发明第二套
   Runtime 语义。
4. Runtime model：host default → Project profile → Agent profile。`readiness.model`
   给出 `required/configured/model_id/base_url`。
5. 配置位置：`GET/PATCH /runtime-profile` 与
   `/projects/{id}/agents/{id}/runtime-profile`；host `GET /runtime/status`。
6. Run statuses（contract 事实，不是 queued/completed）：
   `running | waiting | verified | unverified | failed | interrupted | cancelled`。
7. Run events：canonical Runtime events（`run.created`、node/tool、approval 等）。
8. Tool receipts / Knowledge evidence / approvals：只在 Runtime Run Detail。
9. Failure：Runtime `error.code`。Builder 只投影 `RunObservation`。
10. Retry/resume：仍走 Runtime V1 command；Builder Stop/Approve/Reject 转发
    `runtime.command`。
11. exact `run_id`：`GET /projects/{project}/agents/{agent}/runs/{run_id}`。
12. BuilderOperation 本就有 `run_id`；Slice 4 写入实际 Runtime `run_id`。
13. Builder Chat 此前没有 Runtime client；Test Agent 只调
    `startBuilderTestRun` / `commandBuilderTestRun` / `proposeBuilderTestRepair`。

### Test Run contract

- 用户显式点击 **测试 Agent** 才 `POST .../test-runs`。Apply / Confirm /
  Validate **不会**自动 Run。Repair Apply 后只 Validate；**再次运行**仍需手动。
- 新 operation：`kind=test_agent`。不塞进先前 Build Activity。
- Builder 只存：`run_id`、operation status、派生 `RunObservation`、
  可选 `proposal_id`。
- Runtime 仍是 events / tool receipts / Knowledge evidence / approvals /
  model evidence / output / failure 的唯一事实源。
- Chat 不复制 Runtime events；test operation 不写 `builder_harness_receipts`。
- 未配置 Runtime model：typed `runtime_not_configured`，**不创建 Runtime 行**，
  **不把 Builder Kimi 绑给 Agent**。

`RunObservation`：`run_id`、`version_id`、Runtime status、`runtime_model_id` /
`runtime_model_source`、`output_summary`、`failure_code`、`failed_node`、
`tool_failure`、`knowledge_failure`、`approval_required`、`duration_ms`、
`evidence_count`、`classification`、deterministic `explanation`、
`repair_code`、`next_action`。

### Runtime version semantics

Studio `run()`：Draft fingerprint 匹配 → 已有 version 复用，否则插入
immutable version → schedule execution。Builder Test Run 同一条路径。
Observation 的 `version_id` 与 Run Detail 一致。

### Builder Model ≠ Agent Runtime Model

| | Builder Model | Agent Runtime Model |
| --- | --- | --- |
| 用途 | Intent / Semantic Plan / Builder 理解 | 真正执行用户 Agent |
| 当前 live | Factory Moonshot / `kimi-k3` / profile `known`+`probe` | Host default Moonshot / `kimi-k3`（`/runtime/status`） |
| 证据 | `BuilderHarnessReceipt` | Runtime Run events / output |
| 429 | Factory / ProviderProfile domain | `runtime_rate_limited`，不改 Builder Profile，不写 Harness Receipt |

两者现在碰巧都是 `kimi-k3`。UI 明确写「这是 Agent Runtime Model，不是
Veyra Builder Model。」`runtime_model_source=default|project|agent`。

### Repair classification

- **repairable**：`tool_permission_denied` / `permission_denied` /
  lock mismatch → `create_validation_repair` EditProposal；Confirm 后
  Apply → Validate；不自动再 Run。
- **user_action**：`runtime_not_configured`、unbound、stale knowledge、
  missing secret → 解释 + next action，不假修。
- **environment**：Runtime 429 / 5xx / timeout / stop → Retry later，
  不改 Agent。Stop → Runtime `cancelled` + operation `succeeded` +
  `builder.test_run.stopped`（不是 Builder operation failed）。
- **semantic**：结构成功但行为不符 → 只解释，本 Slice 不改 prompt。
- **waiting**：Runtime `waiting` + `approval.requested`。Builder 显示
  等待批准，复用 Runtime Approve/Reject，不是 failure。

### 证据

- 后端 focused：`test_builder_test_run.py` + `test_builder_test_runs.py` +
  `test_composition.py` → **32 passed**
- Desktop focused：`BuilderTestRun.test.tsx` + `BuilderActivityBlock.test.tsx`
  + `project-builder.test.tsx` + `local-client.test.ts` +
  `workbench-phase.test.ts` + `factory-conversation.test.tsx` → **92 passed**
- Desktop `tsc --noEmit` 通过
- `ruff check` / `ruff format --check` / `mypy`（Slice 4 相关 3 files）/
  `git diff --check`：clean
- 未做全量 `make check`；未做 Playwright

### 真实 acceptance

**CASE 1**（已有简单 Agent + Runtime 已配置）：

- Project：`New project`
- Agent：`中英文翻译 Agent`
- Explicit Test Run 输入：`Hello world`
- `run_id=01a0bd7a-a87e-720a-9872-5ce075f38a63`
- immutable `version_id=01a0bd7a-a87e-77fc-bf4f-1571a1c2a52e`
- Runtime status `unverified`（canonical 成功，不是 queued/completed）
- output：`你好，世界`
- Runtime model：`kimi-k3` / `source=default`（Agent Runtime，不是 Builder 标签误用）
- View Run Detail exact `run_id`：15 条 Runtime events
- Builder receipts：`[]`；Chat messages：`[]`
- Factory profile 仍是 `known` / `probe`（Runtime 调用未改 Builder Profile）

**CASE 2**（构造 `runtime_not_configured`，验收后已恢复 Agent profile）：

- 临时 Agent profile `api_key_env=VEYRA_SLICE4_MISSING_KEY`
- Test Run：`run_id=null`，无假成功 Runtime 行
- `failure_code=runtime_not_configured` / `classification=user_action` /
  `next_action=open_runtime_settings`
- 解释明确：Builder Kimi 不会自动成为这个 Agent 的 Runtime
- Agent profile 已 PATCH 回 `null`，readiness 恢复 host default `configured=true`

**CASE 3**（permission / readiness repair）：

- 三个真实 Project 当前没有 `filesystem.read` pin，也没有 Tool-node Agent。
- 未为了验收改现有 Draft、未读敏感文件。
- 闭环由 focused integration
  `test_no_automatic_run_after_apply_and_repair` 覆盖：
  typed Observe → EditProposal repair → Confirm Apply → Validate →
  Run 计数不变。

### 四服务

真实配置，无 temp DB / temp project root / loopback fake provider：

- Desktop `5173` → 200
- Community `5174` → 200
- Local `8771` `build_sha=4e3c2e6-slice4-dirty` /
  `local_0023_builder_harness_receipts` / `database_ready=true` / `status=ok`
- Community API `8772` `build_sha=a719813-interaction-v2-dirty` /
  `community_0008_plugin_registry` / `database_ready=true` / `status=ok`
- **Builder Model**：Moonshot / `kimi-k3` / `known` + `source=probe` /
  strict JSON Schema supported
- **Agent Runtime Model**：host default Moonshot / `kimi-k3` /
  `https://api.moonshot.cn/v1` / `configured=true`
- 真实 Projects 仍在：`dddd` / `test` / `New project`

### 剩余 Builder Phase 2 gaps

- 模块尚未做最终 release gate / Playwright CASE 1–3
- 现有工作区没有 Tool Agent，live permission repair 未在真实 Project 上点过
- 旧 Factory「平台试跑」(`FactoryTestRun`) 仍在；Slice 4 是 Builder Test Agent
- 不自动 behavioral repair、不 LLM judge、不 scheduled Run、不 Community publish

闭环：

```text
Build → Validate → Explicit Test Run → Observe → Explain
→ optional Repair Proposal → Confirm → Apply → Validate
→ explicit Run again
```

Builder Model ≠ Agent Runtime Model。

---

## Historical checkpoint（2026-09-20，Builder Harness Receipt = complete）


- Branch：`codex/agent-platform` → `origin/codex/agent-platform`
- HEAD：`aba074d` 之上本 checkpoint 提交 ProviderCapabilityProfile +
  BuilderHarnessReceipt（精确 SHA 以 git HEAD 为准）
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`
- 不要重开 Interaction Model V2 / Durable Conversation / AgentSemanticPlanV1 /
  SemanticPlanCompiler / ProviderCapabilityProfile / Harness Receipt
- 暂停：autonomous Run、Community redesign
- 下一步：Slice 4 Test Run → Observe → Explain → optional Repair Proposal →
  Builder Phase 2 release gate

### Builder Harness Receipt = complete

一次真实模型调用一条 `BuilderHarnessReceipt`。它回答「这次调用在什么受控
Harness / Provider 协议下发生」，不是 prompt 归档、不是 CoT、不是第二套
ProviderProfile、不是 operation timeline、不是 Chat 气泡。

```text
Conversation Message  ≠  BuilderOperationEvent  ≠  BuilderHarnessReceipt
≠  Proposal  ≠  Runtime Run
```

- 生命周期：准备 context → persist `prepared` → provider request →
  finalize `success`/`failed`。请求失败时 Receipt 已经存在。
- invocation_kind：`resolve_intent` / `interview` / `semantic_plan` /
  `semantic_plan_repair`。一个 operation 可有多条，按 sequence 排序。
- typed fallback：strict → json_object 是两次 invocation；两条 Receipt。
- 只存安全 metadata：policy/schema/snapshot hash、included/excluded
  枚举、当时 profile 摘要（id/model/endpoint/status/source/schema_profile）。
- 不存：system/developer/user prompt、conversation 全文、Project JSON、
  Knowledge/File 正文、密钥、Authorization、headers、provider body/response、
  hidden reasoning。
- snapshot hash 来自 Builder 实际可见的 canonical bounded metadata
  projection，不含 secret / timestamp / 绝对路径 / 正文。
- 历史不可变：finalize 后 Recheck / Project / Catalog 变化不改写旧 Receipt。
- Project scoped：conversation + operation + project 必须同时匹配；跨
  Project 读 404。无全局 receipt lookup。
- 无模型调用的 deterministic operation 可以没有 Receipt；UI 显示
  「模型调用：无」，不是错误。
- 不记录 Runtime evidence。`run_id` 字段留给 Slice 4，本轮未 start Run。

Activity → 默认折叠「构建详情」：Provider / Contract / Structured mode /
Policy / Context / Excluded / Status。hash 只在 Technical details。
Chat 不渲染 Receipt。

API：operation 详情附 `receipts`；另有
`GET /api/v1/projects/{project}/builder/conversations/{conversation}/operations/{operation}/receipts`。
迁移：`local_0023_builder_harness_receipts`。

### 证据

- 后端 focused：`test_builder_harness_receipts.py` +
  `test_builder_conversations.py` + `test_factory_client.py` +
  `test_factory_routes.py` + `test_capability_probe.py` +
  `test_provider_capability_profile.py` → **78 passed**
- Desktop focused：`BuilderActivityBlock.test.tsx` +
  `project-builder.test.tsx` + `local-client.test.ts` +
  `workbench-phase.test.ts` + `factory-conversation.test.tsx` → **82 passed**
- Desktop `tsc --noEmit` 通过
- `ruff check`（本切片相关）/ `ruff format --check` / `mypy`（170 files）/
  `git diff --check`：clean
- 未做全量 `make check`；未做 Playwright

### 真实 Moonshot 验收（一次，到 Proposal ready，未 Confirm）

- Project：`New project`
- 请求：「创建一个日程提醒整理 Agent。」
- conversation `01a0ba7f-b355-78b1-b742-9140807d2198`
- operation `waiting`，events 到 `builder.proposal.ready`
- messages：`user` + `assistant`（无 Receipt 气泡）
- `run_id=null`；未创建新 Agent（现有仍是 `礼物包装 Agent` /
  `中英文翻译 Agent`）
- 3 条 Receipt，全部 `success`：
  1. `resolve_intent` / `json_object` / `BuilderIntentV1`
  2. `interview` / `none`
  3. `semantic_plan` / `strict_json_schema` / `AgentSemanticPlanV1`
- Provider `moonshot` / model `kimi-k3` / profile `known` + `source=probe`
  / schema `mfjs`
- Excluded 含 knowledge_contents / project_file_contents / credentials /
  secrets / hidden_reasoning / raw_prompts / provider_response_bodies
- 刷新 conversation 与 receipts GET 均恢复 3 条；跨 Project 读 404
- DB/API/消息扫描：无 API key、无 Authorization、无 raw prompt、无
  provider body、无 Knowledge 正文
- 随后 Factory status 仍是 `known` / `probe`（generate 未改 capability truth）
- 不是 429

### 四服务

真实配置，无 temp DB / temp project root / loopback fake provider：

- Desktop `5173` → 200
- Community `5174` → 200
- Local `8771` `build_sha=aba074d-harness-receipt-dirty` /
  `local_0023_builder_harness_receipts` / `database_ready=true`
- Community API `8772` `build_sha=a719813-interaction-v2-dirty` /
  `community_0008` / `database_ready=true`
- Factory `configured=true`，Moonshot / `kimi-k3`
- 真实 Projects 仍在：`dddd` / `test` / `New project`

### 下一步

Slice 4 Explicit Test Run → Observe → Explain → optional Repair Proposal。
不要开始 Community redesign。

---

## Historical checkpoint（2026-09-19，ProviderCapabilityProfile = complete）

- Branch：`codex/agent-platform` → `origin/codex/agent-platform`
- HEAD：`aba074d`（dirty working tree，**未 commit / 未 push**）
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`
- 不要重开 Interaction Model V2 开发
- 当时暂停：Harness Receipt UI、Slice 4 Test Run、autonomous Run、Community redesign
- 当时下一步：Harness Receipt → Slice 4

### Builder Interaction Model V2 = complete

产品验收已关。最终 release gate caveat：

当前环境没有 Playwright，所以完整 browser CASE 1–3 没有全部自动化执行。

已有证据：Live Moonshot CASE 1 PASS；scripted provider CASE 2 / CASE 3 PASS；Desktop focused tests PASS；refresh / naming / missing capability / Recent 已验证；四服务真实配置正常。完整 Playwright acceptance 留到 Builder Phase 2 最终 release gate。

### 审计（半成品 → 本轮事实）

1. 类型定义：有。Python `ProviderCapabilityProfile` + TS 合同。本轮扩展了 identity / support / status。
2. 持久化：本轮起写入 `provider_capability_profiles`（`local_0022`）。此前只是每次从 host 推导。
3. 静态 + 有界 probe。未 probe 时 `source=static_known`。`POST /api/v1/factory/capability-probe` 才 probe。
4. Factory generate 读取 resolved profile（缓存优先，否则 static_known）。
5. `GET /api/v1/factory/status` 暴露 profile + 安全 `summary`。Settings 轻量显示。
6. model 切换：identity 变，旧 profile 不复用。
7. endpoint / base_url 变：fingerprint 变，旧 profile 不复用。Query 不进入 fingerprint。
8. 不把 `/models` 当能力证明。Probe 不调用 `/models`。listing ≠ capability。
9. Moonshot fallback 不再靠「读 403 body 里的 json_schema」。401/403/429/5xx/unknown 4xx 不 fallback、不把 capability 打成 unsupported。403 现为 `factory_forbidden`。只有 `schema_incompatible` / `response_format_unsupported` 才允许 strict → json_object。
10. 本阶段已补：synthetic probe、cache identity、invalidation、typed failure、Factory 消费 profile、无用户数据、无密钥持久化。未做 Harness Receipt / Slice 4 / Playwright gate。

### ProviderCapabilityProfile

只回答：「这个 Provider + Model + Endpoint 支持怎样的模型请求协议？」

不回答：「Veyra Agent 应该是什么？」Canonical 仍是 AgentSemanticPlanV1 → SemanticPlanCompiler → AgentBlueprint / AgentSource。

- 身份：`provider_id` + `model` + `endpoint_kind=chat_completions` + `base_url_fingerprint` + `probe_version=semantic-plan-ok-v1`
- Probe：固定 prompt `Return an object with field "ok".` + `{ok: boolean}` schema。无 Project / Knowledge / Files / Conversation / 用户 Prompt。
- 顺序：minimal strict JSON Schema → 仅 schema/response_format 不兼容时才 `json_object` → 否则 unsupported/unknown。401/403/429 停止。429 = `status=inconclusive`，不改已有 capability truth。
- Generate：`strict_json_schema_support=supported` → strict SemanticPlan schema；否则 `json_object_support=supported` → json_object + server parse + AgentSemanticPlanV1 校验；都 unsupported → typed `factory_structured_output_unsupported`。未 probe 时沿用 Moonshot static_known / 其它主机 fail-closed json_object。
- 不把 Markdown regex 截 JSON 当 Draft。
- Settings 只显示 Provider / Model / Structured output / Schema / JSON object fallback / Profile status / Checked + Recheck。Builder Activity 不刷 profile 加载。

### 证据

- 后端 focused：`test_provider_capability_profile.py` + `test_capability_probe.py` + `test_factory_client.py` + `test_factory_structured_schema.py` + `test_factory_routes.py` → **53 passed**
- Desktop：`local-client.test.ts` + `factory-conversation.test.tsx` + `factory-capability-summary.test.tsx` → **41 passed**；`tsc -b` 通过
- `ruff check` / `ruff format --check`：本切片相关文件通过
- `mypy`：169 files，无问题
- `git diff --check`：clean
- 迁移头：`local_0022_provider_capability_profiles`
- 未做全量 `make check`；未做 browser E2E；未 commit；未 push

### 真实 Moonshot capability probe（一次，有界）

- `POST /api/v1/factory/capability-probe` → HTTP 200
- 不是 Builder create，未创建 Agent
- 结果：**known / probe / strict JSON Schema supported**
  - Provider：Moonshot
  - Model：kimi-k3
  - Structured output：Strict JSON Schema
  - Schema profile：MFJS
  - JSON object fallback：Supported（generate 大 SemanticPlan schema 仍允许一次 schema 400 fallback）
  - Profile status：Known
  - `strict_json_schema_support=supported`
  - `json_object_support=unknown`（strict 已成功，未再 probe json_object）
  - `source=probe`，`probed=true`
- 随后 `GET /api/v1/factory/status` 读缓存，仍是 Known，没有第二次 live probe
- 不是 429，不是 inconclusive，不是 unsupported

### 四服务

真实配置，无 temp DB / temp project root / loopback fake provider：

- Desktop `5173` → 200
- Community `5174` → 200
- Local `8771` `build_sha=aba074d-provider-profile-dirty` / `local_0022` / `database_ready=true`
- Community API `8772` `build_sha=a719813-interaction-v2-dirty` / `community_0008` / `database_ready=true`
- Factory `configured=true`，`api.moonshot.cn`，`kimi-k3`
- 真实 Projects 未改

### 当时下一步

Harness Receipt（现已完成）。不要开始 Slice 4 / Community redesign / commit / push。

---

## Historical checkpoint（2026-09-19，Builder Interaction Model V2 = complete）

- Branch：`codex/agent-platform` → `origin/codex/agent-platform`
- HEAD：`a719813`（dirty working tree，**未 commit / 未 push**）
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`
- 暂停：ProviderCapabilityProfile 继续产品化、Harness Receipt UI、Slice 4 Test Run
- 下一步顺序：ProviderCapabilityProfile → Harness Receipt → Slice 4

### Interaction Model V2（产品验收已关）

```text
Conversation Message  ≠  Builder Operation / Activity  ≠  Proposal  ≠  Runtime Run
```

- Chat 主时间线只保留 user / assistant / clarification / failure / result
- 每个 BuilderOperation 一个 Activity；完成默认折叠；失败 Retry 属于 operation
- Proposal / Canvas 在 Workbench；不再追加「方案已准备好」聊天消息
- Confirm / Apply / validation 更新原 operation；final result 只写一次
- Recent 两阶段标题：provisional（第一条 user message，无额外模型调用）→ 仍为 provisional 时才升级 `suggested_name`；失败不再叫 `Chat`
- Apply：`suggested_name` → `agent_candidate_identity` → Draft / Project tree；CJK slug 为 `agent-{hash}`
- 没有前端 fake timer；不持久化 raw reasoning / CoT / provider body
- `factory_rate_limited` 保持 typed；UI 显示 Rate limited；不因此改 schema / 换模型 / 无限重试

### 证据

- 后端：`test_builder_conversations.py` + title unit + compiler extra-outputs / naming → **32 passed**（本轮 focused）
- Desktop：`project-builder.test.tsx` + `BuilderActivityBlock` + workbench-phase + local-client missing-capability → **76 passed**；`tsc -b` 通过
- 迁移头：`local_0021_builder_operation_events`
- 四服务（真实配置，无 temp DB / loopback provider / fake key）：
  - Desktop `5173` → 200
  - Community `5174` → 200
  - Local `8771` `build_sha=a719813-interaction-v2-dirty` / `local_0021` / `database_ready=true`
  - Community API `8772` `build_sha=a719813-interaction-v2-dirty` / `community_0008` / `database_ready=true`
  - Factory `configured=true`，`https://api.moonshot.cn/v1`，`provider_family=moonshot`
  - 项目仍在：`dddd` / `test` / `New project`

#### Live Moonshot

- CASE 1（`New project`，「创建一个中英文翻译 Agent。」）：**PASS**
  - conversation `01a0b55b-a9cf-7195-b163-205624fc0103`
  - kinds：`user` + `assistant`（无 Proposal ready 气泡）
  - events 到 `builder.proposal.ready` → confirm → apply → `builder.operation.completed`
  - title / Agent 名：`中英文翻译 Agent`（不是 Generated Agent）
  - slug：`agent-0f68d95b`（现有 CJK hash 合同）
  - result 一次；waiting / completed 刷新可恢复
- 失败会话 `Chat` 标题：activity/get 已现场修成 `中英文翻译 Agent`（无额外模型调用）
- `test` 项目此前浏览器创建「中文转德语翻译」仍在；不是 Generated Agent
- HTTP 429 是 provider rate limit，不是 V2 / Compiler / schema 缺陷

#### Deterministic provider（同一条真实 Builder path）

- CASE 2 会议纪要：scripted turn → Semantic Plan → Compiler → Apply；名称 `会议纪要整理 Agent`；「摘要 / 决定 / 待办」保留在 system prompt（canonical 仍是单 Output node，未为验收改成多 Output）
- CASE 3 GitHub missing capability：typed `factory_missing_capability`；不创建 Agent；不 Catalog auto-add；Workbench 可展示 missing；前端接受 `missing_capability` proposal action，不再把合法结果打成 invalid proposal
- 本轮 **没有** 再对 Moonshot 发 CASE 2/3（遵守一次有界 live probe）

#### Browser

- 本环境无 Playwright/Chrome 自动化
- 产品逻辑：live API CASE 1 + Desktop 测试 + 用户此前 `test` 项目截图
- `New project` 另有一条 waiting 会话 `01a0b55a-...`（title `中英文翻译`，candidate 来自 suggested_name）；未代为 Confirm，避免重复 Apply

未做全量 `make check`；未 commit；未 push。

---

## Current checkpoint（2026-09-18，Builder Interaction Model V2 implementation = complete；live browser create 未关）

- Branch：`codex/agent-platform` → `origin/codex/agent-platform`
- HEAD：`a719813`（dirty working tree，**未 commit / 未 push**）
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`
- 暂停：ProviderCapabilityProfile 继续产品化、Harness Receipt UI、Slice 4 Test Run

### Interaction Model V2（domain 已落地）

```text
Conversation Message  ≠  Builder Operation / Activity  ≠  Proposal  ≠  Runtime Run
```

- Chat 主时间线只保留 user / assistant / clarification / failure / result
- 每个 BuilderOperation 投影成一个可折叠 Activity block；进度来自 `builder_operation_events`
- Proposal / Canvas / Resource plan 在右侧 Workbench，随 server 阶段打开
- Apply 使用 Semantic Plan `suggested_name`；CJK slug 为 `agent-{hash}`，不再默认 Generated Agent
- Recent 标题优先 `suggested_name`；失败且尚未出计划时保持 `Chat`，不用整句 prompt
- 刷新后 Conversation + events + Proposal 可恢复
- 没有前端 setTimeout 假进度；compiler 一次性产出 Blueprint，Canvas 显示已编译结构
- Create 与 Edit 共用 Activity / Workbench / Confirm / Result；`target_kind` 预留 agent | workflow
- 已在 head 的真实库启动时跳过 Alembic exclusive upgrade，避免 8771 卡在 `command.upgrade`

### 证据

- 后端：`test_builder_conversations.py` + compiler A–D + naming/deconflict + integrity skip-upgrade → 本轮相关 **passed**
- Desktop：`project-builder.test.tsx` + workbench-phase + factory-conversation + local-client；`tsc -b` 通过（含 BuilderActivityBlock）
- 迁移头：`local_0021_builder_operation_events`
- 四服务（真实配置，无 temp DB / loopback provider）：
  - Desktop `5173` → 200
  - Community `5174` → 200
  - Local `8771` `build_sha=a719813-interaction-v2-dirty` / `local_0021` / `database_ready=true`
  - Community API `8772` `build_sha=a719813-interaction-v2-dirty` / `community_0008` / `database_ready=true`
  - Factory `configured=true`，`api.moonshot.cn`，`provider_family=moonshot`
  - 项目仍在：`dddd` / `test` / `New project`
- 对 `New project` 的真实 Kimi CASE 1 三次均 `factory_rate_limited` HTTP 429。失败路径符合 V2：仅 `user`+`failure`，events 以 `builder.operation.failed` 结束，刷新可恢复，未创建 Agent。Recent 现有三条 `Chat` 失败会话。
- Isolated Chrome 验收脚本未能在本环境执行（自动化被拦截）；Desktop 仍需 Community 登录后才能进入 Chat UI。

不要把「实现完成」写成「浏览器 CASE 1–2 创建成功」。

---

## Current checkpoint（2026-09-18，ProviderCapabilityProfile = complete / paused）

- Branch：`codex/agent-platform` → `origin/codex/agent-platform`
- HEAD：`a719813`（dirty working tree，**未 commit / 未 push**）
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`
- 暂停：Harness Receipt UI、Slice 4 Test Run

### ProviderCapabilityProfile

Factory structured output 按主机声明，不再默认所有 OpenAI-compatible 主机都是 Moonshot MFJS。

- `GET /api/v1/factory/status.capability_profile`：`source=host_defaults`，`probed=false`
- Moonshot（`api.moonshot.cn` / `api.moonshot.ai` 及其子域）：`json_schema` + MFJS + strict + 一次 schema 400 → `json_object`；发送 `reasoning_effort`
- 其它主机：`json_object` only，无投影、无 fallback、不发 `reasoning_effort`
- 不是 live `/models` structured-output 探测，不是 Run，不含密钥

### 证据

- 后端：`pytest` `test_provider_capability_profile.py` + `test_factory_client.py` + `test_factory_structured_schema.py` + `test_factory_routes.py` → **30 passed**
- Desktop：`local-client.test.ts` + `factory-conversation.test.tsx` → **38 passed**（含缺失/不一致 profile 拒绝）
- `ruff check` / `ruff format --check`：本切片相关文件通过
- `mypy`：capability_profile / client / service 无问题
- Desktop `tsc -b` 当时仍有 BuilderActivityBlock 错误；后续 V2 已修
- 未做全量 `make check`；未 commit

---

## Historical checkpoint（2026-09-18，Builder Interaction Model V2 初版落地，浏览器未关）

- Branch：`codex/agent-platform` → `origin/codex/agent-platform`
- HEAD：`a719813`（dirty working tree，**未 commit / 未 push**）
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`
- 暂停：ProviderCapabilityProfile、Harness Receipt UI、Slice 4 Test Run

### Interaction Model V2

```text
Conversation Message  ≠  Builder Operation / Activity  ≠  Proposal  ≠  Runtime Run
```

- Chat 主时间线只保留 user / assistant / clarification / failure / result
- 每个 BuilderOperation 投影成一个可折叠 Activity block（server-owned events）
- Proposal / Canvas / Resource plan 在右侧 Workbench，随真实阶段打开
- Apply 使用 Semantic Plan `suggested_name`（不再默认 Generated Agent）
- Recent 标题优先用 suggested_name；Runtime History 仍只属于右上「历史」
- 刷新后 Conversation + Activity events + Proposal 可恢复
- 没有前端 setTimeout 假进度，也没有逐步飞入节点的假执行史

### 证据

- 后端窄测：`test_builder_conversations.py` + compiler/factory naming/A–D compile
- 前端：Desktop Durable Chat / Activity / Workbench / local-client / app Recent
- 迁移头：`local_0021_builder_operation_events`
- 未做全量 `make check`；未 commit

---

## Current checkpoint（2026-09-17，Knowledge V1 = complete / released）

- Branch：`codex/agent-platform` → `origin/codex/agent-platform`
- Knowledge V1 code SHA：`83518068937271c4a0372674284782b56500e47c`
- Release/acceptance SHA：见本文末尾记录的最新提交（文档与浏览器验收证据）
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`

### Knowledge V1 闭环

```text
Source ingest → truthful state → Project ownership → Agent binding → immutable pin
→ deterministic index → Runtime retrieval → persisted evidence
→ Run Detail citation/evidence → stale/remove safety
```

本地 UTF-8 txt/md 上传 → 后端唯一事实的 ingest/parse/index 状态 → 显式构建确定性分块索引
→ Agent 绑定并固定 source hash（不静默升级）→ 仅绑定范围内的词汇检索 → 有界模型上下文
→ Run `knowledge.context` 证据（reference / source hash / chunk / 行号 / rank / score /
query_hash / hit_count，不存原始 query 与正文）→ Run Detail 引用与 hash 门控片段预览
→ 内容漂移只转 stale 不自动重建 → 使用中删除被拒绝。

### Validation（发布门禁，`560a912` 代码即 `8351806`）

- Focused review：按 24 项边界逐条核对 Knowledge diff，未发现真实 bug，未改产品代码
- `env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`：452 passed；Ruff、mypy、lock checks
- `cd web && npm test`：Desktop 309 passed（41 文件），Community 15 passed
- `npm run typecheck`、`npm run build`：通过（Desktop 主 chunk warning 保留）
- 隔离浏览器 E2E（Chrome + playwright-core）：**27 checks / 0 failed**，覆盖
  upload → not_indexed → Build index → indexed/chunk_count → bind → commit → Run →
  evidence → excerpt `ORBIT-731` → 精确 run_id 刷新不重跑且证据不变 →
  空检索诚实提示 → stale 拒绝旧片段且不泄漏新内容 → 使用中删除 409
- E2E harness 在仓库外临时目录，使用临时 SQLite、临时 Project 根和 loopback 脚本 provider；
  脚本内断言 `root_path` 与 `runtime/status.model_base_url`，未调用真实模型
- GitHub Actions billing 仍是外部阻塞；本轮未 rerun CI，不写成 CI PASS

### 本轮的一次真实事故与处理

隔离服务最初通过 `nohup ... &` 启动，会在 Shell 调用结束后被回收；期间服务被按默认配置
重启，导致 E2E setup 在**真实** Project 根建了 4 个 `Knowledge E2E*` 测试项目。所有 E2E
在登录步骤即中止，未执行任何 Run、未调用外部模型。经用户明确授权后按产品 DELETE 路径将
这 4 个项目移入废纸篓，工作区恢复为 `dddd` / `test` / `New project`。

教训：隔离服务必须作为长驻作业启动，并在跑 E2E 前用 `root_path` 与 `runtime/status`
在带内断言隔离，不能只看 `/api/v1/health`。macOS 上 Project 存储根要用 `/private/tmp`，
因为产品正确地拒绝符号链接根目录。

第二次同源事故：用 `source env.sh` 设置隔离变量后，**这些变量在同一 shell 会话里跨命令
保留**。删除临时目录后重启服务，两个后端指向了已删除的临时库——本地库被自动重建成空的，
Community 库无迁移记录（`database_ready: false`），界面显示空项目列表，Runtime 还指着
已停的 loopback provider 和假 key。真实数据未丢失，用 `env -u` 显式重启即恢复。

固化流程：

- 绝不用 `source` 设置隔离环境变量；只用 `env VAR=... command` 内联传递
- 多行命令不要用反斜杠续行传给 shell 工具（会被折叠成字面转义，把相邻变量粘成一个）
- **每个大模块收尾后重启整个项目**（5173 Desktop、5174 公开站、8771 Local、8772 Community）
  并核对界面真实可见，不只核对 health；Vite 必须从各自 app 目录启动并带 `--strictPort`，
  否则会从仓库根目录启动并回落到别的端口，出现「服务在跑但页面打不开」

### 未来边界（都不是 Knowledge V1 blocker）

embeddings、vector search、reranker、GraphRAG、PDF/OCR、web ingestion、
historical Knowledge artifacts、sentence-level attribution。不要为“更完整”扩这些能力。

### Next major module

**Builder Phase 2 / Build loop integration。**

其后仍是 Community 分享闭环（真实发布/导入预览，去掉公开 Web 静态 `communityEntries`）。
不要重开 Resource Library / Runtime V1 / Knowledge V1。

---

## Builder Phase 2 窄审计（2026-09-17，基于 `a719813` 实际代码）

范围只覆盖 Builder Phase 1 到 Knowledge / Resource / validation / Runtime 的连接点，
不是全仓审计。结论全部来自代码与现有测试，不含计划。

### A. Builder Harness 当前实际能看到哪些 Project facts

`local/builder/harness.py` 的 `messages()` 构造一份 typed context，上限
`MAX_CONTEXT_BYTES = 400_000`，超限抛 `ContractValidationError`（可见失败，不静默截断）：

- `project`：`project_id` / `name` / `description` / `manifest_hash`
- `inventory.agents` / `.workflows` / `.knowledge`：来自 `project_summary`，逐项剔除 `source_path`
- Agent/Workflow 额外注入：`draft{revision, etag, source_file_hash}`、
  `nodes[id, component_type, agent_id, version_id]`、`transitions`、`lock`、
  `versions[version_id, source_hash, behavior_hash]`
- `project_bindings`：`ProjectResourceBinding.to_dict()` → `reference` / `content_hash` / `source`
- `files`：`list_files(project_id)`，仅路径清单
- `resources`：Catalog `factory_snapshot()` + `content_hash` / `origin` / `factory_selectable`
- `unselectable_resources`：`reference` / `kind` / `availability` / `runtime_status`
- `target`（edit_source 模式含完整已保存 source + revision/etag）、`conversation`
- `authority`：`writes=explicit_confirmation_only`、`file_contents=not_loaded`、
  `resource_creation=not_supported_by_this_adapter`、`multi_object_mutation=False`、
  `runtime_host_configuration=not_checked`、`runtime_execution=not_performed`

`tests/integration/local/test_edit_proposal_routes.py:428-429` 断言 Knowledge 正文
（`CONTENT_NOT_FOR_BUILDER`）和主机路径都不出现在 context 中。

### B. Knowledge V1 是否已经进入 Builder context

**元数据层面：已经进入，比预期完整。** `project_summary` 的 knowledge 走
`_knowledge_listing`，返回 `knowledge_id` / `slug` / `name` / `description` / `version` /
`source_file_hash`，以及完整 `processing`（`origin`、`filename`、`media_type`、
`uploaded_content_hash`、`content_hash`、`ingest_status`、`parse_status`、
`index_status`、`chunk_count`、`failure_reason`、`updated_at`）。Harness 只剔除
`source_path`，因此索引状态与内容 hash 都对模型可见。正文不可见，符合
`PROJECT_DESIGN.md` §6.0「Knowledge and Files are metadata/bindings only」。

**解析层面：没有进入。** `BuilderTarget.kind` 只有 `Literal["agent", "workflow"]`，
`resolution.py` 的 `inventory` 也只遍历 `("agent", "workflow")`。服务端没有任何
Knowledge 解析或歧义澄清，Knowledge 选择完全交给 `edit_source` 的自由生成。

### C. Project Resources 的 ownership/readiness/pin 是否已经进入 Builder context

**部分进入。** ownership 与 pin 有：`project_bindings` 给出 `reference` + `content_hash`。
readiness 只能间接推导：`resources` / `unselectable_resources` 带 `availability` 与
`runtime_status`，需模型自行按 reference 关联。context 中**没有**按 Project 投影的
readiness，也没有 `bound_content_hash` 漂移信号——漂移检查存在于校验期的
`inspect_agent_dependencies`（`project_binding_status=stale`、`resource_unbound`），
不在模型看到的 context 里。`PROJECT_DESIGN.md` §5.0 要求 Project Resource Library 报告
`current/stale/unbound/builtin`，Builder context 目前没有这一层投影。

### D. Builder 当前能否生成合法 knowledge_refs + source.lock

**机制上可以，但完全依赖模型正确抄写 64 位十六进制 hash，且缺少解析与就绪展示。**

- `contracts/schemas/agent-source.schema.json:620-626` 含 `knowledge_refs`
  （`uuid7@semver` 正则），`edit_source` 模式把该 schema 交给模型
- context 暴露每份 Knowledge 的 `source_file_hash`，模型可据此填 `lock`
- 写错会被拦：`_knowledge_check` 判 `lock_mismatch`（version 或 hash 不符）、
  `context_not_declared`（ui binding 未在 knowledge_refs 声明）、
  `context_too_large`（>8 份），`_validate` 抛错后进入有界 repair loop，
  三次失败则 `edit_generation_invalid`，Draft 不变 → **fail closed，不会写坏 source**

**与 Studio 路径的 parity 缺口：** `bindKnowledgeToAgent`（前端）写三处——
`extensions.veyra.knowledge_refs`、`lock[reference] = source_file_hash`、以及
`ui.bindings[<id>] = {kind:"knowledge", reference, x, y}`。Builder 若只写前两处，
校验仍通过（bindings ⊆ refs 成立），但 Studio 左栏 Knowledge 卡片不会出现，
形成用户可见的不一致。

**测试覆盖：0。** 没有任何测试覆盖 Builder 驱动的 Knowledge 绑定。

### E. Builder 当前能否生成合法 Tool.uses + Project resource lock

**可以，且有测试证明（针对 `skill_refs`）。**
`test_builder_project_context_reuses_resource_and_changes_real_graph` 完整验证了
绑定 Project 资源 → 模型复用该 reference → `lock[reference] = descriptor.content_hash`
→ apply → Draft 真实改变、revision+1、project summary 更新、apply 后 validate 通过。
`_validate` 额外强制：**新增**依赖必须 `factory_selectable` 且 availability 不属于
`quarantined/disabled/unavailable`，否则「New dependencies must be selectable Factory
resources」。`test_unknown_dependency_is_repaired_and_permission_diff_is_real` 覆盖修复。

已证明的是 `skill_refs` 路径。`node.uses`（Tool）走同一 `add(node.uses, "tool")` 与同样的
lock 要求，但**没有** Builder 生成 `Tool.uses` 的测试证据。

### F. Apply 后是否真的走相同的 backend validation/security boundary

**是，同一条边界，无旁路。** `EditProposalService.command("apply")`：

1. `confirm` 必须为真，否则 `edit_confirmation_required`
2. 重跑 `_validate`，结果必须与审查时**逐字段相等**，否则 `DraftConflict`
   （"Dependencies changed since review"）
3. `stale` 为真直接 `DraftConflict`
4. 调 `LibraryService.replace_draft` / `replace_workflow_draft`，传入审查时的
   revision/etag 与 `apply_key` 幂等键

`replace_draft`（`library/service.py:148-246`）内部依次检查：identity 匹配、
`source_file_hash != current_disk_hash` → "source changed outside Studio"、etag、
revision，然后 `_validate_tool_bindings` + `_validate_knowledge_ownership`，再走
write intent + atomic write + 失败回滚。**与 Studio 保存草稿完全同一路径。**

### G. Apply 后 Studio / Project tree 是否真实刷新

- **Project tree：真实刷新。** apply/undo 后 `BuilderTarget` 依次 `getDraft` →
  `validate` → `upsertProject(await api.getProject(...))`；
  `project-builder.test.tsx` 断言 tree 显示新 Agent 名
- **Studio：不就地刷新。** Builder 面板只给 Studio 链接；Studio 在挂载时重读 Draft，
  所以导航过去能看到已应用的 source，但两处同开时不会实时同步
- **Reject 刻意不重读、不校验**（`action !== "reject"`）

### H. Builder 是否能知道 validation failure

**两层都真实存在，但都没有变成 Builder 可读的 typed feedback。**

- 生成期：`_validate` 抛错 → 错误字符串作为 user message 追加，模型在
  `repair_attempts` 内重试。模型确实看到失败，但是**散文**，不是 typed code
- Apply 后：UI 重读 Draft 并 `validate`，在「应用后验证 / Post-apply validation」
  区渲染结构化 `DependencyReport`（name / reference / status badge / detail /
  `project_binding_status` stale 提示）
- 但客户端把 `valid !== true` 的响应直接判为 `invalid_response` 抛出
  （`local-client.ts:798-804`），API 错误只以原始 `Error.message` Alert 呈现
- **缺口：** `knowledge_unbound` / `resource_unbound` / `resource_lock_mismatch` /
  permission missing / invalid graph 这类 typed code 从未作为结构化反馈回到 Chat，
  也没有「validation failure → 生成修复 Proposal」的闭环

### I. Builder 是否能知道 Run/test failure

**完全不能。** Builder 相关文件中没有 `startRun`、`/runs` 调用或任何 run 状态 UI。
Harness 明确声明 `runtime_execution=not_performed`、
`runtime_host_configuration=not_checked`。只有运行**前**依赖检查，Run evidence
从不进入 Builder。这与 `PROJECT_DESIGN.md` §6.0「Runtime descriptor support is not
host configuration readiness or a successful Run」一致，但意味着 Build Loop 的
Run/Observe/Repair 段目前不存在。

### J. 当前第一个真实用户断点

以「让这个 Agent 使用我的毕业论文资料」为准，按用户遇到的顺序：

1. **目标解析依赖显式选择。** `focus` 仅在 Chat 作用域选中对象时下发
   （`ProjectBuilderConversation.tsx:48`）。全新 Project Chat 未选中时，
   `basis=context` 会被拒 → clarification。这是安全的正确行为，不是缺陷
2. **没有 Knowledge 解析与歧义澄清（首个真实断点）。** resolver 只解析
   agent/workflow，Knowledge 交给自由生成。面对
   `毕业论文.md` 与 `毕业论文-旧版.md` 模型会静默挑一个，违背「不要猜」
3. **Proposal 不展示 Knowledge 就绪状态。** `_knowledge_check` 只比对 version 与
   content hash（与 §7.3 现有设计一致，**不是既有 bug**），因此绑定
   `not_indexed` / `stale` 的 Knowledge 会被判 `ready`，用户不会被告知运行前必须
   Build index。这同时是 Runtime 陷阱：`read_knowledge_context` 会在真正 Run 时抛
   `knowledge_not_indexed` / `knowledge_index_stale`
4. **lock 正确性依赖模型抄 sha256。** fail closed，但会浪费 repair 次数并可能
   以 `edit_generation_invalid` 死路收场
5. **`ui.bindings` parity。** Builder 产出可能缺 Studio Knowledge 卡片绑定

**结论：Knowledge binding 确认是 Phase 2 Slice 1。** 缺的是服务端 Knowledge 解析 +
歧义澄清 + Proposal 就绪展示 + 服务端计算 lock，复用既有
`AgentSource.knowledge_refs` / `source.lock` / Project Knowledge ownership / validation，
绝不新建第二套 Knowledge binding 存储。

---

## Builder Phase 2 Slice 1 checkpoint（2026-09-17，未提交）

自然语言 Knowledge 绑定已落地并在运行中的服务上可见。**未 commit / 未 push**，
按约定 Builder Phase 2 模块完成后统一发布。

### 设计要点

模型既不挑 Knowledge 也不抄 hash。新增 `local/builder/knowledge_binding.py`：
`resolve_knowledge` 做确定性匹配、`bind_knowledge` 构造候选 source、
`knowledge_readiness` 投影索引状态。`EditProposalService.create_knowledge_binding`
把它塞进**既有** EditProposal 信封，因此 confirm / reject / undo / stale /
revision-ETag / `replace_draft` 全部原样复用，没有第二条写入路径。

解析语义是双向的：先取用户实际输入里最具体的那个别名作为 mention，再看有多少
文档的名字包含它。所以「毕业论文」在同时存在「毕业论文-旧版」时是 **ambiguous →
追问**，而「毕业论文-旧版」唯一命中。`document.md` 是所有 text 创建的 Knowledge
共享的占位名，只有 upload 来源才把 filename 当别名，避免英文句子里的 "document"
把所有资料都变成候选。

### 文件范围

- 新增 `backend/src/veyra_agent_platform/local/builder/knowledge_binding.py`
- `local/factory/edit_service.py`：`create_knowledge_binding` + `KnowledgeBindingUnresolved`
- `local/api/factory/edit_routes.py`：`POST .../edit-proposals/knowledge-binding`，
  歧义/未命中映射为 422 `knowledge_mention_ambiguous` / `knowledge_mention_unresolved`
- `web/packages/api-contracts/src/local.ts`：`KnowledgeBindingPlan` / `CreateKnowledgeBindingRequest`
- `web/apps/desktop/src/api/local-client.ts`：`createKnowledgeBindingProposal` + 校验解析
  （`runnable` 必须等于 `index_status === "indexed"`，自相矛盾的 readiness 直接拒收）
- `features/builder/EditProposalPanel.tsx`：Knowledge 绑定摘要（身份、锁定 hash、
  就绪徽章、片段数、需先构建/重建索引的告警、Draft-only 影响说明）
- `features/builder/ProjectBuilderConversation.tsx`：edit 意图先试确定性绑定，
  `unresolved` / `already_bound` 回落到既有 LLM 提案，`ambiguous` 在聊天里追问
- `tests/integration/local/test_builder_knowledge_binding.py`（新增 8 项）
- `tests/scaffold/test_composition.py`：登记新路由（修 fixture，不放宽产品契约）
- `web/apps/desktop/src/api/edit-proposals.test.ts`：新增 6 项 wire 断言

### 验证结果

- `pytest tests/integration/local/test_builder_knowledge_binding.py`：8 passed
- Builder/Knowledge 回归：`test_edit_proposal_routes` + `test_builder_resolution` +
  `test_agent_knowledge_bindings` + `test_composition` 合计 75 passed
- `ruff check backend tests`、`ruff format --check backend tests scripts`：通过
- `mypy`：158 source files，无问题
- `npm run typecheck`（Desktop + Community）：通过
- `npm run test:desktop`：315 passed / 41 files（原 309，新增 6）
- 确定性测试不接触 provider：`ScriptedKimiTransport` 全程为空，
  `test_single_match_...` 断言 `not transport.calls`
- 未跑：`make check` 全量、浏览器 E2E（按约定留到模块收尾）

### 覆盖到的 Slice 1 测试要求

单一匹配 resolve、多匹配 clarify、跨 Project 不可达、proposal 含 target +
Knowledge identity/hash、确认前无 mutation、Apply 写入 refs + lock、apply 后
validation 通过且 knowledge 依赖为 ready、`not_indexed` 可见但不自动构建、
`stale` 可见且不自动重建、revision 冲突保留用户工作、Reject 无 mutation、
Undo 恢复上一版 Draft、无 secret 泄漏、确定性测试无外部 provider。

**未覆盖：** Studio reload 看到绑定（后端已断言 draft 落盘，浏览器层留到模块收尾
E2E）；`already_bound` 回落路径没有独立前端测试。

### 服务状态（Slice 1 重启后）

Desktop `5173` pid 20769、公开站 `5174` pid 21032、Local `8771` pid 42557
（`build_sha=a719813-slice1-dirty`，未提交代码故意用 dirty 标识）、
Community `8772` pid 23160。四个面 200，新路由已在 OpenAPI 中注册，
真实工作区仍是 `dddd` / `test` / `New project`。

### Slice 2 候选（尚未开始）

Resource binding：「让这个 Agent 可以读取项目文件」→ Project Resources 的
`filesystem.read` → readiness / bound hash → Proposal → `Tool.uses` + lock +
required permissions → validate。必须复用 Resource Library V1，不自动 Add 到
Project、不自动授权、不自动升级 stale、不生成假 Tool；资源尚未 Project-bound 时
Proposal 必须显式声明这是额外的 Project mutation。

另外两个已知缺口留待后续 slice：typed validation failure → Builder 可读反馈 →
修复 Proposal（审计 H），以及 Run/Test observe → repair（审计 I）。

---

## Builder Phase 2 Slice 2 Resource binding 窄审计（2026-09-17）

范围只覆盖 Project 已绑定 Resource → Agent Tool 所需路径，不重审 Resource Library V1。

1. **Builder inventory 已包含 Project Resources，但只是原始 binding。**
   `BuilderHarness.messages()` 的 `project_bindings` 来自
   `ProjectResourceBinding.to_dict()`，包含 `reference` / `content_hash` / `source`；
   `resources` 与 `unselectable_resources` 是另一份全局 Catalog 快照。
2. **必要事实分散存在，尚未形成 Project-owned 投影。** 精确 version 在 `reference`
   中；Project pin 以 `content_hash` 命名，而不是 `bound_content_hash`；Catalog
   descriptor 有 `availability` / `runtime_status` / `required_permissions`。
   Builder context 没有 Resource Library API 已有的 `scope=project`、
   `binding_status=current|stale`、`bound_content_hash`、host readiness 与
   `blocking_reasons` 单条投影，需模型自行关联两份数据。
3. **全局 Catalog 与 Project ownership 在存储/API 上明确分离，在 Builder 选择上尚未
   强制。** `ProjectResourceService.list()` 只有 manifest binding 才标
   `scope=project`；全局存在不等于 Project 已选。但 Phase 1 的自由 source 生成仍可
   引用全局 descriptor，最后依赖校验才以 `resource_unbound` 拒绝。
4. **Studio 当前 Tool binding 语义明确。**
   `newCatalogNode()` 生成 `{component_type:"Tool", uses:resource.reference}`；
   `grantCatalogResource()` 用 `projectToolHash()` 强制读取
   `scope=project` 的 `bound_content_hash` 写入 `source.lock`，并只合并 descriptor
   的 `required_permissions`；`attachCatalogResource()` 再写节点和位置。
   Studio 插入已有图时通过 `insertFlowNodeOnEdge()` 拆边，保持节点可达。
5. **`replace_draft` 是 Resource ownership 的最终写入边界。**
   `_validate_tool_bindings()` 收集所有 Tool `node.uses`，要求 reference 存在于
   当前 Project manifest binding，且 `source.lock[reference]` 必须等于 Project pin；
   否则分别为 `resource_unbound` / `resource_lock_mismatch`。之后才 atomic write。
6. **校验层已覆盖所需状态。** `inspect_agent_dependencies()`：
   无 Project binding → `resource_unbound`；Agent lock ≠ Project pin →
   `lock_mismatch`（API 写边界映射为 `resource_lock_mismatch`）；Project pin ≠
   当前 Catalog hash → `project_binding_stale`；live projection 的
   `requires_configuration` → `configuration_required`；其它不可执行状态 →
   `runtime_unavailable`；缺最小权限 → `permission_denied`。它同时返回
   `bound_content_hash`、`locked_hash`、`required_permissions` 和 blocking reasons。
7. **现有 EditProposal 足以承载 Tool mutation。** `candidate_source`、结构化
   `changes`、`permission_changes`、dependency `validation`、Draft-only `impact`
   已存在；缺的是一个直接展示 Project pin/readiness/required permissions 的
   Resource binding 摘要，不需要新 Proposal 或新写入协议。
8. **Apply 后 Studio 能看到 Tool。** `BuilderTarget` 在 apply 后重读真实 Draft、
   validate 并 refresh Project；Studio 导航/重新挂载会读相同 Draft。Project Chat
   不会原地嵌入 Studio，但没有缓存的第二份 source。
9. **不存在第二套 Resource binding storage。** Project ownership 真相只有
   `project.vproject.yaml.resources`；Agent usage 真相只有 Tool `uses` +
   `source.lock` + permissions。Builder proposal 存的是候选与审查收据，不是 binding。
    10. **Slice 2 第一个真实断点：** 模型仍在两份分散 context 中选择 Resource identity
    并抄 hash。它不能确定性理解“读取项目文件”，也不能在 global-only / cross-Project /
    多候选时可靠阻止猜测；Proposal 也没有明确展示 Project pin、stale/readiness 和
    最小权限。Slice 2 应沿 Slice 1：服务端只从 `scope=project` 投影解析
    `filesystem.read`，服务端使用 `bound_content_hash` 构造 Tool/lock/permission
    候选，再复用现有 EditProposal confirm/apply/reject/undo。

---

## Builder Phase 2 Slice 2 checkpoint（2026-09-17，未提交）

确定性 Project-owned `filesystem.read` 绑定已落地。**未 commit / 未 push**，
按约定 Builder Phase 2 模块完成后统一发布。HEAD 仍是 `a719813`，工作树含
Slice 1 + Slice 2。

### 设计要点

模型既不挑 Resource 也不抄 hash，也不自动把 Catalog 项加入 Project。新增
`local/builder/resource_binding.py`：`resolve_project_resource` 只匹配
`scope=project` 的 `veyra.tool.filesystem.read`，`bind_project_tool` 用
`bound_content_hash` 写 `Tool.uses` / `source.lock` / 最小权限，
`resource_readiness` 投影 `current|stale`、`requires_configuration` 等真实状态。
`EditProposalService.create_resource_binding` 把它塞进**既有** EditProposal 信封，
confirm / reject / undo / stale / revision-ETag / `replace_draft` 全部原样复用。

解析优先级：显式 `reference` > 自然语言能力别名。Project 里有多个
`filesystem.read` 版本时自然语言意图是 **ambiguous → 追问**；全局 Catalog 有、
当前 Project 没有时是 **unbound**，不会自动 Add。Catalog hash 漂移时 Proposal
标 `stale`，lock 仍钉 Project pin，永不静默升级。

### 文件范围

- 新增 `backend/src/veyra_agent_platform/local/builder/resource_binding.py`
- `local/factory/edit_service.py`：`create_resource_binding` + `ResourceBindingUnresolved`；
  构造函数接入 `project_resources` 与 `resource_readiness`
- `local/app.py`：EditProposal 装配挪到 Runtime readiness 之后，才能注入上述依赖
- `local/api/factory/edit_routes.py`：`POST .../edit-proposals/resource-binding`，
  映射 422 `resource_mention_ambiguous` / `resource_mention_unbound` /
  `resource_mention_unresolved`
- `web/packages/api-contracts/src/local.ts`：`ResourceBindingPlan` /
  `CreateResourceBindingRequest`
- `web/apps/desktop/src/api/local-client.ts`：`createResourceBindingProposal` +
  一致性校验（`stale !== (boundHash !== catalogHash)` 等自相矛盾计划拒收）
- `features/builder/EditProposalPanel.tsx`：Resource 绑定摘要（reference、
  Project pin、readiness、最小权限、blocking reasons）
- `features/builder/ProjectBuilderConversation.tsx`：edit 顺序为
  Resource adapter → Knowledge adapter → 既有 LLM 提案；`unbound` / `ambiguous`
  在聊天里说明，不猜测
- `tests/integration/local/test_builder_resource_binding.py`（新增 8 项）
- `tests/scaffold/test_composition.py`：登记新路由
- Desktop `edit-proposals.test.ts`、`project-builder.test.tsx`：wire 与 UI 顺序

### 验证结果

- `pytest tests/integration/local/test_builder_resource_binding.py` 以及
  Builder/Resource 回归（含 `test_edit_proposal_routes`、`test_agent_tool_bindings`、
  `test_composition`）：74 passed
- `ruff check` / `ruff format --check`：通过
- `mypy`：159 source files，无问题
- Desktop `edit-proposals.test.ts` + `project-builder.test.tsx` + `studio.test.tsx`：
  60 passed
- `git diff --check`：干净
- 确定性测试不接触 provider
- 未跑：`make check` 全量、浏览器 E2E（按约定留到模块收尾）

### 覆盖到的 Slice 2 测试要求

单一 Project `filesystem.read` 解析并钉 `bound_content_hash`、最小权限合并、
全局 Catalog-only / 跨 Project 不可选、多版本必须精确选择、Apply/Validate/
Reject/Undo 走既有 Draft 边界、Catalog 漂移不静默升级、`requires_configuration`
不得显示为 `ready`、revision 冲突保留用户工作、确认前无 mutation。

**未覆盖：** 其它 Tool 种类、自动把资源加入 Project、自动 Test Run、
typed validation repair（审计 H）、Run observe→repair（审计 I）。

### 服务状态（Slice 2 重启后）

真实配置重启，未使用隔离库、未指向 loopback provider：

- Desktop `5173` pid 93390 → 200
- 公开站 `5174` pid 93420 → 200
- Local `8771` pid 93323：`build_sha=a719813-slice2-dirty`，`database_ready=true`，
  `database_revision=local_0019_edit_proposals`
- Community `8772` pid 93302：`build_sha=a719813f03fc31e39f1213e9039619bd0ec1bcc3`，
  `database_ready=true`
- OpenAPI 可见 `POST /api/v1/projects/{project_id}/edit-proposals/resource-binding`
  以及既有 `knowledge-binding`
- 真实工作区仍是 `dddd` / `test` / `New project`；Runtime `model_base_url` 为
  Moonshot 正式地址，不是 `127.0.0.1:8899`

### Slice 3 判断

下一个真实用户断点是 **typed validation feedback → 修复 Proposal（审计 H）**，
不是 Run/Test observe→repair（审计 I）。

依据：Slice 1/2 已把 Knowledge 与 `filesystem.read` 的 identity/hash 从模型手里
拿回来；用户确认 Apply 后若 `resource_unbound` / `lock_mismatch` /
`permission_denied` / 图不合法，Chat 仍只看到散文或 `invalid_response`，
无法生成可审查的修复提案。用户明确禁止自动 Test Run；Run 观察闭环仍按
Studio / Runtime 既有路径，不在 Builder 里偷偷开跑。

不要重开 Knowledge V1 / Resource Library V1 / Runtime V1 / Builder Phase 1。
不要 commit / push，直到整个 Builder Phase 2 模块完成。

---

## Builder Phase 2 Slice 3 窄审计（2026-09-17，基于 dirty Slice 1+2 实际代码）

范围只覆盖 Apply 后 validation → Builder 可读反馈 → 可选 repair Proposal。
不重审 Slice 1/2，不碰用户额外的 conversation canvas 修改。

1. **Agent `POST .../agents/{id}/validate` 的真实 contract**
   `LibraryService.validate()` 在 source 能解析时**永远**返回 HTTP 200 且 `valid: true`，
   外加 `source_hash` / `behavior_hash` / `lock_hash` / `file_hash`。依赖问题不改变
   `valid`，而是写入 `dependencies[]`、`dependency_summary`、`runtime_ready`、
   `runtime_ready_scope="agent_dependencies"`。`inspect_agent_dependencies()` 的
   status 枚举：`ready | missing | lock_missing | lock_mismatch | kind_mismatch |
   configuration_required | runtime_unavailable | review_required | permission_denied |
   secret_declaration_missing | context_not_declared | context_too_large |
   project_binding_stale | resource_unbound`。另有 `blocking_reasons`、
   `bound_content_hash`、`locked_hash`、`required_permissions`。
   **不存在** `knowledge_not_indexed` / `knowledge_index_stale` 于 validate contract
   （那是 Runtime `read_knowledge_context` 的 ProjectError）。不要发明这些 code。

2. **Workflow `POST .../workflows/{id}/validate`**
   解析成功且 `resolve_workflow_calls()` 通过则 `valid: true` + 三个 hash +
   `file_hash`。**没有** `dependencies`。调用失败是 422 `contract_invalid` /
   其它 typed ProjectError，不是 `valid: false`。Slice 3 不扩 Workflow repair。

3. **invalid Draft / dependency 如何编码（两层，不要混）**
   - **写边界** `replace_draft`：`resource_unbound`、`resource_lock_mismatch`、
     `knowledge_unbound` 是 `ProjectError` → HTTP 422。图/schema 失败是
     `contract_invalid`。这些进不了已保存 Draft（除非 disk reload 绕过写校验）。
   - **Validate 端点**：已保存 Draft 的依赖问题是 200 + `valid: true` +
     `runtime_ready: false` + `dependencies[].status`。典型路径：保存时权限不足
     （写边界不查权限）、Knowledge 内容变更后锁仍是旧 hash、disk reload 写入错误 lock。
   - `resource_lock_mismatch` 是写错误码；validate 里对应 `lock_mismatch`。

4. **已存在的字段**
   `valid`、`dependencies`、`blocking_reasons`、`dependency_summary`、typed
   `ProjectError.code` 都已存在。validate **当前不会**发 `valid: false`。
   `runtime_ready: false` 才是依赖失败的业务信号。

5–6. **LocalApiClient 仍把 `valid !== true` 当成 `invalid_response`**
   `sourceValidation()`（`local-client.ts`）在 `record.valid !== true` 时抛
   `invalid_response`。这同时作用于 `validate()` **和** EditProposal.validation。
   已有测试故意把 proposal `valid: false` 当作畸形响应。
   **这是 Slice 3 的第一个断点。** 依赖失败且 `valid: true` 的 payload 已被
   `local-client.test.ts` 接受；`valid: false` 仍被拒。畸形/缺字段才应是
   `invalid_response`。

7. **BuilderTarget / EditProposalPanel 如何展示 post-apply validation**
   Apply 后 `BuilderTarget.command()` 重读 Draft 再 `validate()`。只要 parse 成功
   就渲染「应用后验证」并写「已通过结构验证」，**无视** `runtime_ready`。
   `EditProposalPanel` 用 `DependencyReport` 展示提案审查期校验，没有
   “Create repair proposal”。Chat 本身不读 validation；只有右侧 review 区读。

8. **DependencyReport 已能展示**
   每个依赖的 name / reference / status 徽章 / detail / stale 提示。
   不展示 Project pin vs Agent lock 的 hash 对照，没有 repairable 标记，
   没有 next action。Studio 与 Builder 共用此组件；Slice 3 不改 Studio 语义，
   在 Builder validation 区叠加 issue cards。

9. **Builder Chat 不能把 validation result 当成 typed 反馈**
   validate 抛错时只把 `Error.message` 放进 Alert。`valid: false` 会变成
   `invalid_response`。成功但 `runtime_ready: false` 被说成验证通过。

10. **EditProposal 还不能基于 failed validation 建 repair**
    `create()` 走模型；`_validate()` 对 candidate 的 `lock_mismatch` /
    `missing` 等直接 `ContractValidationError`，不会生成「把 lock 改回 pin」
    的确定性提案。没有 validation-repair 路由。必须新增确定性构造，但仍写入
    **既有** EditProposal 信封（confirm/apply/reject/undo/stale）。

**Slice 3 第一个真实断点：** 客户端拒绝 `valid: false`；Builder 把任何 parse
成功的 validate 当成 Validated。应投影现有 `dependencies[].status` 为
Builder-readable issues；仅对服务器已知正确答案的问题提供一条 repair Proposal。

---

## Builder Phase 2 Slice 3 checkpoint（2026-09-17，未提交）

typed validation failure → Builder-readable feedback → deterministic repair
Proposal 已落地。**未 commit / 未 push**。HEAD 仍是 `a719813`，工作树含
Slice 1 + Slice 2 + Slice 3，以及用户自己的 conversation canvas 修改（未改动）。

闭环：

```text
Apply → backend validation → typed Builder feedback → deterministic repair
Proposal → confirmation → repair apply → revalidation
```

### 设计要点

`valid: false` 是业务结果，不是 `invalid_response`。LocalApiClient 的
`sourceValidation()` 现在只要求 `valid` 为 boolean；畸形字符串
`valid: "false"` 仍拒绝。后端 `LibraryService.validate()` 对能解析的 source
仍然返回 HTTP 200 + `valid: true`；依赖失败的真实信号是
`runtime_ready: false` + `dependencies[].status`。Builder 把这两类都投影成
Validation failed。

新增 `local/builder/validation_repair.py`：把 inspect 行投影为 bounded issues，
只对服务器已知正确答案的问题构造 candidate：

- `lock_mismatch` / `lock_missing`（Tool）：`source.lock` ← Project
  `bound_content_hash`
- `permission_denied`：只合并 `required_permissions`，不扩大授权
- Knowledge hash 漂移且 version 未变：显式 rebind 到当前 Project
  `source_file_hash`，Proposal 标明不是 silent upgrade

不可修：`resource_unbound`、`configuration_required`、`project_binding_stale`、
`missing`、`runtime_unavailable`、`review_required`、歧义/缺 secret。只解释
下一步，不生成假 candidate，不 Catalog→Project add，不重建索引，不配密钥。

`EditProposalService.create_validation_repair` 写入**既有** EditProposal 信封
（confirm / reject / undo / stale / revision-ETag / `replace_draft`）。
确认前 Draft 不变。没有自动 while-fail-repair 循环。为让 `replace_draft`
能通过，构造 lock 修复时会一并对齐其它可修的 sibling lock；仍是一条用户确认的
Proposal。模型 / provider 不参与。

Undo 复用 `replace_draft`：权限修复可以撤销。若 previous source 是 disk
reload 进来的非法 lock，Undo 会被写边界以 `resource_lock_mismatch` 拒绝，
Draft 保持已修好的 pin——这是 fail-closed，不是第二条写入路径。

### 文件范围

- 新增 `backend/src/veyra_agent_platform/local/builder/validation_repair.py`
- `local/factory/edit_service.py`：`create_validation_repair`
- `local/api/factory/edit_routes.py`：`POST .../edit-proposals/validation-repair`
- `web/packages/api-contracts/src/local.ts`：`CreateValidationRepairRequest` /
  `ValidationRepairPlan`；`ValidateResponse.valid: boolean`
- `web/apps/desktop/src/api/local-client.ts`：接受 `valid: false`；解析
  `validation_repair`（拒绝 `automatic_upgrade` / Catalog add）
- `features/builder/validation-feedback.ts` + `BuilderValidationIssues.tsx`
- `ProjectBuilderConversation` BuilderTarget：Validated / Validation failed +
  Create repair proposal
- `EditProposalPanel`：Validation repair 摘要与 Diff
- `tests/integration/local/test_builder_validation_repair.py`
- Desktop：`local-client.test.ts`、`edit-proposals.test.ts`、
  `project-builder.test.tsx`、`validation-feedback.test.ts`

未触碰用户的 conversation canvas / Factory conversation 修改。

### 验证结果

- `pytest tests/integration/local/test_builder_validation_repair.py` +
  `tests/scaffold/test_composition.py`：28 passed
- 先前同批回归（`test_edit_proposal_routes`、`test_agent_tool_bindings`、
  `test_agent_knowledge_bindings`、Slice 1/2 binding tests）在修复前已绿；
  Slice 3 未改那些产品路径
- `ruff check` / `ruff format --check`：通过
- `mypy`：160 source files，无问题
- Desktop 窄测：`local-client` + `edit-proposals` + `project-builder` +
  `studio` + `validation-feedback`：95 passed
- `npm run typecheck`（Desktop + Community）：通过
- `git diff --check`：干净
- 确定性 repair 测试 `ScriptedKimiTransport([])`，断言 `not transport.calls`
- 未跑：`make check` 全量、浏览器 E2E

### 覆盖到的 Slice 3 测试要求

`valid=false` 被客户端接受、畸形 `valid:"false"` 仍是 `invalid_response`、
Builder 展示 typed issue、不显示 traceback、lock 修复钉 Project pin、
缺权限只补 required、确认前无 mutation、Confirm 改 Draft、revalidate 显示
Validated、Reject 不改 Draft、revision/ETag drift 冲突、权限 Undo 恢复、
`resource_unbound` 不自动 Add、`configuration_required` 不伪造 repair、
未知 issue 不猜、模型不参与、无外部网络。

### 明确未完成

- Catalog → Project mutation from Chat
- explicit Run/Test
- Run observe → repair
- Builder Phase 2 release

### 服务状态（Slice 3 重启后）

真实配置重启，未使用隔离库、未指向 loopback provider：

- Desktop `5173` pid 34809 → 200
- 公开站 `5174` pid 34873 → 200
- Local `8771` pid 34875：`build_sha=a719813-slice3-dirty`，`database_ready=true`，
  `database_revision=local_0019_edit_proposals`
- Community `8772` pid 34762：`build_sha=a719813f03fc31e39f1213e9039619bd0ec1bcc3`，
  `database_ready=true`
- OpenAPI 可见 `POST /api/v1/projects/{project_id}/edit-proposals/validation-repair`
  以及既有 `knowledge-binding` / `resource-binding`
- 真实工作区仍是 `dddd` / `test` / `New project`；Runtime `model_base_url` 为
  Moonshot 正式地址，不是 `127.0.0.1:8899`

---

## Builder Phase 2 Slice 4 窄审计（2026-09-17，不实现）

问题：Slice 4 是否应该是

```text
explicit Test Run → observe Run result / typed Runtime failure
→ Builder explanation → optional repair Proposal
```

**结论：应该是这条链路。Runtime API 已经足够稳定，可以在 Slice 3 之后开工。
现在不要实现。**

1. **Studio 已有完整 start / observe / stop。**
   `POST /api/v1/projects/{project_id}/agents/{agent_id}/run`
   （`LocalApiClient.runAgent`，不是 `POST .../runs`）。
   `GET .../runs`、`GET .../runs/{run_id}`、
   `GET .../runs/{run_id}/events`（SSE）、
   `POST .../runs/{run_id}/commands`（`approve|reject|stop|resume|retry`）。
   Studio：`TestRunPanel` + `useLiveRun`。

2. **Builder 完全不调用 Run。** `BuilderHarness` 声明
   `runtime_execution=not_performed`、
   `runtime_host_configuration=not_checked`。这是 Slice 4 的用户断点，
   不是 Runtime 不稳。

3. **失败是 typed 的。** `RuntimeRunStatus`：
   `running|waiting|verified|unverified|failed|interrupted|cancelled`。
   `AgentRunResponse.error`：`{ code, message } | null`。
   事件含 `run.failed` / `node.failed` / `tool.failed`。
   Knowledge 运行时码已存在：`knowledge_not_indexed` /
   `knowledge_index_stale` / `knowledge_lock_mismatch` 等。
   `blocking_reasons` 在 Resource/validate 上，不挂在 Run 上。

4. **观察不必永久轮询。** SSE 在 status 离开 `{running, waiting}` 时发
   `done` 并结束；Studio 再 `getAgentRun` 刷新。

5. **Repair 仍应复用 EditProposal。** Slice 1–3 已证明确定性修复可以进
   既有信封。Slice 4 只应对服务器已知如何改 Agent source 的 Runtime code
   生成 Proposal；主机密钥 / Catalog add / 自动 approve 只解释。

6. **Slice 4 必须禁止：** 自动 Test Run 循环、静默 apply、Catalog auto-add、
   secret 配置、自动 approve、把模型散文当 typed failure。

**推荐 Slice 4 范围（将来，不现在）：** Builder 里用户显式点 Test Run →
复用 `runAgent` + SSE → 投影 `error.code` → 可选一条 EditProposal →
用户确认。不要重造 Runtime。

---

## Factory structured generation compatibility = resolved（2026-09-17）

Slice 4 **暂停**。Slice 1–3 不重做。本轮只修 Project Chat
`帮我生成礼物包装 agent` 在 `createFactorySession` → `generateFactoryBlueprint`
上的真实 Moonshot 4xx。未 commit / 未 push。

### 真实请求 shape（发给 Moonshot，不含 secret）

`HttpKimiTransport.complete` → `POST {model_base_url}/chat/completions`

```text
model = kimi-k3
messages = [
  system: BUILDER_SYSTEM_PROMPT + create_agent contract,
  user: BuilderHarness Project JSON context（metadata-only，无文件正文/密钥）,
  ...session messages...,
  user: "Generate the AgentBlueprint JSON for this requirement."
]
reasoning_effort = high
max_completion_tokens = 16384
response_format = {
  type: json_schema,
  json_schema: {
    name: agent_blueprint,
    strict: true,
    schema: <Moonshot MFJS projection of AgentBlueprint>
  }
}
temperature / top_p / max_tokens = 不发送
```

`resolve_intent` 仍走 `json_object`（已成功，未改）。Harness / BUILDER_SYSTEM_PROMPT
未削弱，Project context 未去掉。

### 真实 4xx 分类（最小官方配置 probe，未改真实 Project）

`kimi-k3` 在 `/models` 中存在。`json_schema` + `strict=true` + 简单 object **200**。
`json_object` **200**。`reasoning_effort` / `max_completion_tokens` 不是拒绝原因。

当前完整 AgentBlueprint schema（约 7393 bytes）→

```text
http_status = 400
provider_error_type = invalid_request_error
provider_error_code = (none)
rejected_field = $defs.required_capabilities.properties.component_types.items
bounded_message = Invalid request: response_format.json_schema is not a valid
  moonshot flavored json schema, details: <At path '...component_types.items':
  type is not defined>
```

给 enum 补 `type` 之后的第二条 400：

```text
http_status = 400
provider_error_type = invalid_request_error
rejected_field = properties.nodes.items
bounded_message = ... detected infinite recursion without termination condition
```

Walle `CheckRefTermination` 只遍历 `anyOf`，不遍历 `oneOf`，因此
`$ref` → `oneOf`（`$defs.node`）被误判为无限递归。`const` 不是 MFJS
SupportedKeywords。

### Root cause

Moonshot MFJS strict json_schema **支持**，但提交的 AgentBlueprint schema 不是 MFJS：

1. `enum` 节点缺少 `type`（ValidateEnum: "type is not defined"）
2. `$defs.node` 使用 `oneOf` + `$ref`（termination 误报）
3. 节点 `const` 不是 MFJS 关键字

不是 harness 缺失，不是 Slice 4，也不是请求尺寸。

### 修复

`local/factory/structured_schema.py`：provider-specific projection，只用于
`response_format.json_schema.schema`。

- `enum` 补 `type`
- `oneOf` → `anyOf`
- `const` → `{type, enum:[value]}`
- 去掉 MFJS 不认且会干扰的 `$schema` / `allOf` / `if` / `then` /
  `uniqueItems` / `minProperties` / `propertyNames`

服务端仍然：`json.loads` → `AgentBlueprint.from_dict` → `compile_blueprint` →
Factory review → 显式 `apply-draft confirm=true` 才写 Draft。没有 Markdown 截 JSON，
没有自由输出 fallback，没有静默改语义重试。

`_raise_for_provider`：401 / 429 / 5xx 保持独立 code；其它 4xx 仍是
`factory_request_invalid`，但带 sanitized details
（http_status / provider_error_type / provider_error_code / rejected_field /
bounded_message），不泄漏 Authorization / API key / 完整 body。

投影后的同一 schema 对 kimi-k3 探测为 **HTTP 200**。随后 live generate 仍可能
输出 `verification: {}`，因为 MFJS 对 `$ref` 嵌套 `required` 约束不完整。
因此投影会 **inline `#/$defs`**，并对完全缺省的 verification 做有界默认
`{required: false, checks: []}`。其它字段仍走 AgentBlueprint 校验。

### 真实最小验收（New project，未自动 Run）

`帮我生成礼物包装 agent` 经同一套 Local API（Project Chat 路径）：

1. `resolve` 200，`intent=create` / `create_kind=agent`
2. Factory session 201
3. `generate` 200，`state=review`，Blueprint + resource_plan，**0 agents**
4. `apply-draft confirm=false` → `factory_confirmation_required`，仍 0 agents
5. `confirm=true` → Draft `礼物包装 Agent`，Studio draft 200，runs=[]

未自动 Test Run。Slice 4 仍暂停。

---

## Builder durable conversation = complete（2026-09-18）

Slice 4 **暂停**。未 commit / 未 push。右上「历史」未改用途。

### 审计 A–M（代码事实）

A. **ProjectBuilderConversation 的 messages 现在存在** `builder_messages`
   （SQLite，migration `local_0020_builder_conversations`）。进入 Chat 时
   `GET /builder/conversations/{id}` 恢复。此前只在 React `history` /
   `messages` state。

B. **曾经只是 React state。** `setHistory(user)` 是乐观更新；catch 只
   `setError`。现在 `POST /builder/turns` 先 `commit_user_turn` 再 resolve。

C. **refresh 丢失的原因：** 组件 remount 时 `messages=[]`，没有 conversation
   GET。Factory/provider 失败时前端未把失败轮次写成持久记录。现已服务端持久化。

D. **`history.slice(-18)` 来自前端 React messages**，仅 legacy
   `resolveBuilderIntent` 路径仍发送。主路径 `submitBuilderTurn` 只发
   `conversation_id` / `content` / `focus` / `locale` / `retry_of`。
   Server `HISTORY_LIMIT = 18` 从已持久化消息选取 bounded 上下文。

E. **FactorySession.messages 仍持久化**，但是 create_agent 子流程
   （`factory_sessions` / `factory_messages`），不是 Project Chat 的 canonical
   历史。

F. **FactorySession 只覆盖 create_agent 子流程。** 通用 Project Chat 走
   BuilderConversation；Retry 不新建 Conversation。

G. **已有表，职责不同，未重复建：**
   - `agent_conversations` = Runtime Agent chat
   - `factory_sessions` = Factory create_agent
   - `builder_conversations` / `builder_messages` / `builder_operations` =
     Project Builder Chat（本轮新增）
   没有 recent 表。

H. **用户消息在 model call 之前成为状态。** `commit_user_turn` 原子写入
   conversation（如需）、in_progress operation、user message，然后才
   `resolve_intent` / Factory / provider。

I. **Factory/provider 失败会持久化。** turn HTTP 200，operation=`failed`，
   追加 sanitized `failure` 消息。400/401/429/5xx/timeout/malformed JSON
   都不删除此前 Chat。

J. **assistant candidate plan 会持久化**（kind=`plan` / `proposal_reference`）。
   Reject / Confirm / Apply summary / validation summary 经
   `POST .../records` 写入。不持久化 spinner、raw provider body、hidden
   reasoning、secret、system prompt。

K. **「新聊天」** 打开无 `conversation_id` 的 Project Chat；发送第一条消息
   才创建 conversation。不丢弃已有对话行。

L. **左侧「最近」** 来自 `GET /builder/activity?limit=5`：只投影
   BuilderConversation（像 GPT/Codex 的聊天记录）。**不包含 Runtime Run。**
   `translation` / `Run · unverified` 属于右上「历史」，不得出现在 Recent。

M. **Runtime Run 只属于右上「历史」**（`#/runs` / `projectRoutePaths.runs`）。
   点击 Recent Conversation 打开 exact `conversation_id`。

### 验收证据（窄测试）

- `tests/integration/local/test_builder_conversations.py`：persist-before-model、
  restore、resolve/Factory 400/401/429/5xx 保留对话、retry_of 不改写失败、
  reject/confirm/apply/validation、Project isolation、Recent、无 secret/prompt
- Desktop vitest：Project Chat Durable、Recent 投影、`parseDesktopRoute ?conversation=`
- 未跑全量 `make check` / 浏览器 E2E（模块收尾再跑）

---

## AgentSemanticPlanV1 + SemanticPlanCompiler = complete（2026-09-18）

默认 Factory generate 不再让模型输出完整 AgentBlueprint。

```text
NL → persist user message → resolve_intent → AgentSemanticPlanV1
→ SemanticPlanCompiler → AgentBlueprint.from_dict → compile_blueprint
→ Factory review → explicit confirm → Apply Draft
```

- Schema：`contracts/schemas/agent-semantic-plan.schema.json`
- Model：`contracts/semantic_plan.py`（拒绝 hash / UUID / source.lock / 主机路径）
- Compiler：`local/builder/semantic_compiler.py`（复用 Slice 1/2 resolver）
- 兼容桥 `structured_schema.py` 保留，但 generate 的 `json_schema` 是 Semantic Plan
- 仅 schema/`response_format` 兼容性 400 允许一次 `json_object` fallback
- 401/403/429/unknown 4xx/5xx / Markdown 截 JSON 不允许

Compiler 行为：

- 唯一 Project `filesystem.read` → 钉 bound hash + 最小权限
- 两份「毕业论文」→ clarification，不猜
- 唯一 Project `filesystem.read` → 钉 bound hash + 最小权限
- 两份「毕业论文」→ clarification，不猜
- 仅 **项目/工作区 scoped** 的未绑定 `filesystem.read` 才 `missing_capability`
- 「用户上传物品 / read uploaded files / read files」编译为 Start 输入，不要求 Project Tool
- GitHub/MCP/shell 类 intent 仍 `missing_capability`
- missing proposal.action **必须**是 `quarantined_resource_draft`（`executable: false`）；
  前端只接受该值，`missing_capability` 会被当成 invalid_response
- 不发明 Skill / Policy / node UUID

Canonical truth 仍是 AgentBlueprint / AgentSource。

### 服务状态（Durable Conversation + Semantic Plan 重启后）

真实配置重启，未使用隔离库、未指向 loopback provider：

- Desktop `5173` → 200
- 公开站 `5174` → 200
- Local `8771`：`build_sha=a719813-conversation-dirty`，`database_ready=true`，
  `database_revision=local_0020_builder_conversations`
- Community `8772`：`build_sha=a719813-conversation-dirty`，`database_ready=true`
- OpenAPI 可见 `POST /builder/turns`、`GET /builder/activity`、
  `GET /builder/conversations/{id}`
- 真实工作区仍是 `dddd` / `test` / `New project`；Runtime 与 Factory
  `model_base_url` 均为 Moonshot 正式地址，不是 `127.0.0.1:8899`

### 用户更正（2026-09-18，Recent ≠ Run History + missing proposal）

- 左栏「最近」= Builder 聊天记录；右上「历史」= Runtime Run History。
  activity 不再合并 `runtime_runs` / `workflow_runs`。
- Compiler 不再把「用户上传 / read files」当成未绑定 `filesystem.read`。
- `missing_capability.proposal.action` 恢复为 `quarantined_resource_draft`，
  避免 Desktop 整段 turn 被 `invalid missing-capability proposal` 丢掉。
- 已重启 Local `8771`（`a719813-conversation-dirty` / `local_0020`）。
  Desktop `5173` HMR 已加载新 client。

### 用户更正（2026-09-18，消息操作条 + 组装动画）

- 截图里的大「重试」是失败操作条；成功/待确认时改为每条消息下复制、时间，重试只出现在最后一条。
- Project Chat 发送后先思考，再滑出组装画布，阶段从了解需求 → 组装蓝图 → 资源计划，不再一次跳到终态。

### Resume

1. Read `AGENTS.md` → `docs/AI_DEVELOPMENT_BRIEF.md` → `docs/PROJECT_DESIGN.md` →
   `docs/DEVELOPMENT.md` → this file.
2. `git status -sb`、`git diff --stat`、`git diff --name-status`。
3. 工作树保留 Slice 1–3 + Factory MFJS 兼容桥 + Durable Conversation +
   Semantic Plan/Compiler + Interaction Model V2 + ProviderCapabilityProfile。
4. **下一步：在 Desktop 已登录会话里重跑浏览器 CASE 1–3**（等 Moonshot 429 解除），
   或由用户选择 ProviderCapabilityProfile / Harness Receipt / Slice 4。
   不要开工 Slice 4，除非用户明确恢复。
5. 不 commit、不 push、不重做 Slice 1–3、不改右上 Runtime History 语义。
