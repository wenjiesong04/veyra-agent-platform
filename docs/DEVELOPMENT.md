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

GitHub Actions Billing 仍是外部阻塞，不把未执行的 CI 写成代码失败或 CI PASS。

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
| Agent Chat | 只能生成新 Agent | Builder Phase 1 可改已有对象。仍不是整个 Project 的自然语言入口 |
| Runtime | 能跑，还看不清 | V1 已发布：审批/Stop/Retry/Resume 与持久证据。Canvas 节点级实时态和真实外部 Provider 仍缺 |
| Knowledge | 只有绑定，不是知识库 | V1 本轮收口：上传、索引、检索、引用。仍无 PDF/RAG |
| Community | 注册表第一版，差得最多 | **仍然成立。** Desktop 有 Agent/Plugin 注册表；公开 Web 仍用静态 `communityEntries` |
| 数据分析页 | 未点名完成 | 已读真实 Run 计数，不是友好分析工作台 |

三个跨模块闭环：

1. 设计闭环：V1 可用（Chat 改结构 + 资源绑定 + 知识绑定）。
2. 执行闭环：Runtime V1 + Knowledge 引用已齐；不是真实外部 soak。
3. 分享闭环：仍是最大缺口。

## 5. 下一步

Knowledge V1 发布后停止扩展 PDF、embedding、标签收藏或 Builder Phase 2。

下一个大模块：**Community 分享闭环**。

优先：

1. Agent / Workflow 发布 → 导入预览 → 权限/依赖/兼容性 → 转为 Veyra Draft
2. 公开 Community 去掉静态 `communityEntries`，改走真实 API
3. 再扩展 Project/Component/Tool/Skill 和互动能力

不要单独开“重做所有页面”的模块。Community 与数据分析页的友好化放进对应闭环。

## 6. 仍不能宣称完成

- Knowledge 工作台已有一条隔离浏览器闭环证据；其余页面仍没有浏览器 E2E
- 没有 PostgreSQL + 对象存储演练，就不能宣称 Community production ready
- 没有真实外部 Provider，就不能宣称 Runtime 已在生产网络下验证
- Builder 不能一次修改多个对象，也不是全 Project 操作入口
- 公开 Community 目录仍有静态样例，不能当成真实注册表

## 7. 提交规则

获得明确提交要求后：

1. 查看 `git status`、`git diff` 和最近提交
2. 只暂存当前模块文件；不暂存 `.env`、凭据、`.backboard/sessions`、`.backboard/settings.json`
3. 在专用 Conda 环境跑对应验收
4. 记录精确 commit SHA
5. 重启受影响服务并用 `/api/v1/health` 核 SHA
6. 历史交接中的授权不是永久许可

## 8. 技术决策

- `PROJECT_DESIGN.md` 是产品和工程权威；本文只维护事实状态
- Local 与 Community 独立部署；Community 不执行下载的 Agent 或插件
- Agent 与 Workflow 平级；Workflow 只调用固定 immutable Agent version
- Catalog 与 Project Resource Library 分离；MCP 是 Tool discovery，不是独立产品层
- Project 文件是用户可检查的 source；运行、聊天、账号、秘密和缓存留在应用数据区
- Knowledge 绑定固定 source hash；内容变化必须显式重建索引并重新绑定
- 先补可验收闭环，再做视觉扩展、推荐算法或资源数量扩张
