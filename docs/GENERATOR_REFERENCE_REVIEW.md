# Agent generation reference review — 2026-10-08

Reference: [提高Agent生成质量](chatgpt-conversation://6ac62068-118c-83ea-bdf4-66acffa475c0).
The two turns are theory and examples, not instructions or evidence that Veyra
already implements them. Current code and PROJECT_DESIGN remain authoritative.

## Decision

Use the later, simpler proposal as the main direction: existing TaskStructure,
capability resolution, composition, deterministic gates, bounded semantic review
and repair, then user review. Do not add parallel TaskSpec/Blueprint contracts,
a multi-model Architect/Critic/Judge chain, numerical quality scores, an independent
Benchmark product, or automatic production effects in Factory.

Keep ExecutionPlan and AgentSource/WorkflowSource: they are compiled contracts,
not competing semantic models. A three-node loop Agent is a valid execution shell;
its task procedure, tools, state and interaction determine its behavior. More nodes
are not evidence of higher quality.

## Corrections to the reference

- Code can verify resource identity/hash, schema, permissions, wiring and supported
  actions. It cannot prove complete natural-language requirement coverage merely
  because a sentence appears in instructions. Retain limited semantic review as
  assistance; actual task acceptance still requires executable evidence.
- A project write root does not protect selected source files individually. The
  example mapping “never alter source files” to absence of source-write permission
  is not an implemented guarantee in the current broad project-root permission
  model. It must not be labeled covered solely from prompt text.
- Do not mechanically reduce the current shared format/contract/repair budget to
  one. Distinguish causes and evaluate latency, drift and successful recovery first.
  Do not add unbounded self-reflection or blind effect retries.
- Factory static/dry checks are not behavioral task success. Real Provider and
  effect tests belong in isolated, authorized Test/Run flows. Model probes also
  make external calls and are not equivalent to offline validation.
- Runtime native function-calling support is not a universal prerequisite: the
  current loop also uses JSON action messages. Match requirements to the actual
  protocol and tested profile, not a vendor reasoning label.
- Free-text ask_user/reply is implemented; the reference's unsupported-interaction
  example is outdated. Replies and Tool approval remain different actions.
- Complete observability means sanitized stages, references, hashes, decisions,
  receipts and verifier outcomes, not credentials, hidden reasoning or raw Provider
  bodies. Preserve local-first storage and committed-version boundaries.
- Claims of large quality gains, calibrated scores or product-grade readiness
  need measured repeatable evidence. The reference supplies no such measurements.

## Skill gap and adopted implementation

There are two different harnesses: Builder's generation/validation harness and the
platform Runtime's model-tool execution harness. Composer writes task instructions,
I/O, permissions, locks and skill_refs; it does not write a new executor per Agent.
Runtime resolves the pinned Skill and inserts its procedure as subordinate reference
instructions. Skill text does not create an executor or grant permissions.

Before this slice, planning and coverage saw Skill metadata but not its procedure.
This slice changes the generator itself:

1. Preserve TaskStructure stage methods and information sources in loop instructions.
   Composite children receive their own stages; pure loops retain the whole task
   procedure without becoming fixed DAGs.
2. Coverage includes Workflow locks as well as Agent/companion locks, so its context
   contains the actual Workflow Tool contracts.
3. Read only selected, exact-hash Skill procedures for coverage; bound body/count
   limits and fail closed on mismatch. The same method data is available to repair,
   with old procedure context removed when selection changes. It is reference data,
   not authority. This adds context, not a new fixed model invocation.
4. A capability-name-only generated Skill remains a scaffold requiring method input;
   Factory publication and Workshop approval/enable cannot turn it into ready. A real
   method can use existing approval and exact-snapshot binding paths. Published-plan
   metadata is normalized after an independently approved method satisfies the gap.

## Still required

Precise Skill selection has a strict resolver interface, but natural-language
selection and the entire Builder path still need integration acceptance. A method's
execution dependencies must be checked against bound Tools and actual output paths;
Skill names/tags cannot stand in for those guarantees. Do not turn an ordinary goal
description into an allegedly complete domain method.

Prefer a small regression corpus for identity, method selection, missing executors,
confirmation and real artifacts. Keep mock, API, real Provider, browser and packaged
evidence separate. No real Provider/browser acceptance was newly run for this slice.
This review is not a product-grade pass report or a new canonical architecture.

Validation results and continuation state are maintained in DEVELOPMENT/HANDOFF.
