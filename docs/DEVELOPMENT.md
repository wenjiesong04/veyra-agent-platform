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

每次提交前必须：

1. 查看 `git status`、`git diff` 和最近提交；
2. 只暂存当前模块的文件；
3. 在专用 Conda 环境执行对应后端/前端验收；
4. 记录精确 commit SHA 和测试结果；
5. 重启受影响的开发服务，使用 `/api/v1/health` 核对实际加载的 SHA；
6. 不读取、打印、复制或提交根目录 `.env`、凭据、用户 Project、SQLite runtime state。

## 3. 事实基线

### 已由当前代码和测试证明

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

1. 修复 Desktop 导航树和面包屑的重复 React key 警告，并增加不会镜像实现的行为验收。
2. 审计并完成阶段 A 的自然语言修改计划/差异/确认边界；现有 Factory 生成 Draft 不
   等同于修改既有 Project/Workflow。
3. 将 Runtime 证据模型和 Run Workbench 对照设计逐项核对，优先补缺失的 artifact、
   verifier 和 replay 用户路径，而不是新增孤立页面。
4. 依据真实后端 response 重整 Resource Library、Knowledge、Run Workbench、Analysis
   和 Community 的信息架构与空/错误/配置状态。
5. 完成 Community 分享对象的实际发布/导入 pipeline，再进行公网部署和恢复演练。
6. 每一项完成后更新本文、`PROJECT_DESIGN.md` 的状态段和相关 ADR，提交并重启受影响服务。

## 6. 当前验收记录

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

## 7. 技术决策日志

- 保留 `PROJECT_DESIGN.md` 作为产品和工程权威；本文只维护事实状态和执行证据。
- Local desktop 与 Community server 保持独立部署；Community 不执行下载的 Agent 或插件。
- Agent 与 Workflow 是平级 Project 资源；Workflow 只调用固定 immutable Agent version。
- Catalog 与 Project Resource Library 分离；MCP 是 Tool discovery 记录，不是独立产品层。
- Project 文件是用户可检查的 source；运行、聊天、账号、秘密和缓存留在应用数据区。
- 先补闭环和可验收证据，再做视觉扩展、推荐算法或资源数量扩张。
