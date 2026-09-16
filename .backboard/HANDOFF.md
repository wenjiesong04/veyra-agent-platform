# Veyra Development Handoff

## Current checkpoint（2026-09-16，Knowledge V1 close-out）

- HEAD at session start: `ee814e2`（Resource Library V1 released）。
- 本轮收口 Knowledge V1：ingest / index / retrieval / evidence / remove protection，
  以及按 Desktop 资源库风格整理的知识工作台。
- 用户授权：验收通过后 commit/push 到 `codex/agent-platform`。
- 不处理 `.backboard/sessions`、`.backboard/settings.json`、`.env`。

### Validation actually run this session

- `env -u MOONSHOT_API_KEY -u GITHUB_TOKEN make check`：**452 passed**；
  Ruff format/check、mypy 157 files、dependency/lock checks passed。
  首次沙箱跑 plugin registry 因无法写入 Application Support 失败；非沙箱复跑通过。
- `web`: Desktop **309 passed**，Community **15 passed**；
  `npm run typecheck` 与 `npm run build` 通过。Desktop 主 chunk 约 958 kB warning 保留。
- 未跑隔离 Chrome E2E，未调用真实模型/外部 Provider。

### Working tree intended for this commit

后端：Knowledge ingest/index、Project routes、Library ownership/context、Runtime query hash。
前端：Knowledge 工作台、Run Knowledge evidence、contracts/client。
测试：knowledge ingest/index/retrieval/remove/bindings/evidence 及 Desktop 对应测试。
文档：`docs/DEVELOPMENT.md`、本文件。

不要 `git add .backboard/`。只提交已跟踪的 `HANDOFF.md`（若纳入文档收口）。

### Next module after this release

Community 分享闭环：真实发布/导入预览，去掉公开 Web 静态 `communityEntries`。
不要继续扩 Knowledge PDF/RAG，也不要重开 Resource Library / Runtime V1。

### Resume if push is interrupted

1. Read `AGENTS.md` → `docs/AI_DEVELOPMENT_BRIEF.md` → `docs/PROJECT_DESIGN.md` →
   `docs/DEVELOPMENT.md` → this file.
2. `git status -sb`、`git diff --stat`、`git diff --name-status`。
3. 以 Git 和工作树为准，不沿用旧六模块测试数字或“提案服务尚未装配”一类历史结论。
