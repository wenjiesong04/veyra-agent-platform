# Model Capability Registry & Runtime Setup V1 — delivery report

本报告记录 2026-10-04 的当前工作树实现与验证。测试使用 fake Provider、临时
SQLite 和内存 SecretStore；未调用真实 Provider，未 stage、commit 或 push。

## A. Baseline

基线 HEAD 为 `2b904b2`，分支 `codex/agent-platform`。接手时已有 Builder 实时状态、
Workflow App、用户 UI/Runtime 改动和未跟踪 `.backboard/settings.json`；均保留。
本轮在同一未提交工作树集成，没有把既有修改重置成历史交接版本。

## B. Existing Provider Architecture

复用设备本地 `ProviderCredentialStore`、`SecretStore` 和 Project/Agent Runtime
binding。API Key 留在系统安全存储；SQLite、Model Profile、Proposal 和 Run evidence
只保存元数据或引用。Platform Builder Provider 与用户 Runtime Provider 继续分离。

## C. Model Capability Contracts

统一 16 项输入、生成、结构、Agent 与专用能力。每项为
`supported / unsupported / unknown` 并带安全 evidence；metadata 独立记录。
没有用模型名称猜能力，`image_input` 不能满足 `image_generation`。

## D. Model Registry

每个连接可发现或手动添加多个 Model Profile；支持查询、能力级默认值、digest/revision
和连接就绪状态。`registry_ready` 表示档案和连接可参与解析，具体能力仍须逐项具备证据。
发现模型本身不会把未知能力标成支持。

## E. Provider Discovery

保存或重查 API 请求 Provider 模型列表，不发送生成请求。模型列表没有能力信息时保持
unknown；目录不可用时可手动添加 ID。保存的默认 ID 未列出时保留原值并提示补配置，
不会静默改成另一个模型。

## F. Capability Verification

V1 主动探测覆盖文字生成、结构化输出、图片理解、图片生成，均由用户显式触发。
图片探测必须确认可能产生 API 费用，切换能力或完成一次探测后重新确认。
其它能力接受可信 Provider metadata/adapter evidence，暂不提供主动探测。
探测输出和原始 Provider 错误不进入持久化证据。

## G. Model Resolver

纯函数、确定性解析：Agent 显式绑定 → Project 绑定 → 能力/角色默认 → 当前合格 Profile。
未知、明确不支持、失效连接和 stale evidence 不能满足 required。
错误的显式绑定会阻止运行，不会自动落到另一个默认模型。

## H. Builder Integration

从 TaskStructure/ExecutionPlan 按 actor 和 model role 派生能力需求。Proposal 显示理由、
候选 Provider/模型、缺少与未知及不支持的区别。模型缺口不进入 ResourceFactory。
缺模型仍可审核和 Apply，产物标 Needs Setup；运行前按当前本机配置重新解析候选。
可选能力只有在编译出的路径明确允许回退时才可降级。
当前 V2 loop 使用平台 JSON action，未调用 Provider native tools/JSON mode；因此不会把
平台 Tool boundary 或 typed output 错报为原生 `tool_calling/structured_output` 缺口。
实际使用 `response_format` 的 graph Model 仍校验结构化输出能力。

## I. Runtime Preflight

Agent 与 Workflow preflight 返回结构化 setup issues，检查当前 Profile、连接、所需能力、
版本和 digest。可信 metadata/adapter 与 active probe 使用同一能力证据标准；不会因为
总体 verification state 是 declared 而否认有效 metadata。每次实际模型调用前再次检查。

## J. Runtime Setup UX

共享 RuntimeSetupPanel 使用紧凑状态条与原页配置窗口。已有兼容模型时可直接选择并按
真实 Agent/slot 保存绑定，随后自动 preflight；未知模型须明确选择并确认费用后验证。
可在窗口中添加 API 和手动模型 ID，失败重试复用已经保存的连接。任务输入不会因此离开页面。
高级模型管理另开标签；返回时刷新配置。未知图片理解模型不会被自动选作图片生成模型。

## K. Agent App

保留 committed-only 运行与对话版本 pin。缺能力禁止 Run；保存 Runtime 配置不改 immutable
source。导入 Agent 的回归证明同一 committed version/source_hash 可由 Needs Setup 转 Ready。
图片模型 readiness 结果现可被 Desktop parser 正确读取。

## L. Workflow App

复用独立运行窗口、committed version、节点进度与子 Agent 运行。聚合子 Agent setup issues
并保留 node/agent 身份，可为 Renderer 的 image slot 配置图片生成模型。Studio 仍测试 Draft。
需要审批但没有已支持审批关卡的 Workflow Tool 继续 fail closed。
按用户指定的 taste-skill 现有项目重设计指导审计：主任务去掉双层卡片，历史和流程预览默认
折叠，类型和输入标签本地化，节点 ID 进入技术详情；运行按钮改为普通文字 CTA。
补齐历史失败重试、版本切换的过期响应保护、说明/历史/流程展开等交互回归。

## M. Migration

`local_0036_model_capabilities` 在 `local_0035_workflow_versions` 后建立 Model Profiles、
role defaults 和 discovery 状态。旧模型 ID 回填 unknown，不制造验证证据。
fresh DB 与 0035→0036 upgrade 已用隔离数据库验证。当前本机 health 可见 0036；本轮未手动
迁移真实用户数据库。

## N. Acceptance Matrix

A/B：文字与图片理解按实际能力证据解析；C：vision 不满足图片生成；D：unknown 阻止 required；
E：包装创建保留可 Apply 的 Needs Setup；F：后来添加图片模型后重新检查同一源码；
G：错绑在 Provider 调用前拒绝；H：停用/删除/缺 Secret 不会保留旧 Profile 就绪状态；
I：重查、endpoint/Key 生命周期使旧证据失效；J：导入 Agent 在同一 committed version 上补齐配置。
对应证据来自 Registry、Resolver、Builder/Composite Apply、Runtime preflight 和导入集成测试。

## O. Regression Gates

- Desktop：72 files / 574 tests passed；typecheck passed。
- Desktop production build：passed，保留已有的 Vite 大 chunk 警告。
- Backend `env -u PYTHONPATH make check`：982 passed；依赖、format、lint、mypy 通过。
- `git diff --check`：clean。
- Browser：真实 Chrome 登录态运行页检查了布局；原组件只读预览检查暗色和 390px。
  API 配置入口、返回/关闭、版本选择和运行按钮完整可见。选择/保存/主动验证/绑定/自动检查的
  效果路径通过 fake API 交互测试；浏览器验收未启动 Workflow 或调用真实 Provider。
- 390px 的版本选择器 width=324px、height=36px，运行 CTA 保持在可用宽度内。
- 临时验收源码、标签和临时 viewport 已清理；用户主页面主题未更改。

## P. Remaining

用户在原启动环境重启 8771 后，最终代码已加载：新进程启动晚于末次后端修改，health `ok`、
schema 0036、database_ready=true，Builder configured=true。真实礼品 Workflow 的 committed
预检核对 version_id/source_hash 一致，当前只剩 `image_generation` 未验证。
用户须配置或验证具有该能力的模型后才能运行；这是实际配置缺口，不再是无效 readiness 响应。
语音、视频、embedding 等能力已有词汇、档案和 metadata 匹配，未新增它们的 Runtime 执行器或主动探测。

## Q. Files Changed

主要新增 `local/models/`、`builder/model_requirements.py`、migration 0036、Model Registry Settings
与共享 Runtime Setup UI。集成点为 credentials routes/store、Runtime/Workflow service、Factory V2、
Desktop local client/contracts、AgentChatSurface、Workflow App 与 Proposal Review。
Registry、Resolver、Builder、Runtime、导入、升级和 Desktop 测试已补充。完整列表以当前
`git status -sb` 和 diff 为准；此前 Workflow App/Builder/user 修改不算本轮独占成果。

## R. Verdict

COMPLETE（本轮实现、本地门禁、界面与 live preflight 验收）。8771 最终加载已核对；用户在原终端
完成重启，代理未读取密钥。没有由代理调用真实 Provider、commit 或 push；不声称实际图片生成、
打包发布或远端 CI 已验收。
