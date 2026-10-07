# Veyra Development Handoff

## Generator Harness 普通用户实测与继续点（2026-10-05，本地未提交）

- 最新授权：用户明确回复“可以”，允许仅重启8771并在隔离Project做普通用户真实测试。代理已数次仅重载8771以加载修复；最终PID13482、exec session91629，5173/8772保持原服务；health/database_ready与Factory configured均为true，已加载最终源码。没有Git提交/推送/清理、没有改原用户Project/历史失败Run、没有额外真实图片请求。
- 真实Case1已完成：浏览器生成→Apply Draft→校验并提交v1→应用运行；收集40㎡/香薰礼物/6000元，三个方案，选择C改预算5000，等待确认，浏览器刷新恢复同一Run，确认后最终清单。API显示仅1个Run、固定v1、status=unverified；最终合计5000。不是独立语义Verifier通过。原始C方案有5800/实际6000的合计错误，已新增通用Arithmetic，但未把旧Run伪称用过它。
- 实测发现并已修：阻塞终态误显示完成/生成；规划context缺capability名字/混入legacy graph specs；对话memory误需实体工具；运行时输入误为生成阻塞；完整closed Provider schema未在本地验证；registry来源前端拒绝且吞错导致发送禁用；持久状态Source/Apply未闭环；Entity Read只有ID查询；underscore Tool参数被slug校验拒绝；ToolRuntime共享scope并发串扰；历史结果巨型JSON与问答字体/行高。
- 新能力：AgentSource extensions.veyra.state_contract正式契约（不放UI，参与行为hash）；安全ensure_type/read_type_schema与Apply预检/冲突/回滚；Entity Query新1.0.0资源，当前Project、等值filter、50返回/500扫描/1MB、truncated；state类型/字段/identity/status前置校验；旧持久状态Proposal缺契约不能继续Apply；Arithmetic新1.0.0资源，有限AST/Decimal/Fraction、exact+approximate，无eval/外部效应。旧Read/Write资源hash、依赖、迁移不变。
- Case2与Case3尚未实测运行通过：Case2在coverage review遇到HTTP429；Case3旧候选缺闭环未Apply，新一轮再遇429。已停止重复Provider重试。生成上下文/coverage已精简、诊断给出具体缺字段，仍须服务商恢复后用原需求重测，不可用mock替代。这是当前真实阻碍，不是API Key再次授权问题。
- 最终门禁：后端full 1142 passed（/tmp/veyra-generator-final-full.log）；Desktop 661 passed（/tmp/veyra-generator-final-desktop.json）；mypy241 sources clean（/tmp/veyra-generator-final-mypy.log）；Ruff/check383格式文件与diff check通过；两个web typecheck/build通过（Desktop既有large chunk提示）；最新schema/state 13pass、reading 38pass补充验证后续微调。/tmp/veyra-generator-final-state-regression.log 8pass；/tmp/veyra-agent-state-guard-integration.log 2pass；/tmp/veyra-arithmetic-tool-tests.log 71pass；此前full1139pass/3fail其中1是测试keyword参数已修，2是WorkflowSource没有state_contract已改getattr并8pass，不能称此前全量通过。
- UI按指定design-taste preserve与web-design-guidelines终审：阅读模式默认仅Agent应用，technical默认不变；JSON只按声明输出keys识别；普通文本/非契约JSON保持；Artifact卡片复用；深层按需展开/20项增量/键盘与focus/长词/空状态。无动画/新依赖。Root又修限流中文、账号默认ready API优先、问答等待copy、重复Agent计数。最终1470px浏览器确认结果转为字段/表/清单，截图/tmp/veyra-generator-case1-result.png；viewport override未改变claimed user tab实际宽度，因此不声称窄窗口浏览器验收。
- 辅助workflow_verifier_regression已完成前端终态、Harness tests、EntityQuery/并发、安全算术、结果阅读；其余早期辅助曾遭usage limit。全部改动共享working tree，保留前序大量dirty文件与.backboard/sessions；不切换低级模型绕限额。
- 继续顺序：完成当前门禁/修明确回归→确保8771加载确切最终源码→最终UI审查/截图→记录证据→服务商恢复后继续Case2 CSV文件+审批+可打开报告、Case3两次Run保持ID/update/revisions、Arithmetic真实使用与重复稳定性；不宣称产品级。详见docs/GENERATOR_USER_ACCEPTANCE.md。

## 历史检查点：Generator Harness 修复初期（2026-10-05）

- 用户最新范围：先修复生成器核心，再使用不同复杂度、有实际用户价值的任务进行普通用户产品实测，检查效果并继续优化。用户两次要求“先修再测”，因此尚未启动新的真实 Builder/Runtime 测试案例。
- 已写入：Factory-backed TaskStructureV1语义规划、完整closed schema与严格投影；TaskCoverageV1覆盖审查、有界解析/编译修复和必需职责保留；原始/澄清需求均入Harness；actor I/O、stage input_sources、真实typed交接、角色最小资源权限、完整instructions；新增Native ask_user/reply同Run checkpoint，回复不会批准Tool，图像只在final后生成；公开Tool schemas注入与仅前置参数错误恢复；Workflow typed HumanInput/whole-value Transform/候选锁替换。
- 当前源码门禁：定向88 tests、Native问答与typed交接2 integration、27 loop unit、17规划/覆盖 tests、46 frontend tests已通过；mypy239 sources与lint通过。第一次full pytest1009 passed/56 failed集中于旧模型mock及3个实际兼容问题，已逐项收敛到兼容104 tests中100/4，再修正4项后对应17 tests通过；最终full正在运行 `/tmp/veyra-generator-full-tests-final.log`。不能使用第一次full数字宣称最终通过。
- 服务由用户此前启动：8771 PID41445，5173 PID41562；根代理未重启。末次代码仍需确认加载，历史授权不自动用于restart。原账户/Project/Secrets不修改，test fixtures仅tmp与memory secrets。辅助代理后续遭遇usage limit，根代理接手其已写入范围；禁止为了绕过限额切换低级模型。
- 未完成：最终full gates、待输入刷新/结果前置验证/coverage审查最终复核、文档状态收尾、web-design-guidelines终审新增reply组件、普通用户真实产品测试与发现问题修复。真实测试应隔离Project/公开或合成材料，保留授权/receipt/验证边界，不把mock和API harness称为用户端验收。

## Settings / Workflow 运行页与真实校验故障（2026-10-05，本地未提交）

- Settings 改为 Veyra 既有视觉语言中的单内容工作区：我的 API、界面偏好、工具授权、创作助手。服务预设填写地址，自定义协议仍走通用 transport；阿里云专属业务空间地址提供明确引导。保存连接→发现/手动添加模型→显式测试→任务默认值在同一上下文内完成；大量模型支持搜索和分批展示。界面偏好具有实际主题、语言和减少动态效果设置。没有新依赖、React Bits 或 GSAP。
- Workflow App 按 design-taste-frontend 的 preserve/audit 指导重构：紧凑标题与版本、完整说明弹窗、单一任务输入；运行后只显示提交摘要和真实节点状态，图片输入为缩略素材条；成功后结果只显示一次，已完成进度与技术证据按需展开；失败保留步骤和子 Agent 结果入口。历史错误可回到新任务，缺失旧版本不会冒用最新说明。committed version/hash/预检与收费运行授权边界保持。
- 最终 web-design-guidelines 审查修复状态温和播报、焦点返回、重名字段覆盖、缺失版本说明、错误恢复及回链 run_id；真实浏览器另外发现全局标题段落样式截断弹窗全文，已修 CSS 优先级并复验390px/暗色全文与 Escape。隔离模拟验收准备、运行、完成、失败；临时源码/标签页/viewport已清理。
- 真实历史故障：两个子 Agent 均完成，Renderer 的 PNG 与非空对象已经保存；shared required_fields 校验构造包含列表的集合，引发 TypeError，被压成 workflow_execution_failed。已修安全比较，Workflow Verifier仅检查声明输出，与 Agent graph一致，并记录 verifier.result。用真实已保存输出执行修复后的三项check均通过，PNG内容存在；没有重新调用收费模型，也没有改写历史失败记录。
- 证据：Desktop全量630 tests通过；Backend运行/Artifact/Workflow/Agent相关91 tests通过（包含新校验11项和Workflow integration15项）；Ruff、format、两Runtime source mypy、Desktop/Community typecheck/build和diff check通过。Community全量23/24，已有account测试期待Name而页面已用Display name，隔离复跑同样失败，未扩大修改该模块。Earlier image protocol focused88 tests仍属于独立定向证据。
- Live：用户此前重启的8771进程加载了图片API适配；用户主动测试Qwen图片生成成功，模型证据active_probe/supported。当前新Verifier修复尚未由该进程加载，5173后续停止；已请求本轮明确服务重启授权，不能从历史handoff推断。未stage/commit/push、未由代理新增真实图片/Workflow调用。
- 生成质量的未完成边界：完整的三方案/用户选择/修改/状态保留需求，当前确定性生成器降为single_run的分析→出图→校验；companion执行说明只有通用角色brief，Renderer未消费Analyzer结果，生成validation不验证需求覆盖。修复执行校验不代表复杂自然语言生成已经可靠，也不代表用户原助手需求完整实现；后续必须修Planner与需求保真门禁，不能靠增加业务关键词或修改历史版本掩盖。

## Current checkpoint（2026-10-04，Model Registry 与 Workflow 体验收尾）

- 用户要求完成 Model Capability Registry & Runtime Setup V1，并继续重做不舒服/按钮和流程不适用的 Workflow 运行页，指定 taste-skill。官方 taste/redesign 指导用于保留式审计，保留 Veyra tokens、Lucide 和 existing stack；未安装新依赖。
- 新增 Registry、Resolver、0036 migration、Builder per-actor/role needs、严格 Runtime checks 和 Settings。trusted metadata/adapter 可为 declared Profile 提供有效证据；unknown 与 vision 不能冒充图片生成。当前 loop 走 JSON action，不误要求未调用的 native tools/response_format。
- shared RuntimeSetupPanel 变为 compact strip + 原页 modal，新增 RuntimeProviderSetup：API/model discovery/manual、成本同意 probe、精确 Agent/slot binding、automatic preflight。重试复用 saved credential；没有明确已绑定或已验证兼容模型时不会自动选择一个 unknown Kimi 出图。
- Workflow App：去双框，运行 CTA 文本明确，历史/预览默认折叠，字段/节点名本地化、raw schema keys保持；history retry/recheck/loading/版本切换 fail closed。390px 版本选择器与 CTA 的真实 CSS 优先级/裁切修复并复验。
- Exact current source gates：Backend `env -u PYTHONPATH make check` **982 passed / 474 warnings**，依赖/format/lint/mypy通过；Desktop **72 files / 574 passed**、typecheck/build通过；diff check clean。Full logs在 `/tmp/veyra-capabilities-*20261004.log`。运行控制/费用和保存效果只 fake Provider/API 测试，没有由代理调用真实 Provider。
- Browser：Chrome tab `156894241` 的用户 Workflow 页有真实登录态；宽屏观察、新配置窗口与独立 task/flow已生效。只读临时 preview用同一组件/真实GET metadata检查 Dark/390px，effect methods拒绝；width324/height36的版本selector和width340的CTA完整显示。临时两文件/QA tab/viewport已清理，用户主页面theme未改。
- Live 8771：用户在原 PyCharm 启动环境重启，旧 PID `28110` → 新 PID `8276`。新进程晚于末次 backend edit，health `ok`、schema0036、db_ready=true，Builder configured=true。礼品 Workflow 的 committed readiness version_id/source_hash 匹配；唯一 setup issue 为 `image_generation` 未验证，需要用户的对应模型配置。代理未读取密钥，未调用真实 Provider。
- 未 stage/commit/push，保留原 dirty tree 与 `.backboard/settings.json`。A–R final report：`docs/MODEL_CAPABILITY_REGISTRY_V1_REPORT.md`。当前 verdict：本轮实现与本地/界面/live preflight验收完成；不宣称 real-provider run、packaged acceptance 或 CI。

## Current checkpoint（2026-10-02，Builder 实时状态与 Workflow Studio 误报）

- 本轮用户报告 Builder 长时间停在“正在理解需求”，刷新才出现运行模型绑定卡；并指出卡片难看。只读 DB 核查：较早的多对象请求已经以 `unsupported` 完成、未生成 Proposal；后续请求曾进入 `waiting_for_runtime_binding`，并在用户继续后生成待审查 Proposal。后台没有仍在运行的这两条 Builder 操作。
- 原因：新对话后端已持久化 conversation，但 SSE 只在 turn 结束时发最终快照；前端即使启动轮询，在取得 conversation ID 前也无法 GET。现后端在 `_begin` 后发初始快照，前端每帧立即应用并轮询；保留终态快照。Workflow 等待绑定也会显示卡片。Runtime 选择卡重新布局，内部 `waiting_for_*` 状态码不再露给用户；中文提示已修正。
- 修复跨项目切换时上一 Project 聊天短暂保留；`unsupported` Activity 标“未创建”并隐藏假工作台，一般失败不再保留无产物的阶段面板。
- 用户同时指出 Workflow 没有 Agent 式运行页、Studio 红条报错。现状：Workflow 可在 Studio 底部测试，Run Detail 可看结果，但无独立 Workflow App。红条是前端把已提交 Agent 的合法输出 slug `model-known` 误判为非法，已按后端 `_SLUG` / `NODE_ID_RE` 分开校验映射 key/value，且去掉错误提示中的固定 `request → prompt` 示例；当前服务端草稿结构校验有效，无需修改这条 Workflow 的映射。
- 验证：Desktop Builder 定向 **99 passed**、Workflow Studio 定向 **51 passed**、Backend Builder conversation **34 passed**；Desktop typecheck/build、Ruff（后端修改范围）、`git diff --check` 通过。实际浏览器复核旧 unsupported 页面、Runtime 模型卡宽屏/560px 窄屏、Workflow Studio 红条消失及测试入口恢复；未重新对真实 Project 发 Builder 请求验证完整 SSE E2E。
- 获本轮明确授权后仅重启 `8771`：旧 PID `36790` → 新 PID `24097`，health `status=ok`、`database_ready=true`、`database_revision=local_0034_project_entities`。保留原进程所需的 Builder 配置；`5173/5174/8772` 未重启。未 stage、commit 或 push。工作树仅本轮相关源码/测试/文档修改及原有未跟踪 `.backboard/settings.json`。
- 余项：真实 Provider、再次构建和 Workflow 实际 Run 未在本轮执行。

## Current checkpoint（2026-10-02，Workflow App 与 committed Workflow version）

- 新增独立 Workflow App（`#/projects/:projectId/workflows/:workflowId/run`，`pages/workflow-app.tsx`）：只列出明确提交的 Workflow 版本，按所选 `version_id` 预检（readiness 返回 `source_kind/version_id/source_hash`，前端核对一致才放行），以 `source=committed` + `version_id` 启动，显示节点进度、子 Agent 运行、审批与补充输入。Studio 仍测试 Draft；Workflow 树运行按钮、Studio“打开应用”、项目运行记录指向 App。
- 后端：迁移 `local_0035_workflow_versions` 给 `workflow_versions` 加 `committed`（旧快照默认未提交，需重新提交）；`WorkflowRunRequest` 支持 `source/version_id`；AgentCall 只能引用明确提交的 Agent 版本；Workflow Tool 需审批时预检与运行均拒绝（`workflow_tool_approval_not_supported`），不再以 `approved=True` 绕过。项目导入保留 Workflow 固定引用的 Agent 版本的已提交状态。Studio 的 Workflow 人工补充输入等待改为字段表单（`WorkflowInputReplyBar`）。
- 验证：Backend `tests/integration/local tests/unit/local` **773 passed**，Ruff、mypy 通过；Desktop 全量 **554 passed**，typecheck/build 通过。获授权后仅重启 `8771`（PID `24097` → `6620`），health `ok`、revision `local_0035_workflow_versions`。对“复杂版(4)”礼品包装 Workflow 做接口级验证：迁移后旧快照 `committed=false`、按版本预检返回 `workflow_version_not_committed`；`/commit` 后复用同一快照并标为已提交；按版本预检 `source_kind=committed`、四项检查全部就绪。Vite 能编译 `workflow-app.tsx`。未做浏览器端验证（无浏览器工具）；未实际启动 Workflow Run（需要上传图片并调用真实 Provider）。未 stage、commit 或 push。

## Current checkpoint（2026-09-29，Builder Generation Architecture V2）

- 产品模型未改：Agent = model/tool loop；Workflow = typed DAG。本轮把 Builder 从 Prompt+Resource 挂载器升级为任务编译器。
- 主链：`plan_task_structure` → `decide_product_shape` → `compile_execution_plan` → `derive_plan_capabilities` → `ResourceResolver` → `compose_execution_product` → Proposal → `apply_composite`。Factory `generate()` 走 `_generate_v2_product`，不再用用户措辞锁死 Agent。
- Shape 由 TaskStructure / ExecutionBoundary 决定：`PURE_AGENT` / `WORKFLOW` / `AGENT_WORKFLOW` / `MULTI_AGENT_WORKFLOW`。`user_requested_surface` 只是偏好；「不要 Workflow」可强制 PURE_AGENT 并带 warning。
- 验收矩阵：Translation / Research / Workspace Editor / Software Engineer = PURE_AGENT；Document / Gift / Secondhand = AGENT_WORKFLOW（Gift 缺 image_generation 则 Apply blocked）；CRM = WORKFLOW + persistent entity。负向：包装产业/包装是否完整/搜索翻译工具/software engineer 研究报告 不再职业劫持。
- HumanInput = `HumanApproval.review="input"` + Workflow `reply`。业务审批 ≠ tool approval。State = `local_0034_project_entities` + entity tools。Verifier 是 DAG 节点。
- Resolver 仍只接 capability，不接 hallucinated resource id。Resource Factory 职责未改。
- V2 Closeout（2026-09-30）：0034 增加索引与 events→records CASCADE；`EntityStore.write` 拒绝跨 Project/type 覆写；Workflow Tool 节点默认把 values 中的 `entity_id` 传给 entity 工具（mapping key 只能是连字符 slug），无 `result` 时 payload 取 values 快照；Factory `generate()` 不再要求 Builder Provider；Community test fixture 注入 `registry_storage_root`（原 sandbox PermissionError 根因）。
- Live 8771 已重启：`pid=9315` `status=ok` `database_ready=true` `database_revision=local_0034_project_entities` `build_sha=0ad7a3e0…-dirty`。迁移前自动备份 `app.sqlite3.pre-migration`，核心表行数不变。未重启 5173/5174/8772。未 stage / commit / push。
- 门禁：`env -u PYTHONPATH make check` **947 passed** + ruff + mypy；Desktop **68 / 536**；typecheck/build 通过；`git diff --check` 干净。Live Entity Store smoke 通过并清理。Browser E2E unavailable。Real Provider 未执行。
- 明确未做：通用数据库/表单设计器、完整 chat/form 产品系统、图形化改 DAG、Community marketplace、browser automation、MCP 产品化、任意可执行 Tool、loop 出图。
- Remaining：`_generate_loop_agent_product` 死代码仍在 `factory/service.py`；`infer_agent_specification` 只用于显示名；修改方案不是 graph editor；HumanInput 复用 HumanApproval；真实 LLM planner 未跑；V2 composer 只生成 entity.write，不生成 entity.read；Project purge 不清理 entity 行；真实 Application Support 下 Community registry 目录残留历史测试写入（未删除）。

## Current checkpoint（2026-09-28，V1 Release Candidate Cleanup）

- 本轮不是 V1.1。不增加 image generation、browser automation、MCP 产品化、完整 Policy、vector RAG、Community marketplace、AV、新 Workflow primitives、任意可执行 Tool。
- 产品模型未改：Agent = model/tool loop；Workflow = typed DAG。
- Local head：`local_0033_agent_app_versions`。Community 仍是 `community_0015_cloud_runs`。
- 对话 UI 不再把 UUID 当标题。API `_public_title` + 前端 `displayConversationTitle`。旧 title=null/UUID 显示 New conversation / 首条消息。
- Agent App：compact header（名称 / 版本 / 状态 / Edit in Studio）；conversation rail 次要；主列是交互区；activity 是 compact strip；Run 列表不展示 raw run_id。
- 测试 Fixture 隔离回归：`tests/integration/local/test_fixture_isolation.py`。Complex acceptance 仍用 `tmp_path` sqlite + projects。不删除真实 Local DB 里无法证明归属的 Project。
- `.gitignore` 忽略 `.backboard/sessions/` 与 `$DB`。磁盘上仍有 4499 个 session objects，不再进入 `git status`。
- `env -u PYTHONPATH make check`：**915 passed**；ruff/mypy 通过。Desktop `npm test`：**68 files / 519 passed**；typecheck/build 通过；`git diff --check` 干净。未 stage / commit / push。
- 8771 已安全重启加载本轮代码：`pid=46045` `status=ok` `database_ready=true` `database_revision=local_0033_agent_app_versions` `build_sha=0ad7a3e0…-dirty`。未重启 5173/5174/8772（仍 HTTP 200；8772 `community_0015_cloud_runs`）。
- Browser E2E unavailable。Real Provider smoke plan 只写步骤，未执行。

## Current checkpoint（2026-09-28，Complex Agent Product Acceptance）

- 产品模型未改：Agent = model/tool loop；Workflow = typed DAG。本轮不是新产品模块，是全链产品验收 + 阻断闭环的 hardening。
- 主链：User Request → `infer_agent_specification` → CapabilityRequirement → ResourceResolver → ResourcePlan →（missing 且可生成则 Resource Factory approve/publish）→ `compose_loop_agent` → Apply pin/lock → Draft → Commit immutable version → Agent App `source=committed` → AgentLoopRuntime。
- Research / Software Engineer / Packaging Analysis 都是 acceptance fixture，产品代码无职业 hardcode。generate 为 **Specification-seeded HTTP Factory chain**（scripted Kimi interview + scripted Runtime）；不是 Full HTTP Builder chain with a real Provider。
- Composer 现在把 `needs_configuration` 工具写入 Agent lock/bindings/permissions；Apply 校验 snapshot 含这些 lock。GitHub 无 secret 时 App preflight 422 `needs_configuration`，不创建 Run。
- App activity 使用 structured events：Starting Agent / Thinking / Using Web Search / Reading Knowledge / Waiting for approval。不是假进度条。
- 验收：`tests/integration/local/test_complex_agent_acceptance.py`（research full-chain、engineer repair+reject、packaging multimodal+image_gen gap、factory skill、error/tool_failed、github preflight、draft isolation、second turn、Project Runs/Run Detail）。
- 无新 migration：live 仍是 `local_0033_agent_app_versions`。
- `env -u PYTHONPATH make check`：**909 passed**；ruff/mypy 通过。Desktop `npm test`：**67 files / 515 passed**；typecheck/build 通过；`git diff --check` 干净。未 stage / commit / push。
- 8771 已重启加载本轮代码：before `pid=21076`；after `pid=91820` `status=ok` `database_ready=true` `database_revision=local_0033_agent_app_versions` `build_sha=0ad7a3e0…-dirty`。未重启 5173/5174/8772（仍 HTTP 200；8772 `community_0015_cloud_runs`）。
- 本环境无 browser MCP：Browser E2E unavailable。
- Real Provider acceptance was not performed.
- 本轮明确未做：loop image generation、browser automation、完整 Policy Engine、vector/advanced RAG、MCP 产品化、任意可执行 Tool 生成、Community marketplace、audio/video、desktop signing、新 Workflow 能力、新 Resource 类型。
- 下一阶段应基于本轮结果决定 V1 cleanup / commit / release readiness，而不是继续加功能。

## Current checkpoint（2026-09-28，Agent Run App V1）

- 产品模型未改：Agent = model/tool loop；Workflow = typed DAG。
- Studio Test Run = 当前 Draft（`POST /run` 默认 `source=draft`）。Agent App = committed immutable version（`source=committed` / `version_id`）。未 Commit 时 App fail-closed：`agent_has_no_committed_version`。
- Conversation pin `agent_conversations.agent_version_id`；后续 Commit 不静默升级旧对话。新对话默认 latest committed。hybrid 首次 typed inputs 存在 `metadata_json.initial_inputs`，后续 message 合并 Artifact refs。
- `interaction_mode`：`auto|chat|form|hybrid`。缺省/legacy = `auto`，由 typed inputs 推导 chat/form/hybrid，无领域关键词。Runtime 不按 mode 改 tool 语义。Studio Form 视图可编辑；Builder Composer bounded 推导。
- 路由：`#/projects/:id/agents/:aid` = App；`/design` = Studio；`/run?run_id=` = Run Detail；`/run` 无 run_id = App。树点击仍进 Studio；Open App 为 Play 次级链接。Test Run 文案仍是当前草稿。
- Preflight：Runtime model 未配置 → `runtime_not_configured`；GitHub 等 secret 缺口 → `needs_configuration`，不创建失败 Run。审批摘要 Server 生成。Cancel 走 Runtime stop；Retry 新 `run_id`，旧 Run 保留。
- Migration：`local_0033_agent_app_versions`（`agent_versions.committed`，conversation pin/metadata）。隐式 Test-Run version `committed=0`，Studio Commit 才 `mark_version_committed`。
- 验收：`tests/integration/local/test_agent_run_app.py`（committed vs Draft、pin、form/hybrid/image/document、approval、cancel/retry、runtime/github preflight）。Desktop AgentChatSurface + interaction-mode + activity。
- `env -u PYTHONPATH make check`：**901 passed**；ruff/mypy 通过。Desktop `npm test`：**67 files / 515 passed**；typecheck/build 通过；`git diff --check` 干净。未 stage / commit / push。
- 8771 已重启加载本轮代码与 `local_0033_agent_app_versions`：before `pid=34200` `database_revision=local_0032_factory_specification`；after `pid=21076` `status=ok` `database_ready=true` `database_revision=local_0033_agent_app_versions` `build_sha=0ad7a3e0…-dirty`。未重启 5173/5174/8772。
- 本环境无 browser MCP：Browser acceptance unavailable。
- 本轮明确未做：loop image generation、browser automation、完整 Policy Engine、advanced/vector RAG、MCP 产品化、任意 Tool 生成、Community marketplace、audio/video、完整桌面分发/签名。

## Current checkpoint（2026-09-28，Resource Factory V1）

- 产品模型未改：Agent = model/tool loop；Workflow = typed DAG。
- 主链：`missing_required` → `ResourceFactoryStrategy` / `ResourceFactoryPlan` → quarantined Draft → 校验 → 用户确认 → Workshop overlay 发布 → Catalog 发现 → Resolver retry → Composer pin/lock。Resolver 不 `force_select` factory 资源。
- 复用：`ResourceWorkshop` overlay/`approve`/`set_enabled`；Custom Component `tool_wrapper` 语义（declarative specialization，不新建 executor）；Catalog overlay + `factory` tag。无新 migration：Plan 存在既有 `factory_sessions.specification_json` extras（`resource_factory_plans` / `factory_wrappers`）。
- 策略：`generatable`（Skill / 已配置 wrapper）、`requires_user_configuration`（HTTP 需 host+endpoint；FS 需 path_prefix）、`requires_external_integration`（github_/mcp_）、`unsupported`（shell/python/eval/write/image/browser/policy）。
- Skill：结构化 instruction（Purpose / When to use / Procedure / Expected output / Constraints / Failure handling）；先 `quarantined` + `factory_selectable=false`；Approve 后 `ready`；改 instruction → 新 version draft，旧 lock hash 不变。
- Tool Wrapper：只特化 `veyra.runtime.http.request` 与 filesystem read/search/list；host/method/path_prefix 固化；wildcard HTTP、任意 URL/method/headers、shell/python/eval 拒绝。Runtime receipt 带 `factory_resource_id` / version / `base_adapter`。
- `env -u PYTHONPATH make check`：**890 passed**；ruff/mypy 通过。Desktop `npm test`：**65 files / 498 passed**；typecheck/build 通过；`git diff --check` 干净。未 stage / commit / push。
- 8771 已重启以加载本轮代码。未重启 5173/5174/8772。本环境无 browser MCP。
- 本轮明确未做：任意 Python/shell/JS Tool 生成、完整 Policy Engine、Template Factory、MCP 自动安装、image generation Runtime、browser automation、Agent Run App、Workflow Builder、Community Marketplace。

## Current checkpoint（2026-09-28，Resource Resolver & Agent Composer）

- 产品模型未改：Agent = model/tool loop；Workflow = typed DAG。
- create_agent：`derive_capability_requirements` → `ResourceResolver.resolve` → `ResourcePlan` → `compose_loop_agent`。Factory generate 不再调用 `_CAPABILITY_TOOLS` / `_select_tools`。
- Capability Requirement 不绑定 resource ID。Resolver 按 capability tags、availability、factory_selectable、runtime adapter、配置状态、Project pin ranking；tie-break 为更具体 capability 然后稳定 resource_id。
- ResourcePlan bind_status：`already_bound` / `will_bind` / `needs_configuration` / `missing`。Apply 使用 Proposal snapshot hash，不重新 resolve 最新 Catalog。
- Skill/Knowledge 由 metadata 与 Project inventory 进入 Composer；Policy 可绑定但 `runtime_support=partial`；Template `loop_compatible=false` 不进入 loop Agent。
- 验收：Translation 不过度装配；Research 选 Search+Skill+Knowledge；Workspace read-only 无 write；Editor write 保持 catalog `approval_required`；image_generation missing；GitHub needs_configuration；metadata-driven fixture 改变 capabilities 即改变选择；伪造 `veyra.tool.fake.super_search` 被拒绝。
- `env -u PYTHONPATH make check`：**854 passed**；ruff/mypy 通过。Desktop `npm test`：**65 files / 497 passed**；typecheck/build 通过；`git diff --check` 干净。未 stage / commit / push。
- 8771 已重启：before `pid=50514` `build_sha=0ad7a3e0…-dirty` `database_revision=local_0032_factory_specification`；after `pid=47898` 同 SHA / revision / `database_ready=true`。未重启 5173/5174/8772。
- 本轮明确未做：Resource Factory、自动生成 Skill/Tool/Policy、mature Run App、`interaction_mode`、loop 出图、完整 Policy Engine、高级 RAG、MCP 产品化、浏览器自动化。

## Current checkpoint（2026-09-28，Loop Agent Resource Truth）

- 产品模型未改：Agent = model/tool loop；Workflow = typed DAG。
- Catalog 存在 ≠ 可运行。Loop Agent 使用资源必须同时：Catalog 存在且 availability 允许、Project pin、Agent lock hash 一致、权限允许、Runtime adapter 存在、必要配置就绪。Apply 按 Proposal lock hash pin，禁止换成更新版本。
- Builder Proposal `resource_plan.bind_status`：`already_bound` / `will_bind` / `requires_configuration` / `unavailable`。Desktop Agent 方案显示「已在 Project 中 / 将加入 Project / 需要配置 / 不可用」。
- AgentLoopRuntime 加载 `skill_refs`（结构化 Skill prompt + `skill.loaded`）、复用 `read_knowledge_context`（`knowledge.retrieved`）、typed I/O 经既有 `_model_user_content`（image → Image ContentPart；document/pdf → 有界抽取）。HTTP/Browser 无 host allowlist fail-closed。Policy 绑定只发 `policy.partial`，Tool 级 approval/权限/网络仍 enforce。
- 验收 fixture：`tests/integration/local/test_loop_resource_truth.py`（Research / unbound / Apply pin / Skill / Knowledge marker / image / document / PDF / Workspace Inspector）。未调用真实外部 Provider。
- `env -u PYTHONPATH make check`：**831 passed**；ruff format/check、mypy 通过。Desktop `npm test`：**65 files / 497 passed**；`npm run typecheck` 通过；`npm run build` 通过（既有 >500 KB chunk warning）；`git diff --check` 干净。
- 未 stage / commit / push。8771 仍是旧进程，需重启后 Factory Apply pin 与 loop Resource Truth 才对正在跑的本机服务生效。本环境无 browser MCP：Browser acceptance unavailable。
- 本轮明确未做：Resource Resolver ranking、NL Skill/Tool generation、完整 Resource Factory、loop 出图、Packaging Designer 终稿、mature Run App、`interaction_mode`、完整 Policy Engine、PDF/vector RAG、MCP 产品化、浏览器自动化。

## Current checkpoint（2026-09-28，Agent / Workflow 产品模型分开 — 门禁）

- `env -u PYTHONPATH make check`：**808 passed**；ruff format/check、mypy 通过。
- Desktop `npm test`：**65 files / 497 passed**；`npm run typecheck` 通过；
  `npm run build` 通过（既有 >500 KB chunk warning）；`git diff --check` 干净。
- 未 stage / commit / push。8771 在本轮结束后需要加载新代码。本环境无 browser
  MCP，未能在 5173 实际点击创建 Agent/Workflow；Project 树 / Studio / Runs 由
  Desktop 测试覆盖。
- 本轮不做 Community marketplace、RAG、Loop/Parallel/Schedule/Webhook 节点、
  AV Runtime、浏览器自动化。

## Current checkpoint（2026-09-28，Agent / Workflow 产品模型分开 — Studio / tree / Runs）

- 上一轮中断的 AgentSpecification 主链未回滚：规格改造成 loop Agent；SemanticPlan / typed
  dataflow / quality / simulation 归 Workflow。Factory generate 不再走 SemanticPlan DAG。
- Builder 分类 `create_agent` / `create_workflow`；create 指令使用用户原文，interview
  Provider 失败在 Builder 路径会重新抛出。
- Desktop Project 树现为 Agents / Workflows / Knowledge / Files / Runs。Agent Studio
  是能力图 + 运行时间线；Workflow Studio 是 typed DAG，左侧 Agents/Tools/Logic/Human/Data/Output。
- 未 stage / commit / push；保留 Community / Cloud dirty work。本轮不做 Community /
  RAG / Loop 节点 / Parallel / Scheduler / Webhook / AV / Browser automation。

## Current checkpoint（2026-09-28，Agent / Workflow 产品模型分开）

- 用户停止了「AgentSpecification → SemanticPlan → 把每个 Agent 编译成复杂 DAG」主链。
  未 reset / restore / clean / stash / rebase / commit / push。上一轮 typed dataflow
  保留为 Workflow 基础设施；AgentSpecification 改造成 loop Agent 规格，不走 DAG compiler。
- 产品：Agent = 自主 loop；Workflow = typed DAG。Builder 分类 `create_agent` /
  `create_workflow`。AgentRuntime 是 model/tool loop（`max_turns`）；Workflow
  AgentCall 调用已提交 Agent version。Desktop Agent Studio 是能力图，Workflow
  Studio 是节点 DAG。Runs 带 `run_target_kind`。
- 旧 graph Agent 保持 `execution_kind=graph`，可打开，不静默迁移。
- 未 stage / commit / push；保留 Community / Cloud dirty work。

## Current checkpoint（2026-09-27，类型化 I/O 按内容可用）

- 产品目标不再是 V1 窄契约：图片/PDF/文档要能输入、预览和显示结果。Chat 与 Studio Test Run 共用 `RuntimeInputForm` / `RuntimeOutputView`；必填 Artifact 未上传不能开跑。
- 编译：PDF/document/file 输入可编译，Runtime 抽文本；image 输出编译为 `model.image`（纯图直接改终端 Model，混合输出追加生成步）。不再因缺少 image_generation Tool 把生成挡住。PDF 输出仍要 renderer。Factory 原语要求真实 compact type，禁止把照片写成 string、把出图改成 prompt 数组。
- Chat 把纯图片/文件结果留在对话里直接渲染，不再当成 JSON 打开结果画布。画布里的结构化结果也走 `RuntimeOutputView`，混合输出里的图能显示。
- 验证：compiler / hardening / extract **80 passed**；ruff 通过；Desktop Chat + Runtime I/O + canvas **20 passed**；Test Run panel **7 passed**。未 stage / commit / push。8771 仍是旧进程，需重启后新生成的 Agent 才会带 `model.image`。已有礼品包装设计师需重新生成。运行 image 输出仍需绑定 User Runtime image model。未做真实浏览器复验（本环境无 browser 工具）。

## Current checkpoint（2026-09-27，生成质量是执行模型问题）

- 生成 Agent 效果差的根因不是 prompt 里少几条禁令。Factory 把用户一句话立刻标 ready 并一次生成图；SemanticPlan 禁止步骤数据流，但 Factory 仍生成「分析→草案→确认→终稿」这种看起来像流水线的图；HumanApproval 的 rejected 以前一律接到 Output，所以模型只能再发明 `decision == "confirm"`；Runtime 只有共享 values 袋，审批不写业务字段；编译器写的 Model prompt 几乎没有字段说明和步骤契约。历史 Builder real-provider 验收也卡在 Condition 无法做自然语言分类、Transform 无法读上一步 Model。
- 本轮按可运行原语改 harness，而不是再堆 Don't：`RUNNABLE_AGENT_PRIMITIVES` 进入 create_agent / planning / repair；policy `builder-policy-v2`。HumanApproval 可用 `branch_key=approved|rejected` 接两条后续职责。编译器会把「审批后再用 Condition(confirm)」折叠成审批端口。中间 Model 写 named working note，终态 Model 才交 Agent JSON，prompt 带输出 description。
- 验证：compiler/hardening/condition/capabilities **94 passed**；factory/builder/contracts **84 passed**；ruff + mypy 通过。未 stage / commit / push。已有「礼品包装设计师」是旧编译源，需重新生成后才走审批双端口。8771 需加载此代码后新生成才生效。

## Current checkpoint（2026-09-27，生成 Agent 按步骤可用）

- 礼品包装设计师新运行 `01a0e24e-a94f` 已跑完（unverified）。详情页红字是更早的 `01a0e247`。批准后 `decision` 为空，条件 `decision == "confirm"` 走了修改分支，跳过最终方案；`image-generation-prompts` 为空数组。
- 中间 Model 不再被要求交最终 JSON，只把步骤笔记交给下一个节点；能直接走到 Output 的 Model 才校验 Agent 输出。空白批准会填上条件里的确认字面量；用户已填写的意见保留。
- 编译器只让最后一级 Model 写最终字段契约。运行画布连线使用明确描边。
- 验证：capabilities / compiler **55 passed**；ruff 通过。未 stage / commit。8771 需加载后，已有 Agent 的下一次运行才按新规则执行。

## Current checkpoint（2026-09-27，Test Run JSON 输出失败）

- 礼品包装设计师 `analyze_item` 失败码 `agent_output_invalid`：Agent 输出是 `object`/`array`，Runtime 要 JSON；kimi-k3 回了 Markdown 分析。HTTP Runtime 未发 `response_format`。
- 现对结构化输出发送 `response_format=json_object`，并在 system prompt 末尾追加权威字段名（YAML slug，如 `final-packaging-design`）。编译器提示也改用 slug。不从 Markdown 刮 JSON。
- 验证：unit client/capabilities/compiler **57 passed**；ruff 通过。未 stage / commit / push。8771 需加载此代码后才能对这次 Agent 生效。

## Current checkpoint（2026-09-27，Test Run 图像预检是旧 8771）

- 礼品包装设计师有 image 输入；当时 8771 未 reload，仍把 `kimi-k3` 标成 `image_input=unsupported`。磁盘能力表已开放。已重启 8771：该 Agent `runtime-readiness.ready=true`，`image_input=supported`。
- Studio 左侧 Model「待配置」是目录只看 host `RuntimeModelClient.configured`，忽略已就绪的 User Runtime Provider。现与 `runtime/status` 同一套判断。
- 验证：unit readiness/capabilities **20 passed**；ruff 通过；live `/runtime-readiness` ready。未 stage / commit / push。

## Current checkpoint（2026-09-27，Runtime 模态开放 + 文档抽取）

- 用户策略：用户绑定的 Runtime 模型默认开放图像输入，不为「其它模型」fail-close；PDF / 文档 / Office / 普通文件应对模型开放，而不是在 Run 前挡住。
- `RuntimeModelCapabilities`：精确 model id。`kimi-k3` 以及其它用户绑定模型 `image_input=supported`。仅 `kimi-k2`、`moonshot-v1-8k`、`moonshot-v1-32k` 保持图像关闭。`video_input` / `audio_input` 仍为 unsupported（adapter 未启用）。
- 非图像 Artifact 经 `artifacts/extract.py` 抽取有界纯文本写入 prompt；图像仍走 `image_url` data URL。Run JSON / events 不含 bytes、host path 或 `artifact://`。文件夹不是 ArtifactRef 种类。
- 验证：pytest 24 passed（capabilities / extract / artifact runtime / runtime status）；ruff check 通过；mypy 4 files 通过；Desktop `local-client.test.ts` 40 passed。未 stage / commit / push；保留其它未归属 working-tree 修改。未做真实浏览器 Test Run 复验。

## Current checkpoint（2026-09-27，Runtime 预检误报未绑定）

- 账号默认 User Runtime Provider 解析为内部 `user_default` / Agent 绑定为 `explicit` 时，Studio `runtime-readiness` 解析失败，测试运行误报「尚未绑定」。
- 现将预检 `profile_source` 映射为契约值 `agent` / `project` / `default`；前端同时接受旧值，并在预检失败时回退 `runtime/status`。
- Studio Model 节点检查器是 `model.primary` → User Runtime Provider / 模型的调用映射；绑定写 `runtime_bindings`，不把 API Key 或 credential id 写进 Agent 源。
- 验证：capabilities / credential readiness pytest **14 passed**；Desktop `local-client.test.ts` **41 passed**。未 stage / commit / push。

## Current checkpoint（2026-09-27，不再做 Cloud data plane）

- 对照 `0ad7a3e0b2a11ccf9186f23dab40628375509c73`：生成、Chat 和本机页面在这一版是正常的。之后的 Cloud Project / Conversation / File / Credential / Run 不再是产品。
- `5173` + `8771` 是本机软件。`5174` 只保留公开展示和社区目录/账号。`8772` 启动 `veyra_agent_platform.community.app:app`。
- Desktop 不再自动把 Project 或 Builder 对话同步到云端。最近聊天读本机 Builder activity。
- 文档已改：`README.md`、`docs/PROJECT_DESIGN.md`、`docs/AI_DEVELOPMENT_BRIEF.md`、`docs/DEVELOPMENT.md`。未 stage、commit 或 push。

## Current checkpoint（2026-09-27，Connected Account workspace redesign）

- Desktop `#/account` 已从两张同权重大卡片重组为三层：账号身份摘要、公开资料编辑、会话与设备安全。身份摘要同时显示头像、display name、handle、登录邮箱、连接状态与“Community 元数据 / 本机执行”边界。
- 公开资料表单保留原头像选择/替换/删除、display name、handle、只读登录邮箱和显式保存行为；字段改为响应式两列，头像编辑独立成浅色编辑区，保存动作放在表单 footer。
- 根据原 Account / Community 设计补入“Community 中的你”：真实链接到 Creator workspace、Published releases、Starred resources，并展示当前已启用的发布不可变版本、保存/评审和 Fork lineage 能力；未展示尚未实现的组织、计费或私有备份。
- 新增明确的本机数据边界清单：Project / Agent / Workflow source、Run / approval / receipt、Secret 值和主机凭据不会因登录自动上传或按账号分割；只有显式 Publish/Sync 才离开设备。
- 会话列表不再直接显示长 User-Agent。浏览器与平台会归一为 `Mac · Chrome`、`Windows · Edge` 等；显式 `device_name` 仍优先保留。当前会话显示“退出此设备”，其它会话显示“撤销访问”。桌面端 17 个真实会话使用固定高度内部滚动，窄屏恢复自然页面滚动。
- 退出账号独立为 Account access 区，并明确只结束登录，不删除本地 Project 或 Community release。未修改 account/session API，也未执行头像、资料、撤销或退出 mutation。
- 验证：Desktop 全量 **66 files / 490 tests passed**；Account/App 定向 **59 passed**；Desktop typecheck、production build 与 `git diff --check` 通过；保留既有 Vite >500 KB chunk warning 与 jsdom Canvas stderr。实际浏览器检查了当前真实账号、Community 路由卡、17 个会话、浅色/暗色与窄 viewport。
- 未 stage、commit 或 push；保留其它未归属 working-tree 修改。

## Current checkpoint（2026-09-27，Creator workspace redesign + Star state consistency）

- Desktop `#/community/mine` 已改为紧凑的创作者工作台：真实 Published / In review / Rejected / Total stars 指标，完整单块 Release Studio 背景，以及 Agent / Project / Workflow / Plugin Pack / Template / reusable resources 六类发布入口。
- 当前真正接通 Community 发布的仍只有 Agent immutable release 与 declarative Plugin Pack。Project 只有现有本地 `.vproject.zip` export，Community Registry publication 尚未实现；Workflow / Template / Component / Tool / standalone Skill 同样以 planned 状态显示，不伪装为可点击能力。
- Agent 与 Plugin Pack 选择、来源选择、检查和确认都留在同一 Release Studio 内；删除了并不存在持久后端的 Community Draft 指标和空白草稿面板。Discover 恢复紧凑的 Community 标题与真实能力说明。
- 修复 Discover 与 Published 对同一 release 收藏图标不一致：Published 现在与 Discover 共用认证 `listStarredRegistryAgents()` 恢复的 version-bound Star 集合；Starred 页仍以列表本身作为权威集合。新增 Published 同步回归测试。
- 验证：Desktop 全量 **66 files / 490 tests passed**；Community + App 定向 **64 passed**；Desktop typecheck、production build、`git diff --check` 通过。保留既有 Vite >500 KB chunk warning 与 jsdom Canvas stderr。
- 实际浏览器：浅色/暗色与窄 viewport 下检查 Mine；Agent / Plugin Pack 切换正常；真实 Discover 与 Published 对同一 `Community Acceptance Transform Agent` 都显示“取消收藏”。没有调用发布、上传、Star/Unstar 或其它 mutation。
- 未 stage、commit 或 push；保留其它未归属 working-tree 修改。

## Current checkpoint（2026-09-26，Community flagship visual refinement）

- 在上一轮 Community information architecture 基础上继续收敛视觉：Discover 从大块营销 Hero 改成轻量产品头部；Published 改为紧凑版本记录；Starred 有独立标题和可控空态；Mine 收紧标题和发布区留白。
- 统一使用克制的浅色/暗色 token、GitHub 风格底线导航、版本记录行、轻量 hover/淡入/轨道浮动动效；`prefers-reduced-motion` 会关闭动画。
- 保留真实 Registry / Star / Review / 发布导入 API、现有路由和侧栏；没有新增假指标、假帖子或未实现资源类型入口。
- 实际 Chrome 检查：Discover、Published、Starred、Mine 四个页面在当前 5173 正常渲染；Published 不再一条记录占满整屏，Starred 不再使用大块空白卡片。
- 验证：Desktop 全量 **488 passed**；Desktop typecheck；Web Desktop/Community build；Desktop build 的既存 >500 KB chunk warning 与 jsdom Canvas stderr 保留。
- 未 stage、commit 或 push。不要 reset/clean/stash/覆盖其它未归属改动。

## Current checkpoint（2026-09-26，Community catalog view switch）

- Discover / Starred 现在支持卡片与按行两种真实显示模式，按钮使用 `aria-pressed`，偏好保存到 `veyra.community-view-mode.v1`，刷新后保留。
- 列表模式已在 Chrome 5173 实际点击确认，显示为紧凑 release row；随后已恢复默认卡片模式。
- 只改 Community Page/Card/CSS 相关 UI，并修复一个重复 mine loader 的 TypeScript 不可达分支；没有改 Community 后端、契约或数据。
- 定向 Community page tests **3 passed**；Desktop 全量 **488 passed**；Desktop typecheck/build 通过。未 stage、commit 或 push。

## Current checkpoint（2026-09-26，Community reference design implementation）

- 当前 Community UI 已按用户提供的主设计图落地：Discover 为 Community + 几何装饰 + search/category chips/recommended cards；Published 为 metrics/filter/table；Starred 为 search/sort/card collection；Mine 为 Creator Center + metrics + resource launch tiles + recent releases + draft boundary。
- Discover / Starred 的 grid/list toggle 已保留并实际验证；card preview 是声明式 Agent graph visual，不是伪造的资源截图或后端字段。
- 未实现的 Workflow/Skill/Tool/Plugin discovery 不伪装为可用；Plugin Pack 的现有 publish lane 在 Creator Center 可展开。
- Desktop 全量 **488 passed**；App suite **59 passed**；Community 页面定向 **3 passed**；Web build、Desktop typecheck 通过；已有大 chunk/jsdom warnings 保留。
- 未 stage、commit 或 push。

## Current checkpoint（2026-09-26，Community information architecture and visual refresh）

- Desktop Community 当前工作树已从发布后台式布局刷新为开发者社区入口：Discover 有社区 Hero、真实 Agent release feed、版本检查路径、下一步引导和诚实的 Discussions coming-next 状态；`mine` 是创作者工作台，发布为主列、版本与安全检查为侧栏，Plugin Packs 默认折叠。
- 只改了 `web/apps/desktop/src/pages/community.tsx`、`web/apps/desktop/src/features/community/community.css`、`web/packages/connected-account/src/styles.css` 的本轮社区 UI；已有 Community 发布/导入/Star/Review/API 和其它 dirty worktree 范围保持不动。
- 讨论帖子、creator follow、Feed 后端仍不存在，当前 UI 不伪造内容；版本详情的真实评价仍是现阶段可用的交流边界。
- 实际浏览器检查：5173 Discover 与 Mine 浅色、深色均正常；页内 Browse releases / Start publishing 不改变路由；Mine 下方 Plugin Packs 已变为折叠 secondary lane。
- 验证：Desktop 全量 **488 passed**；Web Community **23 passed**；Web typecheck、Desktop build、Community build 通过。Desktop build 仍有既存大 chunk warning；测试仍有既存 jsdom Canvas stderr。
- 未 stage、commit 或 push。不要 reset/clean/stash/覆盖其它未归属改动。

## Current checkpoint（2026-09-23，5174 Showcase V1）

- Branch：`codex/agent-platform`；HEAD：`0ad7a3e0b2a11ccf9186f23dab40628375509c73`；working tree dirty，未暂存。
- Product boundary：5173 Desktop owns daily work and Community interaction；8771 is Local API；8772 is the separate Community account/Registry service；5174 is the anonymous Public Showcase.
- 5174 now serves product/features/how-it-works/safety/sharing/docs/build-status sections. It has no account/Registry routes or `/api` proxy and renders while 8772 is offline. `web/apps/community` package rename and unreachable legacy-page cleanup are deferred.
- Verified content is bilingual, light/dark aware, responsive by CSS breakpoints, and explicit that the preview is illustrative and no public installer is available. Repository links are on the active branch and may require GitHub access.
- Browser evidence: actual 5174 root and sections rendered with 8772 down; legacy `#/community/published` reload normalized to `#home`; Chinese/English and light/dark toggles worked; 200% zoom showed the collapsed mobile navigation breakpoint. The user took control before the narrow-screen menu click, so that interaction is covered by unit test, not claimed as manual mobile E2E.
- Tests: Showcase focused 22 passed; full web Desktop 472 + Community 22 passed; both typechecks/builds passed. `conda run -n veyra-agent-platform env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`: 703 passed, Ruff format/check, dependency/lock and mypy 187 files passed. Desktop 1.16 MB bundle-size warning and existing Alembic `path_separator` deprecation warnings remain; Showcase JS bundle is 230.93 KB.
- Offline acceptance was run with 8772 stopped: 5174 root stayed HTTP 200, legacy Registry hash returned to `#home`, and the page showed no Registry/account controls. Afterward the four-service stack was started with real settings: 5173/5174 HTTP 200; 8771/8772 HTTP 200, `database_ready=true`, revisions `local_0026_builder_semantic_plan` / `community_0008_plugin_registry`, build `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`. The DBs were already at head; no migration ran.
- No migration, Registry/API/schema/data change, Builder Provider call, or Project data mutation. No staging, commit, push, PR, or tag.
- Preserve the existing Community Sharing work, independent shell/sidebar/scroll UI edits, `$DB`, `.backboard/sessions/`, and `.backboard/settings.json`; none is to be reset or swept into a commit.
- Next: keep this slice bounded. If the user later authorizes it, handle public GitHub/document access and publishable desktop artifacts separately; do not resume Community Marketplace expansion.

## Historical checkpoint（2026-09-22，Agent Composition Slice 5 locally verified；状态已被后续记录取代）

- Branch：`codex/agent-platform` → `origin/codex/agent-platform`
- 权威 release HEAD：`5f8e8a8bda0946b1f29cdae38ee4cedaa3560fbe`
- Graph Compiler V2：`8bef91c9cd546717b30134059172c74ceedc6289`
- Typed I/O + Artifact Runtime：**released** at `5f8e8a8`
- Builder Workspace/Test 位于每次 Builder operation 的 Conversation 历史中，
  不是固定右侧栏
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`、`$DB`，
  也不误改无关的 `shell.tsx` / `shell.css` / `app.test.tsx`
- 不要重开 Graph Compiler V2、Typed I/O、Conversation Test 布局或 Slice 1
- 不要创建独立 Playground，不要把 Conversation Artifact Binding 当主任务
- 暂停：autonomous Run、Community redesign、behavioral eval / LLM judge、
  unsandboxed AI code、fake Vision/PDF/image gen、Workflow Builder Compiler
- 当前状态：Agent Composition & Capability System V1 Slice 1–5 已本地实现并通过当前本地门禁；
  Slice 5 尚待真实浏览器/Provider/sidecar 验收与 release checkpoint
- Conda 环境 `veyra-agent-platform` 下 `env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`
  通过：695 passed；Ruff format/check、mypy、dependency/lock checks 通过
- Web 全量测试通过：Desktop 59 files / 463 tests，Community 3 files / 15 tests；
  两应用 typecheck 与双应用 production build 通过（Desktop 主 JS chunk 超过 500 KB）
- Slice 5 聚焦 Desktop 测试：133 passed；新增 Studio/Builder 共用 Runtime Canvas、
  immutable version 恢复、workspace Run 隔离、审批继续、SSE reconnect 与安全 inspector 覆盖
- `git diff --check` 通过；没有真实浏览器 E2E、真实 Provider/sidecar 或 release 验收
- Slice 1–5 仍未提交/推送，不代表已发布
- 不提交、不推送，也不做 reset/checkout/clean/stash/restore/rebase

Slice 1 reference baseline（本轮不重做）：

- 单职责翻译/摘要仍允许 Start → Model → Output
- 多职责 `steps` 不再静默压成一个 Model prompt
- `step_intents` 可带 `capability_requirement`（Project-bound name/id）
- 优先复用已绑定、ready、唯一匹配的 Project Resource Library 能力
- 不 Catalog auto-install，不静默造 Tool，不假装 vision ready

原则：

- Agent I/O is typed by user intent.
- Binary values are ArtifactRefs, not inline Run JSON.
- Declared modality does not imply runtime capability.
- Missing parser/renderer/generator must remain a truthful missing capability.
- Manual Canvas and AI Builder compile the same canonical AgentSource.

### Typed I/O Slice E

- `RuntimeModelCapabilities` 与 Builder `ProviderCapabilityProfile` 严格分开
- Moonshot `kimi-k3`：`image_input=unsupported`；`unknown != supported`
- Runtime readiness 增加 `modalities` check；Run 前失败
  `runtime_model_incompatible` / `unsupported_modality`
- Model adapter 可组 OpenAI-compatible `image_url` parts；HTTP 边界拒绝
  `file://`、host path、`artifact://`。Vision 实际发送时改写为 data URL，
  不把 bytes 写入 Run JSON / events
- 当前真实 Runtime Model 不支持 vision：CASE C 必须在 Run 前 truthful 失败

### Typed I/O Slice F

- 共享 `RuntimeInputForm` / `RuntimeOutputView`
- Studio Test、Workflow Test、Builder Test、Run Detail 共用
- `FactoryTestRun` 是旧 UI 死路径（产品入口是 `ProjectBuilderConversation`），
  不实现 Typed I/O，也不继续扩展
- 未做完整 Playground page

### Typed I/O Slice A

- Agent/Workflow `inputs`/`outputs` 解析为 `TypedField`
- 旧 compact map（`text: string`）继续 parse/run；等价字段仍 compact 序列化，
  github-triage fixture 的 `behavior_hash` 不变
- 用户可见类型：string/number/integer/boolean/object/array/table 以及
  image/pdf/document/file/audio/video（底层 `type: artifact` + `artifact_kind`）
- 声明 modality ≠ Runtime capability。image/pdf 不得退化成 string
- Factory 兼容 schema 仍然只生成 compact scalar/json，不向 Kimi 暴露 artifact

### Typed I/O Slice B

- 复用 `local/storage/objects.py`：`objects/sha256/<digest>`
- `ArtifactRecord` / `to_ref()`；bytes 不进 JSON
- Alembic head：`local_0025_project_artifacts`
- Project-scoped multipart upload：
  `POST /api/v1/projects/{project_id}/artifacts`
- metadata / content 读取都要求 `project_id` + `artifact_id`
- filename sanitize、magic sniff、extension/claimed MIME consistency、8MB 上限
- 不暴露 host path；不信任客户端 MIME alone

### Typed I/O Slice C

- Runtime `_prepare_inputs` / `_prepare_outputs` 解析 ArtifactRef 或 `$artifact`
- Project isolation、存在性、MIME/accepted media 在 Run 前失败
- `inputs_json` / `result_json` 只存 ArtifactRef，不含 bytes
- Tool `produced_artifacts` → object store + `artifact.created`
  （artifact_id / media_type / filename / size / digest / node_id）
- 事件 payload 拒绝 binary keys

### Typed I/O Slice D

- SemanticPlan 扩展 compact 类型（含 image/pdf/document/file/audio/video）
  与 `multiple`；不放 artifact_id / storage_ref
- Compiler 保留 multiple outputs；一个 Output node 可收集多字段
- pdf_parser / pdf_renderer / image_generation / unsupported_modality
  仅在 Project-bound Resource 存在时生成 Tool
- image → text 可编译，并警告 `requires_runtime_image_input`

Focused evidence（未 commit）：

- pytest typed I/O + artifacts + runtime routes + compiler + composition +
  factory schema：163 + 5 passed
- ruff/mypy on Runtime modality modules：clean
- desktop typecheck：pass
- desktop vitest runtime form/output + Builder/Studio/client：113 passed
- 服务已用真实 `.env` 重启：
  Desktop `5173` → 200；Community `5174` → 200；
  Local `8771` `build_sha=8bef91c-typed-io-dirty` /
  `local_0025_project_artifacts` / `database_ready=true`；
  Community `8772` 同 SHA。
  Builder Model：Moonshot `kimi-k3`（`https://api.moonshot.cn/v1`，
  `strict_json_schema_support=supported`）。
  Runtime Model：Moonshot `kimi-k3`（同 endpoint，`MOONSHOT_API_KEY`）。
  Runtime modalities：`text_input=supported`，
  `image_input=unsupported`，`structured_json_output=supported`，
  `source=static_profile`。unknown ≠ supported。

### Typed I/O Slice A

- Agent/Workflow `inputs`/`outputs` 解析为 `TypedField`
- 旧 compact map（`text: string`）继续 parse/run；等价字段仍 compact 序列化，
  github-triage fixture 的 `behavior_hash` 不变
- 用户可见类型：string/number/integer/boolean/object/array/table 以及
  image/pdf/document/file/audio/video（底层 `type: artifact` + `artifact_kind`）
- 声明 modality ≠ Runtime capability。image/pdf 不得退化成 string
- Runtime 对 Artifact 值做 ArtifactRef shape 校验（store 隔离在 Slice B/C）
- SemanticPlan 仍是 string/number/boolean（Slice D）
- Factory 兼容 schema 仍然只生成 compact scalar/json，不向 Kimi 暴露 artifact

### Typed I/O Slice B

- 复用 `local/storage/objects.py`：`objects/sha256/<digest>`
- `ArtifactRecord` / `to_ref()`；bytes 不进 JSON
- Alembic head：`local_0025_project_artifacts`
- Project-scoped multipart upload：
  `POST /api/v1/projects/{project_id}/artifacts`
- metadata / content 读取都要求 `project_id` + `artifact_id`
- filename sanitize、magic sniff、extension/claimed MIME consistency、8MB 上限
- 不暴露 host path；不信任客户端 MIME alone

Focused evidence（未 commit）：

- pytest typed I/O + contracts + templates + schema + factory/compiler +
  resource binding + workflow versions + runtime/import/factory routes：
  132 + 62 passed（Slice A）
- ruff/mypy on Slice A modules：clean
- desktop typecheck：pass
- desktop vitest graph/TestRun/BuilderTest/studio：53 passed
  （另一次全量 desktop vitest 422 passed，含无关既有 dirty UI 测试）

CASE C 根因：MFJS 投影把 `properties.then` 当成 JSON Schema combinator
剥掉，Kimi 在 `branches` 上连续三次 `missing field(s): then`。
Provider-facing schema 已去掉 `branches`；server 展开 extra ports。

Live（Moonshot / kimi-k3，未 Apply）：

- CASE A：Start → Model → Output
- CASE B：Model ×3
- CASE C：Start → Model → HumanApproval → Model → Output
  （风险项/行动建议不能映射 `output.not_empty`，不造假 Verifier）
- CASE E：真实 `condition` intent。限制：false 口接到 Output；
  expression 可能落到 `result != ""`，不能表达完整 empty/supplement 分支

裸 CASE C 文本可能被 resolver 判成 Workflow；「做一个 Agent：…」后才进入
SemanticPlan。这是 resolver 边界，不是 Compiler 失败。

已知缺口继续记录：

- Agent Playground **NOT IMPLEMENTED**
- Workflow Builder Compiler **NOT IMPLEMENTED**
- 旧 Factory session 目前只恢复最新 canvas；multi-artifact Conversation 有限
- 手写 PDF input Agent 的 Runtime readiness 不会自动标 `pdf_parser` missing；
  Compiler 在无 Project-bound parser 时 truthful。Runtime 不 UTF-8 decode PDF
- Builder Phase 2 Playwright CASE 1–3 未在本环境执行
- 本轮 authenticated Desktop UI 停在登录页；仓库内无 Playwright 套件

### Compiler V2 边界

- Agent = 可独立执行的能力内部图：Start / Model / Tool / Condition /
  Transform / HumanApproval / Verifier / Output
- Workflow = 多个 immutable Agent version 的编排；AgentCall 只属于 Workflow
- SemanticPlan V2：可选 `step_intents`（semantic_key / name / purpose /
  operation_kind / depends_on）。模型不输出 node/edge id、hash、permission、
  lock、canvas 坐标
- 无 `step_intents`：Start → Model → Output
- 有真实职责边界：多 Model，以及可映射的 Tool / Transform / Condition /
  HumanApproval / Verifier
- Resource resolution 复用现有 deterministic resolver
- Knowledge 保持 binding
- `ui.notes` 默认存在、可删、不进 `behavior_hash`
- `ui.labels` 是画布语义标题；Inspector 显示 component type

### 窄审计（Slice 4 Test Run 连接点，仍有效）

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

### 四服务（当前）

真实配置，无 temp DB / temp project root / loopback fake provider：

- Desktop `5173` → 200
- Community `5174` → 200
- Local `8771` `build_sha=8f71a1e-compiler-v2-dirty` /
  `local_0024_builder_conversation_trash` / `database_ready=true` / `status=ok`
- Community API `8772` `build_sha=8f71a1e-compiler-v2-dirty` /
  `community_0008_plugin_registry` / `database_ready=true` / `status=ok`
- **Builder Model**：Moonshot / `kimi-k3` / `known` + `source=probe`
- **Agent Runtime Model**：host default Moonshot / `kimi-k3` /
  `https://api.moonshot.cn/v1` / `configured=true`
- 真实 Projects 仍在：`dddd` / `test` / `New project`

Compiler V2 live（New project，**未 Confirm / 未 Apply**）：

- CASE A retry：`Start → Model → Output` + `ui.labels.translate=中英文互译` + default Note
- CASE B：`Start → Model ×3 → Output`，labels 资料总结 / 风险分析 / 建议生成 + Note
- CASE C：live Kimi 三次未产出合法 Semantic Plan（compiler 单测仍覆盖
  HumanApproval + Verifier）
- CASE D：resolver 澄清（New project 无 filesystem.read pin）；compiler 单测覆盖
  Tool pin 与 missing_capability

不要把这些 waiting 会话自动 Apply。

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
3. 工作树保留 Slice 1–4 + Factory MFJS 兼容桥 + Durable Conversation +
   Semantic Plan/Compiler + Interaction Model V2 + ProviderCapabilityProfile。
4. 当前交付边界：Slice 4 已本地完成；停止于此，不开始 Slice 5。
5. 不 commit、不 push、不重做 Slice 1–4、不改右上 Runtime History 语义。

## Agent Composition V1 — Slice 3（2026-09-22，已实现并通过本地门禁；未发布）

本节记录 **Agent Composition & Capability System V1** 的 Slice 3 状态，不覆盖
Builder Phase 2 历史编号的 Slice 3 记录。Slice 1/2 与此前工作区改动均保留；
Slice 4 已由后续交接记录完成。不要 commit 或 push。

### 已实现行为

- Capability resolution 仅考虑当前 Project 已 pin 且 ready、supported 的
  Component。唯一匹配时复用；多个匹配时先澄清；若匹配项为
  `requires_configuration`，则提示配置，不静默创建重复项。
- 缺少受支持能力时，经现有 EditProposal、Builder operation/event 和
  Workbench 流程创建 Component proposal；不另建一套 proposal service，
  proposal 生成本身不改动或发布资源。
- Component review 展示输入/输出、实现方式、依赖、权限与 readiness，以及
  预期 Agent 步骤。确认是显式操作并检查过期状态；Reject 后 Component 和
  Agent 均不变。
- 直接 `create_component` 只进入独立确认的 Component 流程，不创建 Agent；
  创建结果可跳转到 Project Resource Library。
- Agent 请求因缺少能力而阻塞时，确认 Component 只会发布 Component。系统随后
  基于当前 Project Resource Library 重新 resolution 原 semantic plan，再单独
  展示 Agent Blueprint review 和确认。Component 精确的
  `resource_id@version` 与 hash 会传入编译、resource plan、`AgentSource.lock`
  和 export。
- 发布成功后的重试复用现有 Component，避免重复创建。Apply、validation 或
  continuation 失败会记录为失败的 Builder operation/event，并停止后续流程。
- 实现范围限制为安全的 `model_recipe`、`transform`，或精确引用已绑定到当前
  Project 的 `tool_wrapper`。不执行任意代码、不创建 Tool、不自动从 Catalog
  安装，也不虚报能力。Composite graph 仍是 design-only；图像/PDF 等尚不支持的
  artifact 能力会明确保持 unresolved。
- Desktop 进入 Project Resource Library 时读取项目资源，并能在那里看到新建的
  Component；相关路由和 scaffold wiring 有回归测试。

### 本地验证

- `env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`：通过；后端
  **693 passed**，dependency/lock 检查、Ruff format/check、mypy 均通过。
- `npm test --workspace=@veyra/desktop`：通过，**55 files / 439 tests**。
- `npm run typecheck --workspace=@veyra/desktop`：通过。
- Builder/Component/Resource/client/Studio 聚焦测试：**6 个文件共 107 passed**；
  最后修正 provenance/route scope 后，另一次后端定向回归 **5 tests passed**。
- `git diff --check`：通过。

以上是本地自动化检查，不等于浏览器产品验收或发布证明。目前没有完成真实浏览器
端到端验收、真实 Provider/sidecar 验收、当前修订的 GitHub CI 或 release
checkpoint。不要称 Slice 3 已发布或已通过生产验收。当前设计与状态见
`docs/DEVELOPMENT.md` 和 `docs/PROJECT_DESIGN.md`。

## Agent Composition V1 — Slice 4（2026-09-22，已实现并通过本地门禁；未发布）

Slice 4 范围为 **Graph Layout + Default Note centered placement**。保留 Slice 1–3
以及工作树中独立 UI 改动；不开始 Slice 5，不提交、不推送。所有变化仍是本地
未提交实现，不代表发布或真实产品验收。

### 已实现行为

- 新增共享、确定性的 DAG 分层布局：按最长前驱深度放置节点，稳定排序分支与合流，
  为 true/approved/passed 与 false/rejected/failed 路径提供可读分支位置；布局只写
  坐标，不增删节点/边，不改端口、顺序或执行语义。
- Studio/Workflow 缺失位置时使用该布局；已有保存坐标作为固定位置保留。Auto Layout
  是显式操作，不会因为页面挂载而重排旧图。
- Builder `FactoryAssemblyCanvas` 与 Studio/Workflow 共用布局 helper，显示语义化边标签；
  Approval 与 Custom Component 按估算节点尺寸参与排布。
- Default Note 放在执行图 bounding box 上方居中，并排除在执行图 bbox 计算之外；
  fit view 范围包含 Note 和执行图。Note 仍可编辑/删除，不带执行 handles。
- 默认 Note 使用可选的 `ui.notes[].manual_position` 标记手动定位；用户拖动后保存/重载及
  Auto Layout 均保留位置。旧的默认 Note 自动坐标可重新居中，旧的自定义坐标视为手动位置。
- Agent 与 Workflow contract/schema 接受该可选布尔标记；Contract 测试证明 Note 坐标/标记
  改变 source hash，但不改变 behavior hash。Builder Blueprint schema parity 一并覆盖。
- 补有 3 节点、分支/合流、7/14 节点确定性与无重叠测试，并覆盖节点尺寸和固定坐标。

### 本地验证

- Conda 环境 `veyra-agent-platform`：
  `env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check` 通过，**695 passed**；
  dependency/lock checks、Ruff format/check、mypy 均通过。
- Web 全量测试：Desktop **56 files / 450 tests**，Community **3 files / 15 tests**；
  两应用 typecheck 与 production build 通过。Desktop build 报告大 chunk 提示，构建成功。
- Blueprint/schema parity 定向测试 **4 passed**；最终 `git diff --check` clean。

### 未完成验收与边界

自动化门禁不等于真实浏览器产品验收。目前没有 Slice 4 真实浏览器 E2E、真实
Provider/sidecar 验收、当前修订的 GitHub CI 或 release checkpoint。Slice 1–4
仍未提交/推送；Slice 5 Runtime Execution Overlay 明确未开始。工作树中的
`.backboard/sessions/`、`.backboard/settings.json`、`$DB` 与用户标出的独立 UI 文件
均按约束保留，不在本 Slice 清理或回滚。

## Agent Composition V1 — Slice 5 Runtime event audit（2026-09-22，实施前审计）

本审计以当前 dirty checkout 的 Runtime 与 Desktop 代码为准。当前 Slice 5 已获用户
明确授权；旧 checkpoint 中“不要开始 Slice 5”的状态已被本次请求取代。此处是审计
结论，不是运行态 overlay 已实现的声明。

### Runtime canonical facts

1. Agent Runtime 实际发出的节点事件为 `node.started`、`node.completed`、
   `node.failed`；HumanApproval 另发 `node.waiting`。Tool、Model delta、Verifier、
   Artifact、Approval 和 checkpoint 也各有持久化事件。`RunEventKind` 还声明了
   `node.queued`、`node.state_changed`、`node.output`、`node.skipped`、
   `node.cancelled`，但当前 Agent/Workflow 执行器没有实际发出这些节点事件；不能据此
   显示 queued/skipped/cancelled node 事实。
2. Condition 在服务端执行 `_condition` 后选择 `true` 或 `false` port；对应
   `node.completed.payload.port` 是真实 outcome。一般节点完成也写入实际选出的 port；
   HumanApproval 的完成 port 为 `approved` 或 `rejected`。
3. 没有 edge-level Runtime event，也没有 `edge_id`。但每个已完成节点的实际 port 与
   immutable run version graph 足以通过唯一 `(from node, port, to node)` transition
   确定 traversed edge；Condition 未选中的另一 port 对应边必须保持 idle。无需增加后端事件。
4. Approval wait 的事实组合是 Run `status=waiting`、`node.waiting`（reason=`approval`）、
   `approval.requested`、持久化 approval request 与 checkpoint。Approve/Reject 走
   canonical Run command API；对 Agent HumanApproval，decision 写入
   `approval.resolved` 与 `node.completed.payload.port`，同一个 `run_id` 从所选后继节点
   继续执行。
5. Stop 的事实是 `run.cancelled` 且 Run `status=cancelled`，不是 failed；当前执行器不发
   `node.cancelled`。因此只有已 start、尚无 completed/failed 的当前节点可在 cancelled
   Run 中呈现 stopped；从未执行的节点保持 idle，不推断 skipped。
6. `retry` 创建新 `run_id`，新 Run 的 `run.created` 带 `retry_of_run_id`；失败/中断后的
   checkpoint `resume` 也创建 child `run_id`，带 `resume_of_run_id`。只有 Approval
   decision 在原 `run_id` 上继续。新 Run 不能合并旧 Run 的事件。
7. Run detail 返回持久化事件；事件在存储中按 `(run_id, sequence)` 追加，读取按 sequence
   排序。SSE 支持 `after` / `Last-Event-ID` 回放。浏览器 `EventSource` 可以原生重连，
   但当前前端 `watchAgentRunEvents` 在 `onerror` 主动关闭连接，实际会禁用原生重连。

### 当前前端连接情况

- Studio Agent Canvas 的 `live-run.ts` 已从真实事件生成有限 `pending/running/waiting/
  completed/failed` 状态；`StudioWorkbench` 将它们映射到 React Flow 节点的 `data-state`
  和现有样式。这是基础节点显示，不是空白实现；尚无 edge 状态、stopped/skipped/queued
  语义或通用共享 projection。`run_id` 写入 Studio URL，但页面刷新后当前路由进入 Run
  Detail，而不是恢复 Canvas；SSE 当前也不会自动重连。
- Studio 的 `RunDetail` 确实消费 canonical Run events；其 Run Event list 是事件证据视图，
  不是节点/边 Canvas projection。Workflow Run Panel 目前以短间隔读取 workflow Run
  snapshot 并展示节点列表，不是 Agent live Canvas 的事件流实现。
- Builder Test operation 保存 canonical `run_id`，服务端 `observe_run` 仅生成摘要；
  Builder 测试启动/审批/拒绝/停止最终委托现有 Runtime。Desktop `BuilderTestRun` 只
  通过 `getAgentRun` 一次读取最终 result，没有 watch SSE，也不把 Run events 投影到
  Workbench Canvas。目前每个历史 Workspace 的 Test operation 是按 Agent 取最新项，
  没有绑定到该 workspace，存在同一 Agent 多个历史卡片串用 Run 的风险。
- Builder 的 Factory proposal Canvas 在 Apply 前是设计提案，不拥有 Runtime Run；没有
  canonical `run_id` / immutable Agent version 时不得展示执行态。运行态图必须从真实 Run
  的 `project_id + agent_id + version_id + run_id` 取回对应版本结构和该 Run 的 events。

实现边界：下一步增加一个共享、纯函数的 event projection；Agent Studio 与 Builder
Workspace 消费同一 projection。仅真实事件驱动节点/边；不改 Runtime scheduler、不添加
推测性事件、不展开 Custom Component 内部图、不改变 Slice 4 坐标或 Note。Inspector
只展示 Run/event contract 已存在且经过 allowlist 的安全事实。

## Agent Composition V1 — Slice 5 Runtime Execution Overlay implementation（2026-09-22）

### 已实现

- 新增共享纯函数 Runtime event projection：按 sequence 排序并去重；只接纳当前 Run
  的事件；节点状态覆盖 idle/queued/running/waiting approval/completed/failed/stopped/
  skipped；只有 `node.completed.payload.port` 对应的真实 transition 会显示 traversed，
  后继正在 running 时该边显示 active。取消 Run 不会把未开始节点伪装成 skipped。
- Studio Run URL 刷新后恢复只读执行画布，从 `run_id` 读取 canonical Run，再按其
  `version_id` 读取 immutable Agent source；缺少对应版本时显示安全错误，不回退到最新 Draft。
  Canvas 展示节点/边运行状态、Note、审批与停止操作、Runtime inspector 和 Run Detail 入口。
- Builder Workspace 使用同一执行画布和 projection。Test operation 新增可选
  `workspace_id` 元数据并在历史操作读回；每个 workspace 只选自身的最新 Test Run，
  同一 Agent 的其它历史卡片不会串用 Run。
- 前端 EventSource 网络错误时不再关闭处于 CONNECTING 状态的连接，保留浏览器原生
  Last-Event-ID 重连；快照合并按 sequence 去重。
- 没有新增 Runtime event、migration 或推测性事件，也没有改变 scheduler、Run command
  语义、Slice 4 的 graph coordinate / Note 布局。Inspector 只显示格式受限的错误 code、
  时间、duration，以及 Tool receipt / artifact evidence 是否存在，不回显 payload message。

### 本地验收证据

- `env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`：**695 passed**；Ruff format/check、
  mypy、dependency/lock checks 均通过；运行环境为 Conda `veyra-agent-platform`。
- `npm test`：Desktop **59 files / 463 tests**，Community **3 files / 15 tests**。
- `npm run typecheck`：Desktop、Community 均通过。
- `npm run build`：Desktop、Community 均通过；Desktop 有 >500 KB 主 chunk 提示。
- Slice 5 focused Desktop suite：**8 files / 133 tests passed**；`git diff --check` clean。

### 手工浏览器 / Runtime 验收（2026-09-22）

- 在现有已登录 Chrome 中检查 Studio：画布保留 Default Note，既有 Run 的只读画布使用
  该 Run 的 immutable version；刷新后恢复同一 Run，点击 Model 节点可见 Runtime inspector
  和 Run Detail 入口。此为真实 UI 手工检查，不是自动化 E2E。
- 使用一条合成输入 `这是 Veyra 的本地运行测试。` 创建了一次真实 Runtime Test Run
  (`01a0ca02-b540-70c3-aa20-034d7da9479a`)。执行时观察到 Model 从 running 到 completed，
  Start / Model / Output 最终均 completed；配置 Provider 输出
  `This is a local runtime test for Veyra.`。Run 最终状态为 `unverified`，表示没有 verifier
  证据，不把它描述为已验证结果。刷新后同一 Run 和节点状态仍可恢复。该合成 Run 留在
  本地 `test` Project 中，未删除。
- 当前项目没有可安全复用的 Approval、Condition branch、Custom Component 或 Component
  Proposal 验收样例；本轮没有修改既有 Agent 来制造样例，也没有创建/发布 Component。
- 本轮没有重发 Builder Provider prompt：这会把新提示发送给配置的模型服务并持久化 Project
  Chat 对话，需要用户对这一次具体发送动作明确确认。Development 文档记录的先前 Builder
  请求曾以 `factory_rate_limited` / HTTP 429 失败；本轮没有重试。没有发送账号信息、Run 日志
  或私有项目资料。

### 剩余证明缺口

因此，本地 Runtime 配置 Provider 请求已经有一笔成功执行的手工 smoke，但 Builder
Provider、正式浏览器 E2E、Approval/Condition/Component UI 闭环、GitHub CI、commit/push
及 release checkpoint 仍缺。以上只证明当前 dirty checkout 的本地门禁和有限手工路径；
Slice 1–5 均未发布。

## Agent Composition V1 — 本轮 Builder 与 Custom Components 追记（2026-09-22）

- 用户确认后，本轮只发送了一次指定的合成 Builder 请求；Provider 成功返回，未遇到
  429，因此没有 retry。检查真实 Proposal 后未 Confirm / Apply：图里有一个 Condition 和
  两个 HumanApproval，但 Condition 实际只分空/非空，审批与 Transform 顺序串联而非
  urgent/routine 两条分支，Transform 输出 request，output contract 只有 `result`，不符合
  `{priority, summary}`。Note 声称的 branch/output 与图不一致。此 Proposal 不通过验收。
  无 fake capability、Custom Component 提案、Tool 或额外权限，也未改动 Agent。
- Provider receipt 的自动上下文包括 Project/Agent、Workflow、Knowledge 的 metadata、
  resource bindings、Catalog capabilities、Project file metadata 与 Project config；
  Interview/Semantic Plan 还携带当前对话消息。Receipt 标记未包含 Knowledge/file 正文、
  credentials/secrets、Runtime events、隐藏推理或 Provider response body。以后不得将这笔
  请求描述成完全不附带 Project metadata。
- 用户截图的 `Not Found` 根因已复核：本机 8771 health `build_sha=5f8e8a8`、数据库
  revision `local_0025_project_artifacts`，组件列表 GET 为 404；当前工作区的
  `projects/routes.py` 已有该路由。用临时 SQLite 的 TestClient lifecycle 集成测试通过。
- 修复 Custom Components 面板的故障态：列表 API loading/error 时禁止修改表单、保存、
  校验、发布及其它生命周期操作；404 给出服务接口不可用说明；Retry 成功后恢复操作。
  Focused Desktop tests 3/3、隔离 backend lifecycle integration 1/1、Desktop typecheck
  均通过。以上不是 browser E2E。
- 本轮未重启 8771；按用户发布顺序，服务重启在可接受提交之后。因 Builder semantic
  proposal 不符合契约，当前不能提交/push，也未重启四个服务。当前 screenshot 真实服务
  仍会返回 404，需在后续获准的发布/重启步骤更新 sidecar 后验证 API 和浏览器界面。

## Agent Composition V1 — 8771 current-dirty restart + Custom Components smoke（2026-09-22）

- 用户随后明确授权只重启 `8771`，并禁止 commit/push/stage/reset/checkout/clean/stash/restore/rebase
  及真实 Project 数据修改。本轮只停掉原监听 PID，再从项目根目录以 Conda Python 启动：
  在仓库根目录的 Conda 环境执行 `env PYTHONPATH=backend/src VEYRA_BUILD_SHA=5f8e8a8-dirty python -m uvicorn veyra_agent_platform.local.app:app --host 127.0.0.1 --port 8771`。
- 沿用 repo-root host config 和真实 Local database/Project root；没有使用 temp DB、E2E root、
  fake/loopback provider。没有查看、打印或改写 `.env` 内容；正常应用启动 loader 读取配置。
  health=`200`，`build_sha=5f8e8a8-dirty`，`database_revision=local_0026_builder_semantic_plan`，
  `database_ready=true`。真实 DB 从 `local_0025_project_artifacts` 升级；migration 只给
  `factory_sessions` 添加 nullable `semantic_plan_json` 列并按启动逻辑保留 pre-migration copy，
  未改变 Project files/resources/records。
- 对既有 test Project 的只读 Custom Components GET=`200`，Project id 匹配，组件数为 0；
  没有写入真实 Component/Project 资源。
- Chrome 手工刷新后：404 和 `组件列表不可用` 消失；空列表正确显示 `还没有自定义组件`；
  New Component、表单、typed I/O JSON 可用。未保存状态下把 implementation kind 切为
  `transform`，确认实现模板联动；之后刷新清空表单，API 再读仍为 0。Draft/Save/Publish
  未执行；空白表单中的 Publish 控件现已 disabled，且没有保存/发布真实 Project 数据。
  没有找到可确认隔离的既有 Project，所以未做隔离 lifecycle browser smoke。
- API error 状态已在重启前观察：404 时表单锁定、列表标为 unavailable；API 正常后错误消失、
  真空列表显示空态。相关自动化 panel tests 3/3、隔离后端 lifecycle test 1/1、Desktop
  typecheck 通过；这些不是 lifecycle Browser E2E。
- `5173`、`5174`、`8772` 未重启，当前分别 HTTP 200、HTTP 200、Community ready（SHA
  `5f8e8a8`）。`8771` 当前由 Conda uvicorn 进程监听。
- 当前 Builder real-provider Proposal 仍 semantic failed；未 Confirm/Apply、未再次调用
  Provider。Agent Composition V1 不 complete。没有 Git stage/commit/push 或其它 Git 状态操作；
  仓库既有 Slice 与独立 UI 改动保留，仅按用户要求更新两份开发记录。

## Agent Composition V1 — Branch Semantics & Output Wiring hardening（2026-09-23）

- 本轮没有调用真实 Builder Provider、没有 Confirm/Apply、没有重启服务、没有 stage/commit/
  push，也没有修改真实 Project。现有失败 Proposal 仍只作为 bug evidence。
- 根因是旧 SemanticPlan 只有线性 `depends_on`，Compiler 将 sibling branch steps 按拓扑
  顺序串联；顶层 outputs 虽存在，Transform fallback 只映射第一个 output。现已增加通用
  `SemanticBranch(key,label)`、`branch_condition`/`branch_key` 和 Transform `output_mapping`。
  Condition 必须有两个 semantic branches；当前 Runtime 双端口 contract 将声明顺序映射到
  `true`/`false`，labels 保留在 `ui.branch_labels` 和 Note/Canvas edge label；不支持的三分支
  或 malformed topology fail closed，不按样例关键词猜测。
- Branched compiler 现在按真实 dependency DAG 编译：每条 branch 的 Approval 只指向自身
  branch downstream，Transform 可组装全部 declared typed outputs，terminal branches 可
  真实汇入同一个 Output；共享 successor 只有在 declared dependencies 存在时才合并。新增
  compiler invariants 防止 sibling dependency、multiple roots/successors 和 ambiguous
  Condition targets；semantic compile errors 不进入 ready/review success。
- Provider prompt、repair、strict schema、MFJS projection 已同步；原先“不要 emit branches”
  的指令已移除。非 Condition 的 malformed branch metadata 只做有诊断的 bounded repair；
  Condition branch 数量、identity、branch-local dependency 错误拒绝。未增加 migration，
  contract extension 保持 schema version `1.0`。
- 空白 Custom Component Publish gate 已修复：无 persisted draft identity 或未成功 Validate
  时 disabled；Save/Update 清掉 validation gate，Validate 成功后才 enabled；focused panel
  tests 覆盖该状态。
- Focused results：Backend semantic/compiler/factory/runtime/contracts **169 passed**；
  Desktop overlay/resource focused **36 passed**；Desktop typecheck、Ruff format/check、
  touched production mypy（8 files）通过。首次包含旧测试文件的 mypy 运行暴露既有 test
  typing debt，未修改或混报为本轮生产错误。Runtime fixture 已实测 True/False 两 branch
  只执行各自 Approval/Transform 并保留双字段 Output；Browser/Provider acceptance 仍未做。

## Agent Composition V1 — live 8771 branch browser acceptance（2026-09-23）

- 只重启 `8771` 到当前 working tree：`build_sha=5f8e8a8-dirty`、health 200、
  `database_ready=true`、`local_0026_builder_semantic_plan`。5173/5174/8772 未重启；没有
  读取/打印 `.env` secret，也没有真实 Builder Provider 调用。
- 创建隔离真实 Local Project `Browser Branch Fixture - 2026-09-23`，ID
  `01a0ca52-c8d1-7582-a773-7b4f3d6bf2c8`，fixture Agent ID
  `01a0ca52-c8d1-763d-876f-9fd2c7e8514f`。仅使用 `mode=alpha|beta`，未改动 `test` Project
  或其已有 Agent；fixture 和 Run 保留，未删除。
- Alpha manual browser acceptance：Run
  `01a0ca53-a2bf-7b24-957a-86dcd8c8a0f8` 在 `approval_alpha` waiting，Beta approval
  未开始；Approve 后同一 Run 完成 `transform_alpha`/Output，Beta transform 未开始，Run
  result 为 `{branch: alpha, summary: Alpha summary for alpha}`。
- Beta manual browser acceptance：Run
  `01a0ca54-c517-787b-bd8d-d4034403f38c` 在 `approval_beta` waiting，Alpha approval
  未开始；Approve 后同一 Run 完成 `transform_beta`/Output，Alpha transform 未开始，Run
  result 为 `{branch: beta, summary: Beta summary for beta}`。
- Canvas overlay 截图与 event list 一致：实际 waiting node、completed nodes、选中 edge 和
  未选 edge 正确；未出现双 branch 同时高亮。两个 completed Run 刷新 `run_id` URL 后均恢复
  immutable Run 的 graph/status。
- Canvas 显示真实 edge labels `Alpha`、`Beta`；Note 描述与实际 graph 一致。Resource Library
  空白 Component 表单手工确认 Save Draft enabled、Validate disabled、Publish disabled；没有
  写入 Component。以上是 manual browser evidence，不把 unit/integration 当 browser E2E。
- 本轮结束点：未开始 Community/Workflow/新功能；无 bug hotfix；没有 commit/push/stage，
  当前 Builder real-provider semantic blocker 仍保留，真实 Provider acceptance 仍需以后单独授权。

## Community Sharing UI refresh（2026-09-23，本地工作树）

- 新用户构想“Discover / Published / Starred / Following”已落到 Desktop 与独立 Community Web 的横向二级导航；Veyra 全局侧栏没有新增第二套 Community 左栏。Discover 使用真实注册表 API，可搜索并按发布时间、真实 Star 数或 Review 评分排序；无虚构 Featured、下载量、导入量或 graph workflow 摘要。
- Published 使用新增的认证 `GET /api/v1/registry/mine/agents`；Starred 使用新增的认证 `GET /api/v1/registry/starred`，两者复用现有 Agent version 和 `community_agent_stars`。Published 列出实际状态，没有虚构的持久 Community Draft。
- Following 页面明确说明当前无 creator-follow / activity-feed API，导航带“Later”标记；没有添加账号关系表、迁移、feed 或示例动态。Discover 只展示现有 Agent Registry；现有 Plugin Pack 发布仍在 Publish 区，但其浏览/导入详情、Workflow/Component/独立 Tool/Skill 市场都未伪装成已实现。
- 本轮先前的发布/导入闭环也保留：Agent source 本机预览、显式确认、Community API 的 Secret ref/机器路径二次硬拒绝；下载后本地 Project 依赖预览，Confirm 前零 Project mutation，Confirm 时检查来源与依赖快照未漂移，只创建新 Draft。
- 验证：Community Registry + Agent Import + Local export 集成定向 **7 passed**；Desktop Community focused **7 passed**；独立 Community app **7 passed**；Ruff 相关路径通过；全仓 `make check` **703 passed**；Web 全量 Desktop **471 passed**、Community **18 passed**，typecheck/build 通过。手工浏览器只验证了真实 5174 Discover（0 个发布版本）和 Following 未开放状态，未执行真实账户的 Star/Publish/Import。
- 当前 5173/5174 为工作树前端；8771/8772 health 仍 HTTP 200，但仍服务 `0ad7a3e`，DB revision 分别为 `local_0026_builder_semantic_plan` 与 `community_0008_plugin_registry`。未重启任一服务；新 `mine/agents`、`starred` 路由和 `target_project_id` 导入预览尚未 live，后续需用户授权后重启对应 API 再做实时验收。
- 本轮没有 stage/commit/push。保留既有 shell/navigation-fold UI 修改、`$DB`、`.backboard/settings.json` 与 `.backboard/sessions/`。尚未完成：Following 后端关系/Feed、插件包的统一 Discover 浏览/导入、Community API live restart/browser acceptance、独立 PR/发布。

## Community Sharing V1 — live API reload + read-only browser acceptance（2026-09-23）

- 本轮只重启 `8771` Local API 与 `8772` Community API；没有重启 `5173` / `5174`，没有调用真实 Provider。
  旧 listener 已确认分别为 Conda Uvicorn Local/Community app 后才按 PID 停止；新 listener 为 27611 / 27612。
  使用 Conda `veyra-agent-platform` Python 3.11.15、仓库根目录、`PYTHONPATH=backend/src`、原有应用配置，
  `VEYRA_BUILD_SHA=0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`。没有设置 temp DB、E2E root、fake/loopback
  provider；没有读取、输出或覆盖 `.env` secret。Community 使用仓库已有 dotenv 启动入口。
- 两个 health 均 HTTP 200、`database_ready=true`、`schema_version=health.v1`，Local DB revision
  `local_0026_builder_semantic_plan`，Community DB revision `community_0008_plugin_registry`；两服务
  报告同一完整 dirty build marker。OpenAPI 3.1.0 确认 Local Agent import analyze/read/apply 路由和
  Project Agent import 已加载；Community publish/list/detail/version/download/star/unstar/moderation 与新增
  `GET /api/v1/registry/mine/agents`、`GET /api/v1/registry/starred` 已加载。
- Live 只读 API：匿名 `GET /api/v1/registry/agents` → HTTP 200、0 releases；mine/starred → HTTP 401
  `authentication_required`。没有 Project、账号、Agent、Run、release、Star 或 Component mutation；没有测试 fixture。
- Manual browser acceptance（隔离 Codex IAB，非自动 E2E）：独立 Community Web Discover 显示真实 0 releases，
  search field 可输入，Recently published / Most starred / Top rated 可切换；Published 与 Starred 显示登录边界；
  Following 明确提示未开放、无 Follow API，并区分 Star release 与 Follow creator。Light/dark 页面无明显破版。
  Desktop Community deep link 因无登录会话重定向至 Login。5173/5174 最后检查均 HTTP 200。未把该检查称为
  Playwright、jsdom 或 API test。
- 未完成的真实认证闭环：Publish、authenticated Published listing、Star/Unstar reload、Agent detail、Import Preview
  前后 Project 状态对照、Import as Draft、Studio open。注册会触发 verification-code dispatch；没有指定隔离测试
  账号/邮箱，本轮没有请求验证码、创建账号、发送邮件或借用用户账号。公开目录保持真实 0 releases，没有 fake content。
  这是一项明确的 release blocker；不能把 Community Sharing V1 标记 complete。
- 本轮 full gates：`conda run -n veyra-agent-platform env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`
  通过（703 passed、Ruff format/check、dependency lock、mypy 187 source files）；Web `npm test` Desktop
  471 / Community 18 passed；typecheck/build 都通过。Desktop build 的既有 >500 KB chunk warning 与 Alembic
  `path_separator` deprecation warnings 保留。`git diff --check` clean。
- HEAD 仍 `0ad7a3e0b2a11ccf9186f23dab40628375509c73`、branch `codex/agent-platform`；没有 staged files，未 commit/push。
  保留 Community implementation、用户独立 shell/sidebar-scroll/UI 修改、`$DB` 与 `.backboard` 状态。
- 恢复完整真实验收前，需要用户提供/确认一个隔离 Community 测试账号，或指定测试邮箱并授权注册流程的验证码投递；
  在此之前保持当前服务运行、不要创建临时假账号或发布数据。拿到授权后，从隔离 Project A 的 deterministic Agent
  version 开始完成 Publish → Discover/Star → Project B Import Preview 零变更 → Confirm as Draft → Studio。

## Builder Provider re-acceptance + Custom Component lifecycle — 2026-09-24

- 当前验收只使用两个隔离 Local Projects：Builder 项目 `01a0cee5-90fb-78f4-99ab-e42e9a6365c9`；
  Component 项目 `01a0cef1-4384-702e-a63c-40d7ba6e469a`。不要改用户的 `test` 或其他 Project。
- Builder 只发出一次获准的合成请求；一个正常 Builder turn 内包含意图解析、Semantic Plan 和两次有界
  repair，最终 `factory_generation_invalid` / `semantic_generation`，没有 proposal_id。不是 429；没有
  reviewable graph。不要点 UI Retry 或再调用真实 Provider，除非用户另行授权。没有 Confirm/Apply/Run，
  Builder acceptance failed，不得记为完成。
- Custom Component `Acceptance Echo`：Project 组件 ID `01a0cef2-ec07-7379-b55c-8eb581150d0e`，
  published ref `@1.0.0`，hash `e7de5249088a601226431f3e8946ad22a6b226b4226717e8f0996200fd67a2bc`；
  另有修改描述后的 unpublished Draft。隔离 Agent `Acceptance Harness` ID
  `01a0cef6-a4fc-7d7b-aa0c-d8f0dbf3e346`，revision 2，含 `CustomComponent` node、精确 `uses`/lock 与
  `text <- request` / `result -> result` 映射。Studio validate 显示 component dependency ready；未 commit
  Agent 版本、未 Run、未调用模型或外部工具。
- 发现并修复 Local Library 将 `CustomComponent.uses` 误判为 Tool 的 bug；Project-owned component
  published reference/hash 现在独立校验，dependency inspector 使用真实 Project Custom Component descriptor。
  8771 已按当前 dirty working tree 重启，health 200、`local_0026_builder_semantic_plan`、
  `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`。5173/5174/8772 未重启，仍健康。
- Focused 后端测试 37 passed；全仓 Conda `make check` **704 passed**，Ruff format/check、dependency
  lock、mypy 187 source files 通过。Web Desktop **472 passed**、Community **22 passed**，两端
  typecheck/build 通过。保留既有 Alembic `path_separator`、jsdom Canvas `getContext` 和 Desktop
  large-chunk warnings。Git 不 stage/commit/push；保留原有 Community/Showcase、Sidebar、
  `.backboard`、`$DB` 与其他独立用户改动。两验收 Project 和数据保留、不清理。

## Builder Semantic Generation Failure RCA + Offline Hardening（2026-09-24）

- 延续当前 HEAD `0ad7a3e0b2a11ccf9186f23dab40628375509c73` / `codex/agent-platform`。
  不要覆盖既有 Community/Showcase/Registry、Sidebar/scroll、Custom Component、Branch Semantics、
  `.backboard/sessions/`、`.backboard/settings.json` 或 `$DB`。无 staged files；没有 commit/push。
- 失败 session identity：Project `01a0cee5-90fb-78f4-99ab-e42e9a6365c9`；conversation
  `01a0ceeb-5dfb-7f5a-9944-2320254d181c`；operation
  `01a0ceeb-5dfb-71b8-a4f7-06a1542144f6`；Factory session
  `01a0ceeb-cabd-7e1e-bc58-df67cdeb51fc`。只读，不要删除或继续修改 acceptance Project。
- 三个 Semantic Plan Provider attempts 都是成功的 strict JSON Schema / MFJS 调用。三次都通过 JSON
  parse、当时的 Python SemanticPlan contract 和 branch/obligation validation，在 semantic compiler
  失败：依次为 `normalize_result` 的 `advice_priority` 未知输入、`normalize_result` 的
  `urgent_priority` 未知输入、`normalize_urgent` 的 `advice_priority` 未知输入。最终
  `factory_generation_invalid` / `semantic_generation`，无 Proposal/Blueprint、Draft、Run 或 Component。
  只有第三次 SemanticPlan JSON 被安全保存；首次和 repair 1 的 raw structure、exact repair prompt 和
  numeric HTTP status 不可用，不能从 diagnostics 中反推完整原文。
- Root cause: ordinary step-level `inputs/outputs` 被误认为 Model→Transform 数据流。Compiler 只允许
  Transform 映射 Agent top-level inputs/literals 到 Agent top-level outputs；`depends_on` 只表达控制/顺序。
  Old repair 有 diagnostic 但没有 field allowlist 或 machine code/path/expected，Transform preservation
  obligation 又把这个 invalid mapping-only step 锁死。MFJS nested branch/output projection 无损，非根因。
- 当前修复：非 reusable step-level I/O 以 `unsupported_step_io` + exact path/expected 拒绝；有效的
  reusable `model` / `transform` / `capability` component contract typed I/O 保留；普通 Model 必须产出
  Agent declared fields，Transform 只映射顶层输入/literal。Compiler source 错误输出 machine code/path/
  expected/allowed input；Repair 明确分辨 genuine deterministic Transform 与非法的 Model-output rename。
  非法 mapping-only Transform 不再被当成 user obligation，但 approvals/branches/multiple-model 等真实职责
  仍 fail closed。MFJS schema path 与 nested item 保持。
- Regression fixture：`contracts/fixtures/invalid/agent-semantic-plan-real-provider-failure.json`，只含
  保存下来的 final plan sanitized shape；不可声称它包含丢失的前两次 raw response。Scripted integration
  使用真实 fixture → derived compiler-invalid repair → neutral valid plan，进入 waiting/review graph，未
  Apply；验证两个 sibling Approval 不串联、两字段输出、branch labels/Note 与 compiled graph 相符。另有
  three-invalid-repair exhaustion 保持 `factory_generation_invalid` 且无 Project mutation。
- 验证：Builder/Factory/SemanticPlan/MFJS/Compiler/Proposal/Custom Component focused **156 passed**；
  全仓 Conda `env -u PYTHONPATH -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check` **713 passed**、
  Ruff format/check、dependency lock、mypy 187 files 全通过；Web Desktop **472 passed**、Community
  **22 passed**，typecheck/build 全通过。既有 Alembic `path_separator`、jsdom Canvas 与 Desktop chunk
  warnings 保留。无 migration、真实 Provider 调用、service restart、Project 数据 mutation。
- 下一步只可单独授权 **Builder Real Provider Re-Acceptance #2**。在那之前 Builder 仍未 real-provider
  accepted，不可标记 Composition V1 complete，不要 Retry，不要 stage/commit/push/release audit。

## Builder Real Provider Re-Acceptance #2（2026-09-24，本次 FAIL）

- 当前 branch/HEAD 仍是 `codex/agent-platform` / `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；工作树原先 dirty、无 staged files。旧 Project `01a0cee5-90fb-78f4-99ab-e42e9a6365c9` 和旧失败 Conversation/Operation/Factory session 都保持原样。
- 只发送一次获准 Builder turn；新 Conversation `01a0d1a6-3580-71d9-84d4-550407c34ef7`、Operation `01a0d1a6-3580-721b-b709-57c59c0a17e3`、Factory session `01a0d1a6-72d7-713a-b749-ca0df9c9eaf7`。Provider `moonshot/kimi-k3`；receipts 为 resolve_intent/json_object、interview/none、semantic_plan/strict_json_schema+mfjs，全部 success；Semantic Plan 1 attempt / 0 repair。没有 Retry 或后续真实调用。
- Blueprint 结构有 Condition + urgent/routine branch-local Approval + 各自 Model、typed outputs `priority`/`summary`；sibling branches 未串联。**Acceptance FAIL**：Compiler 将自然语言 Condition purpose 静默回退成 `request != ""`，实际判断空/非空，并不区分两个业务类别；Note 却声称按请求内容分类。同时 operation `proposal_id=null`，只有 Factory session review Blueprint，没有附件要求的持久化 canonical Proposal ID。不要把 `builder.proposal.ready` 事件误称为带 ID 的 canonical Proposal。
- User asked about screenshot login error: 原因是当时 8772 Community API 未启动；后来只因用户明确说“全部都启动”，启动了 8772，并也启动了原先不可用的 5173、5174。恢复后登录错误提示消失，但 browser 登录表单仍为空、客户端提示邮箱/密码必填；没有读取/输入/传输账号凭据。因此浏览器 Proposal UI/Canvas acceptance 未完成，API/Factory session proof 不冒称浏览器验收。
- API counts before/after：Agent 0、Workflow 0、Custom Component 0、Project-owned resource binding 0、Runtime Run 0、Workflow Run 0。没有 Apply/Confirm、Agent Draft、Component、Run、外部 Tool/HTTP 或 migration。旧失败 Conversation 仍 `factory_generation_invalid`。
- 有根因的最小 compiler 修复已落地：Natural-language Condition purpose 不再推断为 `field != ""` / 默认结果；仅接受 Runtime 支持且引用已声明 Agent input 的显式比较表达式，否则 fail closed 并提供 machine-readable `code/path/expected/allowed_inputs`。Prompt/schema 描述同步。新脱敏回归 fixture `contracts/fixtures/invalid/agent-semantic-plan-condition-fallback-reacceptance-2.json`；新增单测确认真实 plan 形状不再默默生成错误分支。没有实现 proposal-ID persistence 或自然语言 classifier feature。
- 代码修复后未再调用 Provider；focused SemanticPlan/Compiler/Factory/Builder/Proposal/Custom Component suite **158 passed**；Conda `make check` **714 passed**、Ruff/dependency lock/mypy 187 通过；Web Desktop **472**、Community **22**，typecheck/build 通过。Warnings: Alembic `path_separator`, jsdom Canvas, Desktop chunk size。
- 所有四服务当前均健康：5173/5174 HTTP 200；8771/8772 health 200、ready，revision `local_0026_builder_semantic_plan` / `community_0008_plugin_registry`，build `0ad7a3e0b2a11ccf9186f23dab40628375509c73-dirty`。代码修正后只重启 8771 载入当前树；Community/Showcase未改。
- `docs/DEVELOPMENT.md` 已记录完整证据与失败门禁。本轮未 stage/commit/push；不做 Release Audit。Builder Re-Acceptance #2 = **FAIL**；Agent Composition V1 不能 accepted / release ready。下一轮需先解决 Proposal persistence 身份与 Condition 自然语言分类可表达性，再单独授权 Re-Acceptance #3。

## Condition Semantic Contract + Canonical Proposal Identity Hardening（2026-09-24，本地 dirty slice）

- 继续使用 `codex/agent-platform` / HEAD `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；保留 Community/Showcase、Sidebar/scroll、Custom Component、Branch Semantics、`.backboard` 与 `$DB` 等既有 dirty 范围。
- 版本审计结论：`8bef91c → 0ad7a3e` 是大范围能力扩展，不是代码整体退化；当前真实问题集中在 Condition executable boundary、Factory Proposal persistence 与未完成的 release evidence。
- Condition Runtime grammar 是 `==` / `!=` + string/boolean/integer literal。新增 `condition_expression` 与 `purpose` 分离；普通自然语言分类无可执行表达式时 fail closed；不引入隐式 Model classifier、`eval` 或 generic intermediate state。
- `edit_proposals` 复用为 canonical Builder creation Proposal store，新增 `proposal_kind=create_agent`、candidate snapshot/provenance，并通过 `local_0027_builder_creation_proposals` 以 `project_id + builder_creation_operation_id` 做唯一关联。Proposal、operation.proposal_id 和 ready event 在同一 SQLite transaction 中 materialize；重复调用复用原 proposal。
- `POST .../builder/conversations/{id}/records` 对 proposal_id 做 server-side ownership 校验，拒绝随机或跨 operation proposal reference。
- 本 Slice 没有真实 Provider、Confirm/Apply、Run、服务重启、stage、commit 或 push。没有修改既有 acceptance Project。
- 验证：focused **129 passed**；full `make check` **720 passed**；Ruff/format/dependency lock/mypy 188 source files；Web Desktop 472 / Community 22，typecheck/build；`git diff --check` clean。保留 Alembic `path_separator`、jsdom Canvas stderr 和 Desktop large-chunk warnings。
- 下一步：仅在用户单独授权后做 Builder Real Provider Re-Acceptance #3；要求 proposal-only、稳定 proposal reload、truthful Condition、零 Agent/Run mutation。Confirm/Apply/Release Audit 仍未执行。

## Server Execution Plane V1（2026-09-25，最新）

- Branch/HEAD 仍为 `codex/agent-platform` / `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；
  dirty worktree 全部保留，不 commit、不 push、不 reset/clean/stash/rebase。
- Cloud DB 已 forward-only 到 `community_0015_cloud_runs`，Local DB 为
  `local_0031_project_artifact_sync_state`。新增 migration 不修改旧 revision。
- Platform Provider、User Runtime Credential、Device Credential 已分域。Cloud API key
  只以 AES-GCM ciphertext 存储；master key 不进 SQLite；API/Artifact/Proposal/Conversation/
  Run event/result/evidence 不含 plaintext secret。解析顺序 Agent > Project > account default，
  无 Platform key fallback。
- Cloud Run 已覆盖 immutable Agent Version integrity、Cloud File ownership、Model/
  Transform/Condition/Verifier/Output/HumanApproval、Tool `local_host_required`、durable
  events/SSE、approval、stop、retry lineage、resume checkpoint、restart recovery。Cloud
  Host 不导入 Local app/SQLite。
- Builder `create_agent` waiting operation 仍是 durable Local Conversation state；Cloud
  credential selection 先写入 Cloud Project `primary_model` binding，再用显式
  `credential_scope=cloud` 恢复 operation。普通 Chat 不要求 Runtime Credential。
- Focused **8 passed**；Cloud **27 passed**；backend full **767 passed / 399 warnings**、
  mypy **234 source files**、Ruff/dependency lock PASS；Desktop **487 passed / 66 files**、
  Community **23 passed / 4 files**；typecheck/build PASS。真实 mock Cloud acceptance 与
  restart persistence 通过。Real Provider / Real Runtime Model / Real Agent Model Run：
  **NOT RUN**；没有新的 Cloud 页面或 UI redesign。
- 下一步只有用户单独授权后再做 **Builder Real Provider Re-Acceptance #3**；不要自动进入
  Workflow Builder、RAG、Community 扩展或真实 Provider 请求。
- Web closure：5174 当前默认是 authenticated Cloud Workspace，`#/showcase` 保留公开展示；
  Web 页面只走 Cloud API，不暴露 Local Host 能力。Desktop 仍是 Local Host + Cloud 的完整
  工作台。
- Deployment/packaging：production compose now selects Cloud Host, requires PostgreSQL/S3/
  credential master key/auth/origin/CORS settings, and Cloud readiness checks DB/blob/cipher.
  Fresh/copy SQLite migrations and PostgreSQL SQL audit pass; live PostgreSQL NOT RUN because
  Docker is unavailable. Package static smoke PASS; macOS Cargo build and signing/notarization
  NOT RUN because tools/Apple credentials are unavailable.
- Share/cross-client evidence: isolated two-account API harness proved Publish → Discover →
  Star → Download → Local Import Preview (no mutation before Confirm) → Draft → Local Run;
  authenticated Web/Desktop simulation proved shared project/conversation/run IDs. Real
  Browser E2E remains NOT RUN because Chrome debugger is unavailable.

## Cloud Files & Library Foundation #1（2026-09-25，已完成）

- 当前仍为 `codex/agent-platform` / HEAD
  `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；保护全部既有 dirty worktree，
  不 commit、不 push、不 reset/clean/stash/rebase。
- Cloud migration 已 forward-only 从 `community_0011_project_artifacts` 升级到
  `community_0012_cloud_files`，真实 8772 已重启到该 head；Local 保持
  `local_0031_project_artifact_sync_state`。新增 `cloud_files` 和
  `cloud_project_file_references`，没有把 Cloud bytes 放入 SQLite。
- 新增 `cloud/files/BlobStore` 与 `FilesystemBlobStore`。Cloud File upload 通过
  temporary object 流式计算 SHA-256/size，超过配置 limit 或中断时不产生 active
  metadata；finalize 使用 server-generated key。API 只返回 file_id、文件 metadata、
  hash 和 lifecycle，不返回 owner/storage path/storage key。
- Cloud routes：`/api/v1/cloud/files` 的 list/upload/get/content/delete，以及
  `/api/v1/cloud/projects/{project_id}/files` 的 list/attach/detach。Project reference
  是 relation，不复制 blob；跨账号 list/get/download/attach/delete 非披露 404；
  referenced file delete 为 409 `file_in_use`。
- Local routes/client 提供显式安全 materialize foundation（仅 `assets/` / `knowledge/`，
  hash/size 校验，拒绝 traversal/symlink）以及 Knowledge `cloud_file` source-ref。
  Project Artifact envelope 只携带 file identity metadata，不携带 bytes；不自动上传
  Local Project，不自动 index Knowledge。
- 真实 acceptance：Chrome 真实打开并确认既有账号、Sidebar、Artifact Project 页面正常；
  Cloud upload/attach/download 使用 isolated authenticated acceptance harness。验收记录：
  首次 upload/list/get/download/attach 通过；重启 8772 后 metadata/blob/download 通过；
  detach/delete/archive 清理通过，最终 blob count=0。没有真实 Provider、Runtime 或
  Agent Run。Harness 不是纯 UI upload E2E，页面与 API 证据边界已明确记录。
- 最终 gate：backend **754 passed / 399 warnings**，mypy **216 source files**；Desktop
  **484 passed / 64 files**，Community **22 passed / 3 files**；typecheck/build PASS，
  `git diff --check` PASS。不要复用上一 Slice 的 746/482 作为本轮数字。
- Verdict：**CLOUD FILES & LIBRARY FOUNDATION #1 COMPLETE**。下一阶段候选是
  **Cloud Chat & Conversation Persistence #1**，但不自动进入。

## Existing Chat Server Authority & Cross-Client Persistence #1（2026-09-25，已完成）

- 当前仍为 `codex/agent-platform` / HEAD
  `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；保留全部既有 dirty worktree，
  不 commit、不 push、不 reset/clean/stash/rebase。
- 当前原始 Chat authority 已审计为 Local Builder：`ProjectBuilderConversation` →
  LocalApiClient → Local `BuilderConversationService` / `BuilderConversationStore`，
  数据位于 Local `builder_conversations`、`builder_messages`、`builder_operations`。
  Agent Runtime conversations 和 Factory sessions 仍是不同的 Local domain，本轮没有
  把它们错误合并成 Chat。
- 新增 Cloud migration `community_0013_conversations`，Cloud 8772 已重启到该 head。
  Server Conversation/Message API 是账号级 authority，包含 Project/Agent relation、
  revision、stable message sequence、idempotent message_id、operation/proposal/event refs、
  attachment Cloud File refs、owner isolation 和 archive/restore。
- 新增 shared Cloud contracts 与 connected-account client。Desktop 新增
  `ConversationMigrationCoordinator`：账号 session 可用时从现有 Local Builder snapshots
  做 stable-ID import；不删除 Local rows。Recent 读取 Server list，旧 Local API 只作为
  server unavailable 的 cache/执行 bridge；没有新增 Cloud Chat 页面，没有长期双主 Chat
  sync，也没有把 Server 代码依赖到 8771、Local SQLite 或本机路径。
- Message attachment 只保存当前 owner 的 `cloud_file_id` 及服务端 metadata snapshot；
  不保存 bytes、API key、credential、Keychain、session token、absolute/local path。
- 真实 API acceptance：A/B 两个账号会话模拟 Desktop/Web；同一 conversation_id 读取
  M1、追加 M2，另一端重新读取 M1/M2；同一 Cloud File attachment ref 可见并可下载；
  8772 restart 后 Conversation、Messages、Project relation、attachment ref 保持，最后
  清理 acceptance 数据。没有 Real Platform Provider、Runtime Provider 或 Agent Run。
- 最终 gate：backend **758 passed / 399 warnings**，mypy **221 source files**；Desktop
  **486 passed / 65 files**，Community **22 passed / 3 files**；typecheck/build PASS，
  `git diff --check` PASS。Focused Cloud Conversation **4 passed**、migration coordinator
  **2 passed**。UI 没有大改；本轮尝试打开现有 Chat 页面时 Chrome debugger connection
  不可用，因此不把页面检查伪称为通过；数据 cross-client 证据使用 authenticated API
  harness。
- Verdict：**EXISTING CHAT SERVER AUTHORITY #1 COMPLETE**。下一阶段只可在单独授权后评估
  **Server Credential Vault & Cloud Runtime Foundation**，不自动进入。

## Canonical create_agent Proposal Confirm / Apply identity closure（2026-09-24，本地 dirty slice）

- 当前仍在 `codex/agent-platform` / HEAD `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；既有 dirty 范围全部保留。本 Slice 没有 Provider、真实 Run、服务重启、stage、commit 或 push。
- canonical Builder create-agent 的 Apply authority 现在是持久化 `edit_proposals` Proposal snapshot，不是可变 Factory session Blueprint。Proposal 保存 source/behavior/lock hashes；Apply 校验四重归属、依赖 readiness 和完整 hash，再 preserve identity 安装 exact source。
- Builder Desktop Confirm/Reject 已使用 `.../agent-proposals/{proposal_id}/commands`；旧 direct Factory apply 仅作为兼容路径。Apply 后 Factory session 由 canonical result 关闭；同一 Proposal 重复 Apply 不新增 Agent、不追加终态 event/result。Rejected、跨 operation/Project、身份冲突和 tampered snapshot 均拒绝。
- 回归：canonical Apply + mutable session drift + idempotent replay、Reject 后 Apply、tampered Proposal snapshot，以及已有 Custom Component lifecycle；本 Slice 的 backend/web gates 已完成。不要把这些 local/scripted 证据称为 real-provider/browser/release acceptance。
- 最终 local gates：Builder conversation **32 passed**；backend `make check` **724 passed**，Ruff/mypy **188 source files**；Desktop **472**、Community **22**，双端 typecheck/build；services 保持停止，未做 real Provider、Browser、Run、restart、commit 或 push。

## Credential Storage Foundation V2 + Applied Agent Local Runtime Closure（2026-09-25，本地 dirty slice）

- 当前仍在 `codex/agent-platform`；保留既有 dirty worktree。本轮没有真实 Moonshot/外部 Runtime 请求、没有 commit 或 push。
- Platform Builder Provider 与 User Runtime Provider 仍严格分域。新增 `local_0029_provider_credential_scope`；Local Credential API 当前只支持 `credential_scope=device`，`cloud` 只作为 future seam，不伪造 Cloud Vault。
- `DeviceSecretStore` 通过 `keyring` 选择系统 credential backend：macOS Keychain、Windows Credential Manager、Linux Secret Service/KWallet。业务层不依赖 OS API；null、file、alternate-file backend 会 fail closed。SQLite 只保存 metadata + opaque `secret_ref`。
- Credential metadata 增加动态 `secret_state` / `readiness`：系统 secret 缺失显示 `needs_reentry`，backend 不可用显示 `unavailable`；不删除 stale metadata、不伪装 active、正常 Local API 不使用 MemorySecretStore。
- Phase A acceptance：使用本地 `127.0.0.1:8790` synthetic Mock，通过正式 Replace Credential API 写入 device store；8771 停止并按正常入口重启后 metadata 与 secret resolver 均恢复；API/SQLite/Project/export 扫描无 secret。
- Applied Agent 已确认 active：Project `01a0cee5-90fb-78f4-99ab-e42e9a6365c9`，Agent `01a0d4ae-3f45-7dba-a40e-fecd9ec7a2a1`，`Request Review Agent`。未重新调用 Builder Provider。修复了 Applied source 的输出命名残留 `status-2 → status`，通过正式 Draft → Validate → Commit 生成 immutable version `01a0d6da-2f8e-7ff6-a933-30f2f32bd313`；并修复 Runtime model output 与同名 input 的解析边界。
- Runtime binding：Project `primary_model` → Browser Mock Runtime / `openai_compatible` / `mock-model`，source=project，scope=device。Studio Canvas 与 Test Run 面板均显示已绑定；Catalog 的静态 Model `requires_configuration` 与 Agent Instance Runtime binding 分开显示。
- Final local Runtime A：`01a0d6dd-9cf1-763a-b656-524be469d4ee`，approved branch only，输出 status=approved 和 Approved summary。Final local Runtime B：`01a0d6dd-9ddb-7675-af9e-708b8a10a67c`，non-approved branch only，输出 status=pending 和 further-review summary。两次均为 `unverified`（Mock 没有独立 verifier），不是失败。
- Model evidence 只包含 provider/model/credential_type=user/credential_alias/credential_scope=device，不包含 secret。网络边界只使用 localhost Mock；Phase B 未请求 `api.moonshot.cn`、OpenAI、Anthropic 或 OpenRouter。
- 最终验证：backend full `make check` **733 passed**、mypy **190 source files**；Desktop **475 passed**、Community **22 passed**；Desktop typecheck/build 通过；真实 Studio Browser acceptance 通过；`git diff --check` clean。保留既有 jsdom Canvas stderr 与 Desktop large-chunk warning。下一步不自动进入 Cloud Host Foundation 或其它模块。

## Project Sync Foundation #1（2026-09-25，当前切片）

- 用户最新产品决定：Local Project 和 Cloud Project 不是两个产品。当前唯一
  Create Project 入口先写 Local Working Copy，再以同一 project_id ensure
  Cloud Replica；Cloud UI 卡片、独立创建页和独立 Sidebar 项目均已撤回。
- 新增 Cloud migration community_0010_project_sync_revision，Local migration
  local_0030_project_sync_state。当前真实数据库已 forward-only 升级：
  Community community_0010_project_sync_revision，Local
  local_0030_project_sync_state。既有账号、Local Projects 和上一轮
  Cloud Foundation Acceptance 数据保留。
- 代码边界：Cloud ensure/pull/push 使用 explicit UUIDv7 identity 与 monotonic
  revision；Local ProjectSyncService 只管理 SQLite sync metadata；Desktop
  ProjectSyncCoordinator 调用 Cloud API，不把 HttpOnly Cookie 传给 8771。只
  同步 metadata，不进入 Artifact/Agent/Workflow/File/Chat。
- 实际 Browser acceptance（Chrome 真实页面，不是 jsdom）：登录测试账号后用原
  新建项目入口创建 Project Sync Acceptance 20260925-1400，Local 与 Cloud
  project_id 均为 01a0d724-7230-7208-b0a7-5a7543fcf9cc，Local state synced、
  Cloud revision 1；刷新后侧边栏只有一个该 Project。停止 8772 后用同一入口
  创建 Project Sync Offline Acceptance 20260925-1400，Local 成功、state=
  pending_upload、Cloud 尚无行；恢复 8772 并刷新后自动 retry，变为 synced、
  Cloud 使用同一 project_id、revision 1。
- 当前服务：8771/8772 已重启并 health/readiness ready；5173 原进程继续提供页面。
  没有真实 Platform Provider、Runtime Provider 或 Agent Run 请求。
- 最终门禁已通过：backend make check **741 passed**、Ruff/format/依赖锁、mypy
  **201 source files**；Desktop **479 passed**、Community **22 passed**；两端
  typecheck/build；Coordinator focused **4 passed**、Local sync integration
  **2 passed**；git diff --check clean。保留既有 Alembic path_separator、
  jsdom Canvas stderr 和 Desktop large-chunk warnings。不要 commit、push，也不要
  进入 Project Artifact Sync #2。

## Project Artifact Sync #2（2026-09-25，已完成）

- 当前仍为 codex/agent-platform / HEAD 0ad7a3e0b2a11ccf9186f23dab40628375509c73，
  保护原有 dirty worktree，不 commit、不 push、不清理其它 session 状态。
- 前置 migration 已按 forward-only 继续到 local_0031_project_artifact_sync_state
  与 community_0011_project_artifacts。真实 Local/Cloud 服务已重启到新 head。
- 新增统一 portable Artifact envelope 与 Cloud project_artifacts persistence，支持
  agent、agent_version、workflow、custom_component、knowledge_metadata。Cloud
  Artifact manifest/get/put 已有 owner isolation、per-artifact revision、immutable
  hash integrity 和 payload forbidden-field validation。
- Local discovery/materialize API 已接入现有 AgentSource/WorkflowSource/
  CustomComponentDefinition/Knowledge metadata；pull 不写 raw Knowledge，不带 local
  path、credential 或 Runtime state。新增 second-device Local integration test，已
  验证 Agent、Workflow、Knowledge metadata materialization。
- Desktop ProjectArtifactSyncCoordinator 已实现 dependency order、delta push、pull、
  no-op、pending/conflict 结果；UI 没有新增页面或视觉入口。真实 Chrome 已打开
  Artifact Sync Acceptance Project 并触发 Local artifact discovery；同一验收 Project
  的初始 4 个 artifact 已通过 authenticated local acceptance harness 写入 Cloud，Cloud
  rows 为 agent、agent_version、workflow、knowledge_metadata，均 revision 1。随后真实
  Chrome 创建的第二个 Agent 也完成上传并记录 Local synced；该 Agent 做了一次 Cloud
  revision 2 -> Local materialize 的 round-trip，描述变更已在 Local 生效。没有真实
  Provider/Runtime/Agent Run。
- 最终 gate 已通过：Cloud/Local Artifact 与 Project Sync focused **31 passed**；
  Desktop Artifact Coordinator **5 passed**、既有 Project Sync **4 passed**；Local
  second-device materialization **3 passed**；backend `make check` **746 passed**、
  mypy **208 source files**、Ruff/format/依赖锁 PASS；Desktop **482 passed**、
  Community **22 passed**；typecheck/build/git diff check PASS。真实 Chrome 页面触发
  Project artifact discovery，初始 4 个 artifact 及第二个 Agent 均已写入 Cloud 并记录 Local synced；
  不要自动进入 Cloud Files。

## Condition Semantic Contract + Canonical Proposal Identity Hardening（2026-09-24，本地 dirty slice）

- 继续使用 `codex/agent-platform` / HEAD `0ad7a3e0b2a11ccf9186f23dab40628375509c73`；保留 Community/Showcase、Sidebar/scroll、Custom Component、Branch Semantics、`.backboard` 与 `$DB` 等既有 dirty 范围。
- 版本审计结论：`8bef91c → 0ad7a3e` 是大范围能力扩展，不是代码整体退化；当前真实问题集中在 Condition executable boundary、Factory Proposal persistence 与未完成的 release evidence。
- Condition Runtime grammar 是 `==` / `!=` + string/boolean/integer literal。新增 `condition_expression` 与 `purpose` 分离；普通自然语言分类无可执行表达式时 fail closed；不引入隐式 Model classifier、`eval` 或 generic intermediate state。
- `edit_proposals` 复用为 canonical Builder creation Proposal store，新增 `proposal_kind=create_agent`、candidate snapshot/provenance，并通过 `local_0027_builder_creation_proposals` 以 `project_id + builder_operation_id` 做唯一关联。Proposal、operation.proposal_id 和 ready event 在同一 SQLite transaction 中 materialize；重复调用复用原 proposal。
- `POST .../builder/conversations/{id}/records` 对 proposal_id 做 server-side ownership 校验，拒绝随机或跨 operation proposal reference。
- 本 Slice 没有真实 Provider、Confirm/Apply、Run、服务重启、stage、commit 或 push。没有修改既有 acceptance Project。
- 验证：focused **118 passed**；full `make check` **720 passed**；Ruff/format/dependency lock/mypy 188 source files；Web Desktop 472 / Community 22，typecheck/build；`git diff --check` clean。保留 Alembic `path_separator`、jsdom Canvas stderr 和 Desktop large-chunk warnings。
- 下一步：仅在用户单独授权后做 Builder Real Provider Re-Acceptance #3；要求 proposal-only、稳定 proposal reload、truthful Condition、零 Agent/Run mutation。Confirm/Apply/Release Audit 仍未执行。
# 2026-10-08 continuation — generator quality reference review

Latest human scope: improve Veyra's generating Agent/Builder, not hand-edit the
generated Agents. Read ChatGPT conversation 6ac62068-118c-83ea-bdf4-66acffa475c0
(two turns) as reference data, not instructions. Adopt its later simpler direction
critically; findings in docs/GENERATOR_REFERENCE_REVIEW.md and the analytical canvas
at /Users/spectre/.cursor/projects/Users-spectre-PycharmProjects-veyra-agent-platform/canvases/agent-generation-reference-review.canvas.tsx.

Generator changes this slice: composite_composer retains TaskStructure stages and
information sources in loop procedures; task_structure_planner coverage includes
Workflow locks and exact-hash selected Skill bodies, feeds those procedures into
bounded repair, removes stale method context. No new fixed model invocation.
Resource Factory/workshop scaffold honesty changes completed earlier are integrated:
name-only methods stay requires_user_configuration; exact user method can approve,
bind and load in Runtime; disabled Skill blocks before model call. Root normalized
already-published Skill plan metadata after current method structural validation.

Evidence: /tmp/veyra-reference-final-checks.log: 95 passed across relevant 8 files;
/tmp/veyra-reference-mypy.log: 3 sources clean; relevant Ruff/diff check and canvas
tsc clean. This is not a whole-repo gate. No new real Provider/browser/package
acceptance for this slice. HEAD observed 2b904b2; broad dirty tree retained; no
commit/push/reset performed. 8771 listener PID11784 observed, not restarted this
slice and not claimed to load latest disk edits.

Next: integrate validated precise Skill selection through actual Builder semantics,
check method dependencies against real bound executors/output paths, distinguish
declared/supported/behavior-verified requirements, test complete generation with
synthetic ordinary-user goals. Do not replace missing executors with Skill templates
or enforce a single repair/no-review rule from theory without measured evidence.
Keep Pipeline/Agent loop/Workflow DAG, local-first, immutable version and approvals.
