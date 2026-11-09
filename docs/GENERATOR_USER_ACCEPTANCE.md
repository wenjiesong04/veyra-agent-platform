# Generator user acceptance — 2026-10-05

Implementation gates precede these live cases. This document is not a pass report.
Use isolated Projects and synthetic or explicitly supplied inputs. Keep Provider,
API harness, browser, filesystem receipts and product-quality evidence distinct.
Do not modify existing acceptance Projects or publish/send external communications.

## Case 1: A proposal that must wait for the user

Prompt: 我想做一个小店陈列方案助手。每次先问我店铺面积、商品和预算，
给出三个有明显差异的方案及成本说明，让我选择。没有选择前不要出最终方案。
我可以补充或修改要求，它要接着当前任务调整，确认后才给出最终执行清单。

Acceptance: real questions and usable choices; same pinned Run resumes after reply;
no final result or billed image before choice; the chosen option and changes affect
final output; refresh can restore the waiting task; no meaningless node-only claim.

## Case 2: Reconciliation with controlled file effects

Prompt: 我想做一个小店对账助手。读取我选定的订单和付款CSV，按订单号核对，
识别漏付、重复付款和金额不符，列出原始行号和差额。不要擅自改原文件。
只有我确认后才能把结果写成报告，并给我可打开的文件和执行记录。

Acceptance: input selections make sense to a novice; findings match seeded truth;
actual file/Tool contract is used; no write before approval; one receipt per effect;
output file opens and preserves source records; denied approval leaves files intact.

## Case 3: A project task with retained state

Prompt: 我想管理一个小团队的周计划。保存每项任务的负责人、截止时间和状态。
下次我说某项已完成或改了日期时，要更新同一项，不要新增重复任务。
生成周总结前让我确认，保留修改记录。找不到任务或者信息冲突时先问我。

Acceptance: real identity/revision state rather than chat-only promises; update uses
existing task; missing capability or unsupported query is disclosed; no false
completion; user can find the resulting state and understand the next action.

## Required evidence per live case

Record prompt, goal, candidate duties/I/O/resources, setup gaps, decisions, exact
committed versions, expected and actual result, native receipts, usability issues,
fix and retest. A generated source, a passing semantic audit, or mock results alone
cannot establish product-grade readiness. Do not hide unsupported cases by choosing
only basic writing/translation prompts.

## Live findings and current status

Case 1 completed through the browser and a real configured Provider: one committed
Agent v1 and one Run collected 40 square metres, candle/gift merchandise and a
6000 RMB budget; offered three options; waited for selection; accepted option C and
a revised 5000 RMB budget; waited again; restored the waiting task after browser
refresh; and returned a final checklist only after explicit confirmation. Final
cost items sum to 5000 and retain the chosen option and access-path requirement.
Runtime status is `unverified`: this is successful execution and manual acceptance,
not a claim of an independent semantic verifier pass.

An initial option incorrectly called a 6000 RMB breakdown 5800 RMB. The new generic
Arithmetic Tool uses bounded exact rational calculation and receipts. Its local
ToolRuntime regressions pass; a fresh real generated Agent using it remains to be
accepted. The original successful Run is not rewritten as if it used that Tool.

Live generation exposed and led to repairs for: conversation context mistaken for
an Entity Tool dependency; blocked generation displayed as successful/running;
missing capability names in planning context; legacy graph specs mixed into loop
planning; incomplete Provider JSON accepted via contract defaults; Runtime registry
capability-source rejected by the desktop parser; giant JSON in historical results;
missing persistent state contracts/type installation; exact-ID-only Entity Read;
underscore Tool parameter names rejected as Agent slugs; and shared Tool execution
scope crossing concurrent Projects. Existing resource hashes remain unchanged;
Entity Query and Arithmetic are new versioned resources.

Case 2 reached semantic planning and repair, but Provider HTTP 429 stopped coverage
review. Case 3 produced an earlier candidate whose persistence implementation was
incomplete; it was not installed. A fresh generation after repairs also received
HTTP 429. Neither case has passed real Runtime acceptance. No repeated background
Provider retries are scheduled. Existing user Projects, failed Runs and image
outputs remain unchanged.

Final gates and remaining product assessment are recorded in DEVELOPMENT and
HANDOFF. Product-grade readiness is not established: complete Cases 2/3 with real
Provider availability, validate the new arithmetic usage, examine repeatability,
and assess concurrent state updates rather than substituting mock results.
