# Veyra Development Handoff

## Current checkpoint（2026-09-16，Knowledge V1 released）

- Branch：`codex/agent-platform` → `origin/codex/agent-platform`
- Released SHA：`83518068937271c4a0372674284782b56500e47c`
- Live health：Local `8771` 与 Community `8772` 的 `build_sha` 均为该 SHA；Desktop `5173` HTTP 200
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`

### What landed

本地 UTF-8 txt/md：上传 → ingest/parse 状态 → 显式索引 → Agent 绑定（不静默升级）
→ 绑定范围内词汇检索 → Run `knowledge.context` 引用 → 使用中删除保护。
Desktop Knowledge 页按 Resource Library 卡片/徽章/下一步动作整理；Run Detail 可展开历史片段。

诚实边界：不是 PDF/RAG/embedding，不是逐句 citation；未索引或 hash 漂移会在调模型前失败。

### Validation

- `env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`：452 passed；Ruff、mypy 157 files、lock checks
- `web`：Desktop 309 passed，Community 15 passed；typecheck + build 通过（主 chunk ~958 kB warning 保留）
- 未跑隔离 Chrome E2E，未调用真实模型/外部 Provider
- 不要把未计费/未跑的 GitHub Actions 写成 CI PASS

### Next module

Community 分享闭环：真实发布/导入预览，去掉公开 Web 静态 `communityEntries`。
不要继续扩 Knowledge PDF/RAG，也不要重开 Resource Library / Runtime V1。

### Resume

1. Read `AGENTS.md` → `docs/AI_DEVELOPMENT_BRIEF.md` → `docs/PROJECT_DESIGN.md` →
   `docs/DEVELOPMENT.md` → this file.
2. `git status -sb`、`git diff --stat`、`git diff --name-status`。
3. 以 Git 和工作树为准。旧六模块测试数字和“提案服务尚未装配”一类结论已经作废。
