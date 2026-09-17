# Veyra Development Handoff

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

### 未来边界（都不是 Knowledge V1 blocker）

embeddings、vector search、reranker、GraphRAG、PDF/OCR、web ingestion、
historical Knowledge artifacts、sentence-level attribution。不要为“更完整”扩这些能力。

### Next major module

**Builder Phase 2 / Build loop integration。**

其后仍是 Community 分享闭环（真实发布/导入预览，去掉公开 Web 静态 `communityEntries`）。
不要重开 Resource Library / Runtime V1 / Knowledge V1。

### Resume

1. Read `AGENTS.md` → `docs/AI_DEVELOPMENT_BRIEF.md` → `docs/PROJECT_DESIGN.md` →
   `docs/DEVELOPMENT.md` → this file.
2. `git status -sb`、`git diff --stat`、`git diff --name-status`。
3. 以 Git 和工作树为准。历史测试数字和旧的“未完成”结论都需按当前修订重核。
