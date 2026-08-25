# Veyra Agent Platform contributor contract

Read `docs/PROJECT_DESIGN.md` before changing product behavior.

## Repository boundaries

- `backend/src/veyra_agent_platform/local/` owns local desktop APIs and runtime.
- `backend/src/veyra_agent_platform/community/` owns the public account and registry service.
- `backend/src/veyra_agent_platform/contracts/` owns shared schemas only.
- `web/apps/desktop/` and `web/apps/community/` are separate applications.
- `web/packages/` contains reusable UI and generated contract clients.
- Tests mirror the production subsystem under `tests/`.

Do not create catch-all `utils.py`, `services.py`, `helpers.ts`, or giant entrypoints.
Composition roots contain wiring only. Shared contracts, dependency locks, and
migration heads have one designated writer at a time.

## Safety and evidence

- Never commit secrets, user data, runtime state, credentials, or copied legacy state.
- Never add the legacy repository or its environment to `PYTHONPATH` or package paths.
- Every external effect has an authorization decision, receipt, and verifier outcome.
- Worker tasks commit only their owned scope and report tests plus the commit SHA.
- Do not claim a feature complete without executable evidence from the exact revision.

