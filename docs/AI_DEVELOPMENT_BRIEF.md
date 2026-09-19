# Veyra Agent Platform — 长期 AI 开发上下文

> 本文帮助新的主开发 Agent 在更换 Backboard API Key、账号、R-CLI Session、模型或
> 开发窗口后恢复职责、产品方向、架构边界和开发方法。它不是当前进度表，也不是
> 产品功能、测试通过或操作授权的证明。不要把开发连续性绑定在某个聊天 Thread 上。

## 1. 如何使用本文与判断事实

本文保存稳定的产品叙事和协作原则；详细产品设计仍由
[PROJECT_DESIGN.md](PROJECT_DESIGN.md) 维护，不另建一套竞争的工程规格。
本文描述的“应当”“目标”“闭环”是验收方向，不代表能力已经实现。

判断项目事实的优先级：

1. 当前实际代码。
2. 当前 Git 状态，包括尚未提交和未跟踪的代码。
3. [AGENTS.md](../AGENTS.md)。
4. [PROJECT_DESIGN.md](PROJECT_DESIGN.md)。
5. [DEVELOPMENT.md](DEVELOPMENT.md)。
6. [.backboard/HANDOFF.md](../.backboard/HANDOFF.md)。
7. 历史聊天、Codex 总结和本文引用的历史参考。

代码决定“现在做到了什么”，设计决定“希望做到什么”；代码存在不等于运行验收通过。
发现偏差应明确记录事实与目标的差别，不为了迁就旧总结修改真实项目。重要的产品或
架构分歧可以与用户讨论。当前用户指令决定本轮范围和授权，旧文档中的授权不是永久许可。

| 信息载体 | 长期职责 |
| --- | --- |
| `AGENTS.md` | 仓库贡献约束、安全边界、新 Session 入口规则 |
| `docs/AI_DEVELOPMENT_BRIEF.md` | AI 职责、产品定义、长期原则、开发方式、模块方向 |
| `docs/PROJECT_DESIGN.md` | 详细产品模型、架构决策、契约与设计边界 |
| `docs/DEVELOPMENT.md` | 当前模块实现、架构决策落地、验收结果、优先级和主要缺口 |
| `.backboard/HANDOFF.md` | 正在做什么、刚完成什么、working tree、实际测试、中断点和具体下一步 |
| Git / 实际代码 | 最终事实来源；远端提交不包含本机未提交成果 |

不要向本文追加当前 HEAD、未提交文件清单、临时 Bug、测试总数、服务端口/进程状态、
Session ID、Thread ID 或某个账号的工具可用性。历史测试警示只用于防止误认，不维护为计分板。

## 2. 主开发 Agent 的职责

你接管 Veyra Agent Platform，担任主开发窗口和技术负责人。职责不是只给方案，
而是在用户授权范围内持续推动项目，直到整体产品目标得到真实交付；暂停、文档限定
或其它本轮范围约束优先，不能借长期职责擅自继续实现。

主窗口负责：

- 产品与技术架构决策，完整闭环设计。
- 复杂和棘手 Bug、跨模块实现、高风险修改和安全边界。
- 大改动审计、最终代码 Review、模块验收和真实运行验证。
- 开发文档维护，以及辅助 Agent / 子窗口的范围和质量控制。
- 对结果负责：读取、实现、检查、修复、交接，而不把计划写成完成。

代码必须可读、可维护、边界清晰，优先复用现有抽象与依赖。避免无意义重构、
为未来需求过度抽象、不断叠加临时补丁，以及为了“保险”堆积低价值测试。
围绕具体风险选择测试，不在局部问题上无限纠结；确有架构分歧时及时讨论。

## 3. 模型与子任务委派

不要让最高级模型承担所有机械工作。主模型负责架构、复杂实现、跨模块问题、
高风险修改、关键 Review 和最终决策；文件定位、少量代码阅读、重复搜索、窄测试、
静态检查、简单 Review、结果汇总可委派给低成本或低思考模型。

- 若工具确实允许选择模型，可根据复杂度使用 Luna / Terra / Sol / Astra 等可用模型；
  名称只是示例，不假定所有账号都有这些模型或相同能力。
- 工具不支持选择时，不得声称已经做了模型路由；工具不可用时由主窗口接手限定任务，
  不把某次账号限制写成永久项目限制。
- 委派必须说明目标、文件范围、是否只读、禁止事项、验收方法和预期输出。
  默认最多一个辅助窗口，禁止辅助窗口再委派；不同并发规则须有明确授权。
- 主窗口核对报告和差异，不把辅助窗口的结论直接当成验收。共享契约、依赖锁和迁移
  head 同一时间只有一个写入负责人，不让多个窗口覆盖同一文件。
- 子窗口不得自行扩大范围、提交或推送；需要写入或提交时先明确其授权和所有权。

## 4. 仓库、环境与工作区安全

- Repository：`/Users/spectre/PycharmProjects/veyra-agent-platform`
- GitHub：<https://github.com/wenjiesong04/veyra-agent-platform>
- 主要开发/集成分支：`codex/agent-platform`
- 独立 Conda 环境：`veyra-agent-platform`
- Python：`/opt/anaconda3/envs/veyra-agent-platform/bin/python`

这些是开发接管基线，不是产品运行时可硬编码的用户路径。环境要求以当前
`Makefile`、依赖定义及实际检查为准；不要用系统 Python 替代专用环境跑项目检查。
不复用旧 Veyra 环境，不把旧仓库加入 `PYTHONPATH` 或包搜索路径。旧项目只作为
只读迁移证据，提取行为必须重新归属到本项目并留下来源、理由、契约和测试。

尊重现有 working tree：不随意 reset、不 checkout 覆盖修改、不清理不认识的文件。
只编辑当前授权范围；遇到冲突先核对，不从头重做或丢弃旧窗口留下的代码。
不要使用整体暂存掩盖文件归属，尤其不能整体暂存 `.backboard/` 的会话和账号状态。

API Key、`.env`、Secret、凭据、用户数据和 Runtime state 不进入日志或提交。
不为恢复开发读取账号配置、会话对象或凭据文件。Agent source、导出包、浏览器存储、
SQLite 明文和产物不得携带 Secret 值；只保存受控引用，值留在主机密钥设施/显式环境中。
不自动加载用户 Project 的 `.env`；仓库开发启动的主机配置与 Project 数据边界必须分开。

## 5. Veyra 为什么存在

**Veyra 是一间属于用户自己的 AI 工作室。**

普通用户不应先学 YAML、API、MCP、Agent Framework 或 Runtime 细节，才能让 AI
按自己的方法工作。用户可以用自然语言描述方法，再逐步将它转换成可视化、可修改、
可运行、可观察、可控制、可验证、可重复使用、可安全分享的 AI 工作系统。

例如：“我想做一个研究助手，它可以阅读项目资料、查询外部信息、整理报告，
但写文件之前必须让我批准。”Veyra 应帮助用户把它构建成真正可运行的 Agent / Workflow，
同时看清能力、数据、权限和结果证据，而不是只生成一段看似正确的 Prompt。

Veyra 不应被做成单纯的 Agent Workflow 编辑器、Prompt 管理器、Dify / Coze 复刻、
只有 Canvas 的流程图工具，或只有聊天框的 Agent Wrapper。源码可检查和可拥有，
不等于要求每位用户直接编辑源码。

产品主线：

```text
Idea → Build → Run → Observe → Trust → Reuse → Share
```

| 产品面 | 用户价值 |
| --- | --- |
| Canvas / Studio | Build：可视化设计和修改 |
| Resource Library | 配置可用能力、绑定版本与依赖 |
| Veyra Chat / Builder Agent | 在 Global、Project、Agent、Workflow 上下文自然语言创建和修改 |
| Knowledge & Files | 明确选择的可信上下文 |
| Runtime / Runs | 执行、审批、观察、恢复、审计 |
| Community | 发现、讨论、发布、导入和复用 |

每个新功能都要回答：它是否加强了 Build / Run / Observe / Trust / Reuse / Share
中的某个真实闭环？只增加术语、资源数、页面数或技术复杂度，而不能形成可验收的
用户价值，就应暂缓。区别不在“也有 Canvas、Tool、MCP、Workflow”，而在帮助用户
构建它、理解它、控制它、验证它、重复使用它、安全分享它。

## 6. 核心对象与长期架构边界

Project 是用户工作空间，包含或关联 Agents、Workflows、Knowledge、Files、Resources、
Runs。对象之间应有明确来源、版本、权限、依赖、生命周期和 Runtime 关系。
“属于 Project”是逻辑关系，不意味着把聊天、Run 状态、账号和 Secret 都写入 Project 文件夹。

- Project 是容器和 Dashboard，不是又一个图编辑器。
- Agent 与 Workflow 是平级资源；不能把 Agent 改名成 Workflow。Agent 定义可运行能力，
  Workflow 用固定 immutable Agent version 编排调用和控制流。
- Agent source 为 `*.vagent.yaml`，Workflow source 为 `*.vworkflow.yaml`。
  Draft 可修改且受 revision/ETag 保护，已保存/发布版本不可变。
- Source、behavior、依赖锁和包内容需要各自可核对的 hash；仅移动 Canvas 布局不应
  改变 behavior hash，行为变化不能伪装成纯 UI 改动。
- Project 保存用户可检查的定义和资源；运行、聊天、账号、Secret、缓存放在各自的
  应用数据/主机安全边界内。数据根按主机解析，不回退到旧仓库状态目录。
- Local-first Desktop 与 Community 分离：本地 SQLite WAL、repository/migration 与
  内容寻址对象存储；公网 Community 采用独立数据库和对象存储部署，不能暴露桌面 sidecar。
- Local API/Runtime 归 `backend/src/veyra_agent_platform/local/`，公共账号/registry 归
  `backend/src/veyra_agent_platform/community/`，共享 schema 归
  `backend/src/veyra_agent_platform/contracts/`；`web/apps/desktop/` 与
  `web/apps/community/` 分离，`web/packages/` 复用 UI/契约客户端，测试按子系统镜像组织。
- 装配入口只做 wiring；不引入巨型入口或万能 `utils.py`、`services.py`、`helpers.ts`。
  Orchestrator 应以确定性调度、依赖、lease、隔离、重试和恢复工作，不由 LLM 接管调度权限。

Local-first 不自动等于匿名或离线免登录：账号与 Desktop 访问规则以详细设计和代码为准。
Veyra Community 账号与开发工具 Backboard 账号不是同一身份系统，切换后者不是迁移产品数据。

## 7. Studio / Canvas

Studio 是 Agent / Workflow 的可视化设计环境。Canvas 展示结构、执行逻辑、依赖、
工作路径和真实运行状态，不能声称展示模型不可见的内部思维过程。

可表达 Input、Model、Tool、MCP 能力、Transform、Condition、AgentCall、Verifier、
Human Approval、Output 及其它正式支持的能力，但产品概念不等于同名 wire 节点：

- 输入由 source inputs 与 Start 等真实契约表达，不虚构独立 `Input` 节点类型。
- Agent 画布主要承载 Start、Model、Tool、HumanApproval、Verifier、Output 和显式知识绑定。
- Workflow 画布承载 Start、AgentCall、Condition、Transform、HumanApproval、Verifier、
  Output；不直接放 Model 或 Tool。AgentCall 锁定 `agent_id@version_id`，不是文件路径或
  随时变化的 latest。历史 Agent 控制流兼容不等于新产品边界改变。
- MCP 在资源和 UI 中归入 Tools，发现描述经规范化后落为 Tool 节点；不是与 Agent、
  Workflow、Component、Knowledge 平级的新产品层。
- Component 保留 primitive / composite 分类；composite 展开成已锁定的 primitive，
  不是任意新 Flow 类型。Knowledge、Files、Runs、Resource Library 不因共享编辑能力而变成 Canvas。

Canvas / Form / Source 应围绕同一规范化结构形成稳定往返编辑：稳定节点 ID、语义不丢失、
布局不改变行为、差异可审查。临时不完整画布不覆盖最后有效 source；冲突要求显式处理，
不静默覆盖。可设计、结构有效、依赖就绪与能真实运行必须区分。

## 8. Agent Chat / Factory

2026-09-14 产品决策：自然语言构建统一从 **Veyra Chat** 进入，不在 Studio 顶部维护
独立“自然语言修改”产品。Studio 负责结构/Canvas、手动 Form/Source 编辑、配置、验证、
Run 和 AI 修改结果。Project Chat 操作已绑定项目；Global/New Chat 从用户目标开始，
必要时显式选择或创建 Project。运行已有 Agent 的 Conversation 不等于 Builder Chat。

Veyra Builder Agent 是平台自己的项目构建 Agent，不是普通聊天机器人。稳定 Prompt
保存产品模型、资源优先复用、最小权限和确认原则；动态 Harness 注入真实项目清单、目标
source/revision/ETag、资源锁/readiness、权限和数据绑定，不把状态堆进静态提示词。
Factory 保留为创建 Blueprint 的适配器，Edit Proposal 提升为共享安全变更协议；按上下文
扩展能力，而不是长期维护 Factory、Studio AI、Project Chat、Agent Builder 四套逻辑。

优先组合 Resource Library 已有资源，缺失时明确提出缺口。未来生成 Veyra-native
Component/Tool/Skill/Policy/Template 必须有 source、类型、版本、权限、依赖、readiness、
compatibility、validation 和 provenance；可执行代码/高权限 Tool 必须严格审查。项目专用
内容放 Project，可复用资源由用户选择仅本项目或保存 Library，不能自动发布 Community。
当前先验证单对象 Chat → Proposal/Diff/Impact → Confirm → Apply → Canvas/Validation，
不借长期目标一次实现通用 Project mutation、任意工具生成或自动批准。

用户不想拖拽节点时，应能直接说“增加一个 PDF 输入”“写文件之前加入审批”
“把搜索结果交给总结节点”。AI 不能偷偷修改项目。

```text
用户请求 → 理解意图 → Proposal → 影响范围 → Diff / Candidate Source
→ 用户确认或拒绝 → Apply → Validation → revision / ETag conflict protection
→ Undo → Runtime 验证
```

这描述用户可检查的闭环，不是把安全检查延后执行：候选生成时就要验证，Apply 前必须
重新检查 revision/ETag、权限和依赖，Apply 后再次核对实际 source。用户确认针对保存的
候选，不能确认后再偷偷生成另一份；拒绝不改变 source；Undo 通过受冲突保护的新 revision
恢复，不能覆盖确认之后用户的其它编辑。影响范围必须来自真实差异，而非模型口头描述。

Factory 只提出受限语义计划/候选，由服务端编译为 canonical AgentBlueprint，
并解析已登记资源、精确版本、权限、Policy 和锁，
校验后才能写入 Draft。模型输出不可信，不能自行注册未知 Tool、授权、执行、发布或宣称验证成功。
缺失能力应成为显式提案；修复循环有界，不不断试到绕过约束。

Factory 创建对话与运行已有 Agent 的 Conversation 分开。长期目标不仅是“生成一个新 Agent”，
而是成为整个 Project 的自然语言操作入口；单对象编辑不等于已实现多对象 Project 事务。
Factory Provider 与用户 Runtime Provider 的配置、密钥和预算分开；生成器使用哪个模型
不应把生成的 Agent 绑定成只能由该供应商运行。具体默认模型以当前配置为准，不固化在本文。

## 9. Resource Library

Resource Library 是能力仓库，统一呈现 Model、Tool、MCP、Skill、Policy、Component、
Template、Plugin 或其它正式支持的资源。这个产品清单不是声称当前 schema 有相同枚举：
Model 可体现为节点/Provider 配置，MCP 归 Tools，Plugin 可作为声明式资源包入口。

每个资源应展示类型、版本、来源、配置状态、Runtime readiness、权限、依赖和兼容性；
使用精确引用与 content hash，不用显示名称冒充版本身份。

```text
Catalog → Project Library → Agent / Workflow Binding → Runtime
```

全局 Catalog 是发现入口，Project Library 是已选依赖及其锁和使用位置；Studio palette
只是 Project bindings 与内建 primitives 的投影，不能替代前两者。内容漂移应要求显式
重新绑定，不因相同版本字符串而静默接受不同能力。

禁止“假能力”：资源可见不等于 adapter 已实现或 Provider 已配置。不可运行时明确显示
`unsupported`、`requires_configuration`、`design_only`、`unavailable` 等真实状态；
隔离、禁用和待审状态也不得伪装为成功。状态命名和语义以实际契约为准。
结构校验通过、依赖 readiness、主机凭据就绪和实际 Run 成功是不同层次的证据。

## 10. Knowledge 与 Files

Knowledge 和 Files 提供可信数据上下文。文件存在于 Project 中，不等于用户同意把
全部内容发送给模型；必须明确选择和绑定需要使用的知识或文件。

Knowledge 应逐步具备来源、版本、content hash、提取、分块、检索、引用、provenance、
权限和版本历史。绑定应能定位实际使用版本及内容，运行时留下可追溯的知识证据。
这些是建设方向，不是完整 RAG 管线已经验收的声明。

Files 可以浏览和预览；Agent / Runtime 真正读写文件必须经授权的 Filesystem Tool，
遵守 Project 根目录、路径与 symlink 安全、权限、Secret 防护、Human Approval 和
Runtime receipt。UI 预填相对路径不授予读取权限，也不自动读取其内容。
文件管理、知识提取 API 仍须遵守各自的数据与权限边界，不能借“管理操作”绕过安全约束。

## 11. Runtime / Runs 与可信 Agent

点击 Run 后，不只给最终答案。用户应能理解哪个节点开始/结束、哪个模型/Agent/Tool/MCP
被调用、读了什么、写了什么、哪一步等待审批、审批和 Verifier 结果、AgentCall 固定版本、
失败位置与原因、耗时以及最终结果来源。这是可观察执行，不是模型内部思维展示。

运行证据链应贯通 Events、Tool receipts、Inputs / Outputs、Approvals、Artifacts、
Errors 和 Verification；证据带 Run、节点、序列与版本关联，敏感内容按权限脱敏。
模型说“完成了”不是外部 effect 的证据，Tool 成功也不能替代独立 verifier 的判断。
外部 effect 必须有授权决策、receipt 和 verifier outcome；缺证据时显示未验证或失败，
不显示虚假的 verified。

用户最终应能 Stop、Approve、Reject、Retry、Resume、Replay / Inspect。每个控制必须
明确适用状态和 effect 语义：审批等待的继续、终止后的新尝试、checkpoint 恢复、只读
事件回放不是同一件事。未知外部 effect 不能盲目重试，重启不能静默重放副作用。
尚未支持的控制明确禁用或解释，不能因为设计列出按钮就声称已实现。

稳定 Agent 不只是一次聊天或一个 Prompt，而是具有 Source、Version、Resource dependencies、
Permissions、Security boundaries、Runtime evidence、Repeatable execution 和 Conversation
relationship 的数字工作者。用户既可在 Workflow 中调用 Agent，也可开启持久化 Conversation
连续交互；每次执行绑定明确 Agent Version 和 Run，多轮聊天不应失去版本和运行历史关系。

Run Workbench / Monitor 关注当前需要操作的运行、阻塞、审批、失败和验证缺口；Runs
保留可检查的历史，Data / Analytics 使用真实运行指标，而不是重复绘制相同页面。

## 12. Community 与安全分享

Community 不只是下载市场。长期包括作品展示、Feed / Discussion、发布、评论、点赞、
收藏、关注、Review、Report、Moderation 和资源复用；这些是方向，不把已有 registry
切片等同于完整社交社区或生产就绪。

分享对象可逐步覆盖 Agent、Workflow、Project、Component、Tool、Skill、Template 及
其它正式支持的资源。用户在导入前应能检查 Canvas Preview、Version、Dependencies、
Permissions、Compatibility、Provenance，再选择：

- 把 Skill / Tool 添加到 Resource Library。
- 把 Agent / Workflow 导入 Project。
- 从 Project Template 创建新项目。

版本、来源、许可、Fork lineage、升级差异和权限变化必须可检查。点赞、下载量或
Review 不代表安全，也不能替代本地验证。Community 不在服务器执行下载的 Agent 或插件；
源码、枚举或分享 manifest 存在，不证明发布、下载、导入、配置、首次运行已经全部贯通。

## 13. 外部导入与统一 Runtime

任何 Community 或外部资源都不能下载后直接执行未知代码。

```text
Source Identification → Safe Extraction / File Scan → Permission Inspection
→ Dependency Resolution → Capability Resolution → Compatibility Preview
→ Import Preview → Veyra Draft → Canvas / Runtime
```

Folder、ZIP、YAML 等入口是否可用以实际 importer 为准；不能把旧规划中的“未来支持”
反复当成当前缺口，也不能因出现入口就宣称所有格式兼容。ZIP 只是安全解压后复用 Folder
扫描流程；YAML 是 Agent Definition，不是直接可执行程序。限制路径、symlink、大小和
内容风险，不自动安装依赖、启动 MCP、运行 Shell/Python/Node 或导入凭据。

无法映射的能力、权限、知识和外部工作流步骤应保留显式兼容性报告，不能静默丢弃或
自行授予权限。导入、隔离、审查、激活、能力发现、绑定和运行是不同授权阶段。

优先统一路径：

```text
Importer → Import IR → Capability Resolver → Veyra Source → Veyra Runtime
```

不要为了兼容 CrewAI、AutoGen、LangGraph、Dify 等格式各自维护一套 Runtime。
适配器转换成 Veyra 统一结构；未知能力留为 unsupported / review required，受审核能力
才进入 Catalog 和 Runtime，不让外部包扩大主机安全边界。

## 14. 前端原则

Desktop 是主要工作台。现有前端大部分应保留并渐进优化，优先根据真实后端能力完善
UI，不为重新设计而重新设计，也不复制旧 Veyra 的产品模块和状态模型。

Community、Resource Library、Knowledge、Run Workbench、Monitor、Data / Analytics
可以重点重新审视，但必须符合产品对象与职责：信息架构清晰、用户能理解、有来源和
下一步行动、真实能力与未配置能力可区分。空数据、错误、缺配置和不可用状态要诚实；
不依赖假数据，不用视觉效果掩盖后端缺失。单测或构建通过不代表真实浏览器体验已验收。

## 15. 模块规划与历史信息边界

历史 Codex 曾按六个用户可感知模块组织项目：Canvas、Resource Library、Community、
Agent 对话平台、Knowledge、可视化运行工作台。这是规划参考，不是不可修改的绝对架构，
也不等同于详细设计中的 Studio / Runtime / Orchestrator / Monitor / Library / Community
工程分层；不能因不同视角而删除或重复实现某个模块。

**历史完成状态与测试数字都不是永久事实。** `Python 289 passed`、`Desktop 211 tests`、
`Community 15 tests` 是 DEVELOPMENT / HANDOFF 中可见的历史记录，不是本文核验得到的
当前通过结果，也不是质量目标。旧的“模块完成”“尚未接入”“已支持/未来支持”同样
需要按具体代码修订重核，不能把旧 Session 的成功结果继承到 dirty working tree。

本 Brief 不重做全仓模块审计，不建立新的完成度表。指定资料包含已有实现切片，也包含
目标与历史快照；只做有限代码核对时，未快速确认的模块结论一律作为历史参考/待核验。
判断当前状态必须重新依据当前代码、Git、DEVELOPMENT、HANDOFF 和实际测试。
具备类、schema、API 或 UI 中的某一层，不足以宣称整个用户闭环完成。

## 16. 三个跨模块闭环与长期顺序

### A. 设计闭环

Canvas + Resource Library + Knowledge + Agent Chat：

```text
设计 → 修改 → 资源绑定 → 知识绑定 → 验证
```

重点是同一份有效 source 的往返编辑、真实差异、用户确认、依赖/知识锁和冲突保护。

### B. 执行闭环

Canvas + Agent / Workflow + Runtime / Run Workbench：

```text
设计 → Run → Observe → Approval → Evidence → Retry / Resume
```

重点是固定版本、证据链、授权与审批、失败说明、恢复语义，而非只返回模型文本。

### C. 分享闭环

Community + Import / Export + Version + Dependency + Permission + Compatibility：

```text
Publish → Discover → Inspect → Import → Configure → Reuse
```

重点是安全可移植版本、导入预览、配置缺口、升级检查和首次本地运行。

长期优先顺序：

1. 本地核心闭环：设计 → 对话修改 → Resource / Knowledge Binding → Run → Evidence。
2. Community 的 Agent / Workflow 发布 → 导入 → Version / Upgrade。
3. 扩展 Project、Component、Tool、Skill 和 Community Interaction。
4. 最后完成真实外部 Provider 验收、Production Deployment、Desktop Distribution、
   Soak / E2E 与用户试用，作为发布就绪门禁。

这个顺序不是停止前期窄 E2E、Provider adapter 或安全测试的理由，也不是重写已经存在
的部署/导入代码的理由。以真实代码续接切片；具体当前下一步由 DEVELOPMENT / HANDOFF
在核对工作区后确定，并服从用户本轮范围。

## 17. 开发循环、验收与 Git 规则

按大模块推进，模块内部按小切片交付，不一次试图完成整个项目。

每个有意义的小切片：

```text
读取必要文件 → 实现 → 窄测试 → 必要静态检查 → Review Diff → 修复明确问题
→ 更新 docs/DEVELOPMENT.md → 更新 .backboard/HANDOFF.md → 下一切片
```

先找实际调用路径和已有约定，不为局部工作重扫全仓。测试覆盖修改风险与用户行为，
无需每次全量；涉及契约、迁移、安全边界和跨模块语义时扩大相关验证。失败、未运行、
阻塞、fake provider 与真实外部调用要分别记录，不把“计划运行”写成通过。
文档限定任务只做相关文档核验，不以常规循环为由修改产品或扩大交接文件范围。

检查入口从当前 `Makefile` 和 `web/package.json` 确认，不凭记忆编造命令。
后端先在专用环境按需执行 `make verify-environment`，切片用选定 pytest / Ruff / mypy；
模块门禁按影响范围选择 `make check` 及 `web` 工作目录的 `npm test`、
`npm run typecheck`、`npm run build`。这些是入口指引，不是已运行记录。

完整模块完成后，在获得本轮所需操作授权的前提下：

```text
针对性验收 → 必要全局门禁 → 重启受影响真实服务 → 检查实际运行
→ Review → Commit → Push codex/agent-platform → 检查远程结果 / CI
→ 更新 DEVELOPMENT / HANDOFF → 下一模块
```

- 产品验收至少实际执行一次相关用户路径：契约/API 测试不是 UI E2E，fake provider
  不是真实 Provider 验收，本地存储 readiness 不是公网部署/备份恢复证明。
- 使用临时 Project、SQLite 和对象根测试，不对用户实际数据试验迁移或外部 effect。
  真实服务验证应核对运行身份；服务未加载当前代码时不能把 health 算成该修订通过。
- 提交前查看 `git status`、diff、暂存区和最近提交风格，按文件名暂存本模块内容，
  核对无 Secret、用户数据、Runtime state 或无关改动；不得绕过失败的 hooks/检查。
- 未提交工作区证据与精确 commit 证据分开，记录实际命令、代码范围、结果和缺口。
  push 成功不等于 CI 通过，必须实际检查远端结果。
- Commit、push、服务重启和其它外部/破坏性操作受当前明确授权约束；这段流程不是
  自动授权。用户说“不提交 / 不推送 / 不重启”时严格停止在此前边界。
- 不 amend、force push、改 Git 配置、reset 或覆盖未归属修改来制造干净结果。
  未完成或受限的验收如实交接，不能标为模块完成。

交接至少记录：目标、实际完成内容、文件归属、实际命令与结果、未运行项、未解决风险、
当前 working tree、中断位置和下一步具体动作。计划、辅助报告、测试数量都不能代替证据。

## 18. 新 Session / 账号恢复流程

同账号且工具支持恢复时，可以继续已有 Session；若换账号、API Key、Session、模型或
开发窗口后无法恢复，不依赖聊天记忆，不因为旧 Thread 不可访问而重开项目或丢弃代码。
新主开发 Agent 必须先按顺序读取：

1. `AGENTS.md`
2. `docs/AI_DEVELOPMENT_BRIEF.md`
3. `docs/PROJECT_DESIGN.md`
4. `docs/DEVELOPMENT.md`
5. `.backboard/HANDOFF.md`

然后在仓库目录执行：

```sh
git status -sb
git diff --stat
git diff --name-status
```

核对实际分支、已跟踪差异、暂存区和未跟踪文件；后两个命令不包含未跟踪文件内容，
必要时只读取与任务有关的新文件。会话对象仅识别其存在，不读取账号或凭据内容。
Git 的本地 upstream 信息不代表已查询最新远端，不能凭无 ahead/behind 声称已同步。

用实际代码修正过时交接，区分已有成果、未完成实现、历史验收和当前用户授权，再重建
限定范围 Todo，从确切中断点继续。恢复上下文不等于获得继续产品实现、提交、推送或
重启的许可；若旧交接催促开发而当前用户要求暂停，以当前要求为准。

遇到资料缺失时先保留代码并说明缺口，不猜测 Session ID 或模块完成状态。开始实现前
按需核对专用环境，结束前维护当前交接。跨机器恢复还必须安全保留所需未提交代码与
上下文文件；本地存在或能恢复聊天，不等于成果已进入 Git 远端或已备份。
