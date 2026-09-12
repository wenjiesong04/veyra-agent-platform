# Veyra Agent Platform — Canonical Development Design

> Status: **ONLY CURRENT PRODUCT AND ENGINEERING AUTHORITY**
> Revision: 1.4
> Date: 2026-09-09
> Repository: `/Users/spectre/PycharmProjects/veyra-agent-platform`
> Development branch: `codex/agent-platform`
> Legacy source: `/Users/spectre/PycharmProjects/veyra @ 1ffb4cdd45c798556390c20e53fc2d265cd56471`
> Implementation status: W0 environment, contracts, dual web shells, and CI baseline implemented; V1 product services remain in development

This document starts from a new, independent project. It does not assume that the old Veyra repository will be cleaned, merged, or used as a runtime dependency. The old repository is read-only migration evidence. Every extracted behavior must be re-namespaced, simplified, tested, and recorded in this document or a later migration ledger.

---

## 0. Executive Decision

Veyra Agent Platform will be a local-first desktop product with six connected surfaces:

1. **Veyra Studio** — generate or manually design an Agent using Form, Canvas, and Source views.
2. **Veyra Runtime** — run an Agent locally with tools, state, approvals, checkpoints, cancellation, and verification.
3. **Veyra Orchestrator** — a deterministic scheduler for tasks, dependencies, isolated workspaces, retries, and multiple Agent runs.
4. **Veyra Monitor** — live workflow visualization, run timelines, evidence, failures, and human controls.
5. **Veyra Library** — manage Agent files, Component files, packages, versions, imports, exports, and artifacts.
6. **Veyra Community** — required V1 accounts and a remote registry for publishing, downloading, Forking, starring, and reviewing Agent versions and templates.

Veyra's own Factory Agent uses the configurable Kimi Open Platform provider.
The client discovers `/v1/models` and currently defaults to **kimi-k3**.
Generated Agents remain provider-neutral and may use Kimi or another configured
model.

Core product loop:

```text
Describe requirement
→ configured Kimi model generates typed AgentBlueprint Draft
→ server compiles Agent Definition
→ user edits Form / Canvas / Source
→ validate schema, graph, components, permissions, secrets and verifier
→ save immutable version
→ run locally
→ Run Canvas shows every node and event
→ user can stop / approve / reject / resume
→ verifier establishes result status
→ export, Fork or publish a version
```

Product promise:

> **Describe it. Design it. Run it. Share it.**

Chinese promise:

> **描述你的需求，得到一个真正属于你的 Agent；看见它如何工作，并把可靠版本分享给别人。**

---

## 1. Confirmed Development Environment

### 1.1 Legacy environment snapshot

The old Veyra project currently uses:

| Layer | Confirmed environment |
|---|---|
| OS | macOS 26.6.2, Apple Silicon arm64 |
| Python | 3.11.15, Conda env `/opt/anaconda3/envs/veyra` |
| Backend | FastAPI 0.136.1, Uvicorn 0.46.0 |
| Validation | Pydantic 2.13.2 |
| HTTP | httpx 0.28.1 |
| Streaming | websockets 15.0.1 plus HTTP SSE endpoints |
| Security | cryptography 48.0.0, certifi 2025.1.31 |
| Legacy integration | lark-oapi 1.6.7 |
| Persistence | custom JSON/JSONL `WorldStateStore`; no SQLite/SQLAlchemy/Alembic |
| Frontend | React 19.2.6, React DOM 19.2.6 |
| Build | TypeScript 5.9.3, Vite 7.3.3, plugin-react 5.2.0 |
| Icons | lucide-react 0.555.0 |
| Styling | hand-written CSS; no Tailwind/component framework |
| Node | 24.16.0 |
| npm | 11.13.0 |
| Desktop | Tauri 2.11.4, Rust 1.96.1, PyInstaller 6.22.0 |
| Desktop process | React SPA + packaged Python/FastAPI sidecar on loopback |
| Tests | custom Python smoke scripts and Node contract scripts; no pytest/Vitest/Playwright baseline |

Rust is installed under `/Users/spectre/.cargo/bin` but is not currently on the default shell `PATH`. Desktop scripts must add this path explicitly or document shell initialization.

### 1.2 Suitability verdict

| Technology | Keep? | Verdict and adjustment |
|---|---|---|
| Python 3.11.15 | Yes | Stable with FastAPI and existing desktop packaging; create a fresh environment instead of reusing old packages |
| FastAPI | Yes | Well suited to local API, SSE, typed OpenAPI, and a future separate Community API |
| Pydantic 2 | Yes | Use for every Agent/Component/API contract and schema version |
| React 19 | Yes | Suitable for Studio, Run Canvas, Monitor, Community, and desktop SPA |
| TypeScript 5.9 | Yes | Keep strict mode; generate types from backend contracts where practical |
| Vite 7 | Yes | Fast local/desktop builds; keep separate web and desktop configs only if needed |
| Hand-written CSS | Partly | Reuse visual tokens and shell style, not old product selectors/pages; introduce a small UI layer |
| Lucide | Yes | Continue for product icons |
| SQLite | Add | Best local persistence choice; replace JSON/JSONL state with migrations and repositories |
| SQLAlchemy/Alembic | Add | Needed for maintainable SQLite schema and later server migration |
| httpx/OpenAI-compatible transport | Yes | Rebuild as a focused Kimi/provider client with streaming and structured output |
| websockets | Optional | Prefer replayable SSE plus POST commands; use WebSocket only where bidirectional streaming materially helps |
| Tauri 2 | Yes, later | Existing process model is appropriate; integrate after backend/frontend kernel is stable |
| PyInstaller 6 | Yes, later | Proven sidecar packaging; build from the new isolated environment and lock |
| Rust 1.96 | Yes | Add `$HOME/.cargo/bin` to documented build environment |
| WorldStateStore JSON/JSONL | No | Replace with SQLite WAL and content-addressed objects |
| lark-oapi/Feishu | No | Not part of the new product |
| Custom smoke-script gate | No | Replace with pytest, frontend tests, E2E, security, and explicit live lanes |

Overall verdict:

> **The original language/runtime stack is suitable and should be retained. The original persistence, dependency environment, domain modules, test organization, and product pages are not suitable and must be replaced.**

### 1.3 New environment decision

Keep the proven major versions, but do not reuse the old environment packages.

```text
Python family       3.11.15
Python environment  dedicated Conda env `veyra-agent-platform`
Frontend            React 19 + TypeScript 5.9 + Vite 7
Backend             FastAPI + Pydantic
Database            SQLite WAL locally
Desktop             Tauri 2 + PyInstaller sidecar after kernel stability
```

The new isolated environment is created from `environment.yml` at:

```text
/opt/anaconda3/envs/veyra-agent-platform
```

It uses Python 3.11.15 with its own `sys.prefix` and site-packages. The old `veyra` Conda environment remains only for reproducing the legacy repository.

### 1.4 New Python dependencies

Runtime dependencies:

- FastAPI
- Uvicorn
- Pydantic and pydantic-settings
- SQLAlchemy 2
- Alembic
- aiosqlite
- httpx
- OpenAI SDK for Kimi/OpenAI-compatible transport, unless a single httpx transport is deliberately selected
- PyYAML safe loader
- platformdirs
- keyring
- cryptography
- python-multipart

Development dependencies:

- pytest
- pytest-asyncio
- pytest-cov
- respx or equivalent HTTP mock
- Ruff
- mypy or pyright; this project initially selects mypy

Desktop build dependencies:

- PyInstaller 6.x
- Tauri CLI 2.x
- Rust stable toolchain

Do not migrate `lark-oapi`, Weather, Calendar, Feishu, Living Context, Belief, Attention, Commitment, or old Project Guardian dependencies.

### 1.5 Environment isolation requirements

- `sys.executable` must point inside `/opt/anaconda3/envs/veyra-agent-platform`.
- `sys.prefix` must not equal `/opt/anaconda3/envs/veyra`.
- No `PYTHONPATH` entry may point at the old repository.
- No `.pth` or editable install may expose old packages.
- CI installs the new project from an empty environment.
- Tests use temporary SQLite databases and temporary object roots.
- New runtime state must never fall back to old `state/` or `agency/` directories.
- Desktop packaging must install from the new lock/dependency definition, not developer machine site-packages.

### 1.6 SQLite decision

SQLite is the correct local database because the packaged desktop app is single-user and local-first.

Use:

- WAL mode
- foreign keys
- migration version table
- short transactions
- one application writer
- `busy_timeout`
- content-addressed files outside the database
- backup before migration

The public Community V1 uses a separate PostgreSQL deployment. The local desktop database remains SQLite permanently.

---

## 2. Product Positioning and User Need

### 2.1 What the user owns

An Agent is represented by a portable, inspectable source definition:

```text
*.vagent.yaml
```

The file contains behavior, components, tools, inputs, outputs, permissions, approval points, state schema, verification rules, UI metadata, and dependency locks.

The file does not contain:

- secret values
- OAuth tokens
- user project files
- conversation history
- transient run state
- unbounded arbitrary code

### 2.2 Why users need Veyra

Users should choose Veyra when they need to:

1. Own an Agent as source instead of hidden workspace database state.
2. Generate an Agent quickly but still inspect and modify its actual structure.
3. Keep Agent definitions in Git and review semantic changes.
4. Run locally without uploading project data or secrets.
5. See which node is running, blocked, waiting, failed, or verified.
6. Stop, approve, reject, steer, reply, or resume from one interface.
7. Organize several Agent tasks and isolated workspaces with a deterministic orchestrator.
8. Share a version with explicit permissions, dependencies, provenance, and compatibility.
9. Fork an Agent or Component while retaining exact lineage.

### 2.3 Target users

Primary V1 users:

- people who want to create an Agent without writing code
- Agent developers and power users
- small AI-native teams
- creators who want to publish a runnable Agent, not only a prompt

Not initial requirements:

- multi-region cloud execution
- hundreds of SaaS connectors on day one
- cloud execution of downloaded Agents

### 2.4 Product combination

Veyra's intended combination is:

> **Project-owned Agent files + deterministic Canvas round-trip + Kimi-assisted generation + governed local Runtime + node-level run evidence + deterministic orchestration + a version-aware community.**

That combination is the product. No single individual feature is the moat.

---

## 3. Product Scope

### 3.1 Product modules

#### Veyra Studio

- Prompt generation panel
- Form editor
- visual Canvas editor
- source editor
- node inspector
- permission preview
- semantic diff
- validation diagnostics
- save version, run, import, export

#### Veyra Runtime

- graph executor
- model adapters
- tool/component registry
- MCP
- state and checkpoints
- human approvals
- secret broker
- cancellation and recovery
- verification and evidence

#### Veyra Orchestrator

- projects and work items
- dependencies
- Agent version binding
- isolated workspaces/worktrees
- concurrency and leases
- retries and stall detection
- human input and verification gates

#### Veyra Monitor

- active runs
- Run Canvas
- Orchestrator Canvas
- timelines
- approvals
- errors and stale runs
- workspace/branch identity
- stop/steer/reply/resume/retry controls

#### Veyra Library

- Agents and Workflows as first-class Project resources
- Knowledge documents and metadata
- Files / Assets as raw file storage
- immutable versions, imports/exports, packages
- run artifacts, trash/restore
- Resource Catalog keeps an independent global list + detail at `#/resources`.
  The Project Resource Library at `#/projects/:projectId/resources` shows
  selected, locked, and source-referenced Project dependencies. The
  Agent/Workflow palette is a projection of Project resources plus built-in
  primitives, not a replacement for either page.

#### Veyra Community

- Marketplace for sharing and downloading versioned resources
- email-verified account and public creator profile
- Agent and template publishing
- immutable versions
- download/import
- Fork lineage
- Star
- version-bound Review
- Report and moderation
- compatibility and risk information

### 3.2 Phase boundaries

The desktop shell requires a Community session. Unauthenticated routes,
including pasted Studio links, resolve to `#/login` and never render Project
workspace chrome. Local Project files remain machine-scoped; login does not
partition them by account.

Community does not execute downloaded Agents on the server. Users explicitly import and run them locally.

Cloud Runtime, billing, organizations, branch/merge collaboration, recommendation algorithms, and arbitrary code components are later work.

---

## 4. System Architecture

```text
Tauri Desktop Host
  ├─ React SPA
  ├─ Python/FastAPI sidecar
  └─ isolated per-run executor processes

React
  ↕ loopback HTTP + replayable SSE + POST commands

FastAPI
  ├─ Agent Definition compiler
  ├─ Kimi Factory client
  ├─ Studio services
  ├─ Runtime coordinator
  ├─ deterministic orchestrator
  ├─ Tool/approval/secret proxy
  ├─ verifier and evidence
  ├─ SQLite repositories
  ├─ content-addressed object store
  └─ Community API client

Optional Community Server
  ├─ account/auth API
  ├─ registry API
  ├─ upload validation worker
  ├─ closed alpha SQLite / public PostgreSQL
  └─ object storage
```

### 4.1 Process rules

- Local FastAPI listens only on loopback or Unix socket.
- It generates a random local bearer token and checks Origin.
- React never accesses SQLite directly.
- Executor processes never write SQLite directly; they emit IPC events to the coordinator.
- LocalStorage contains only theme/layout preferences, not product truth.
- Community is a separate service; never expose the desktop sidecar to the public internet.

---

## 5. Project, Agent, and Component Formats

### 5.0 Project directory

A Project is a user-owned directory and the primary Studio, Library, Runtime,
and Orchestrator scope. It is a container, not an editor. The on-disk layout
keeps each resource kind in its own folder:

```text
<Project>/
  project.vproject.yaml
  agents/<slug>/
    resource.yaml
    agent.vagent.yaml
  workflows/<slug>/
    resource.yaml
    workflow.vworkflow.yaml
  components/primitive/<slug>/
  components/composite/<slug>/
  knowledge/<slug>/
  assets/<slug>/
  tests/
```

Project Catalog dependencies are declared in `project.vproject.yaml` under
`resources`. These bindings select immutable Catalog references and content
hashes for the Project; Agent and Workflow source locks remain the usage-level
proof. Built-in primitive Components are always available and do not need a
Project binding. Optional Tools, MCP descriptors, Skills, Policies, Templates,
and Composite Components do.

Components remain a storage and catalog kind with required `primitive` or
`composite` class. The global Resource Catalog (`#/resources`) provides list +
detail for description, version, examples, and references. The Project Resource
Library binds optional Catalog versions for the current Project. The
Agent/Workflow Canvas palette is a filtered projection of Project bindings plus
built-in primitives. Composite packages expand to locked
primitive nodes when dropped on a Canvas. Components are not a flowchart
and are not renamed into a ninth Flow type.

The Project Resource Library reports `current`, `stale`, `unbound`, or `builtin`
for each projected resource. A `stale` binding means the same catalog reference
now has different content than the Project hash; Studio and Agent Runtime
preflight surface that drift for explicit re-binding rather than silently
accepting a changed capability.

The Agent Chat surface uses the same local Runtime preflight as Studio and can
offer indexed Project file paths for explicitly declared path-like inputs. A
suggestion only fills a relative path value; it does not turn the Files page
into implicit model context or bypass the Agent's Filesystem Tool permission.

The manifest contains a stable UUIDv7 `project_id`, Project name, listed Agent
UUIDs/slugs/paths, `default_agent_id`, resource policy, and schema version.
Run state, account tokens, secrets, caches, and event history never enter the
Project directory.

Desktop-created V1 Projects are allocated automatically under the Veyra
application-data `v1/projects/` root. That root is resolved from the host
application-data directory at runtime, never a hardcoded user path, so each
install (and a later packaged app or server) gets its own location. The local
index stores a storage-root-relative folder name that matches the unique
display name (for example `dddd/` or `New project(1)/`). Project creation asks
only for the name and optional description; it never asks the user to choose
or type a storage path. Opening an existing folder indexes that directory in
place and does not copy it into managed storage. Native folder and archive
pickers use the host file dialog's default location; they do not jump into
the managed application-data root.

`project_id` is the stable identity; the name is a unique active-workspace
label assigned by the local service. An empty name becomes `New project`, and
collisions use the first free suffix such as `New project(1)`. The on-disk
folder uses that same unique name after stripping characters that filesystems
reject. At most one active Project is pinned. Removing a managed Project moves
it to Veyra Trash. Removing an externally indexed Project unlinks it from the
workspace and leaves the original folder on disk. Desktop shows **查看项目位置**
and reveals the indexed folder in Finder. Portable `.vproject.zip` export
remains a local API for later web or sharing flows; it is not a Desktop
sidebar action.

The native pickers must not surface raw sidecar exceptions such as
`native directory picker failed`. Desktop maps `directory_picker_failed` and
`directory_picker_unsupported` to language-specific recovery text.

V1 permits an empty Project: `agents` may be empty and then
`default_agent_id` is `null`. When Agents exist, `default_agent_id` identifies
one listed Agent. Agents remain flat at `agents/<slug>`; an optional
`parent_agent_id` on a manifest entry creates a child-Agent relationship without
coupling the filesystem path to the hierarchy. Parent references must identify
another listed Agent and must not contain cycles.

### 5.1 Source and package files

```text
Agent source       *.vagent.yaml
Agent package      *.vagent
Component source   *.vcomponent.yaml (platform-owned in V1)
Component package  *.vcomponent (publishing deferred)
```

Source is human-readable and Git-friendly. Package is an immutable archive containing canonical source, lock data, documentation, icons, test fixtures, and signatures.

### 5.1.1 Node definition files

The platform-owned node catalog is checked in as packages under
`resources/nodes/<family>/<id>/node.yaml`. Each package is a versioned
record for a Component, Tool, MCP descriptor, Skill, Policy, or Template.
The local Resource Catalog loads every `node.yaml`, validates family/kind
alignment, and computes the immutable content hash. Studio palette fields
live under `spec.ui` and do not participate in the lock hash. Factory may
assemble only catalogued records. A special node produced for an unusual
requirement is a declarative, non-executable proposal until a separate
human-reviewed adapter promotion flow exists.

### 5.2 Standards strategy

Use portable Agent/Flow/Tool semantics with a versioned Veyra profile for:

- permissions
- secret references
- state/checkpoints
- UI layout
- verification
- evals
- dependency lock
- lineage
- runtime compatibility

Published versions expose a versioned discovery and provenance record.

### 5.3 Agent source example

```yaml
schema_version: "1.0"
agentspec_version: "26.1"
component_type: Flow

agent_id: 01a03795-a5b0-7234-ba76-5c5f0e029334
slug: github-bug-triage
name: GitHub Bug Triage
description: Analyze new bug reports and prepare a verified response.

inputs:
  repository:
    type: string
    required: true

nodes:
  - id: start
    component_type: Start

  - id: read_issues
    component_type: Tool
    uses: veyra.github.issue_search@1.0.0

  - id: analyze
    component_type: Model
    model_ref: model.primary
    system_prompt: Analyze the issue and identify missing evidence.

  - id: approval
    component_type: HumanApproval
    prompt: Publish this response?

  - id: publish
    component_type: Tool
    uses: veyra.github.issue_comment@1.0.0

  - id: verify
    component_type: Verifier
    checks:
      - github.comment.exists

  - id: output
    component_type: Output

transitions:
  - [start, read_issues]
  - [read_issues, analyze]
  - [analyze, approval]
  - [approval.proceed, publish]
  - [publish, verify]
  - [verify.passed, output]

extensions:
  veyra:
    runtime_profile: veyra-runtime-profile/1
    secret_refs:
      - github.main
    permissions:
      network_hosts: [api.github.com]
      tools: [github.issue_search, github.issue_comment]
    verification:
      required: true
```

### 5.4 Components: primitive vs composite

Components are one resource kind with two required classes. They must not
collapse into a single palette bag.

**Primitive** — platform-owned graph node types. These are the only nodes a
Canvas may persist. V1 primitives:

- Start, Model, Tool, HumanApproval, Verifier, Output
  (Agent canvas palette)
- Condition, Transform (Workflow control flow; historical Agent graphs may still persist them)
- AgentCall (Workflow canvas only; references `agent_id@version_id`, both UUIDv7, never a path)

A primitive cannot be authored in a Project overlay, Factory output, or
workshop draft. The legacy node name `Agent` is accepted only as an alias for
`Model` in the UI. Historical `Agent` wire identities and omitted version
fields remain unchanged when reading and serializing old definitions.

**Composite** — a versioned assembly of primitive (and acyclic nested composite)
references. It is a reusable Component package, not a ninth Flow type. Dropping
one onto a Canvas expands to locked primitive nodes. Composites live under
`components/composite/<slug>/` and are referenced by ID + version.

Later primitives: Loop, Parallel, Schedule/Webhook. CustomFunction is not a
primitive; it is a workshop proposal until promoted.

### 5.5 Tools

Initial tools:

- filesystem.read — current Runtime adapter, Project workspace only
- filesystem.list — current Runtime adapter, bounded Project directory listing
- filesystem.search — current Runtime adapter, bounded UTF-8 Project search
- filesystem.write — current Runtime adapter, HumanApproval by default, Project workspace only
- shell.exec — current Runtime adapter, workspace working directory and HumanApproval by default
- http.request — current Runtime adapter, explicit per-node host allowlist and HumanApproval
- github.read — current Runtime adapter, host `GITHUB_TOKEN` secret and read-only API paths
- github.write — current Runtime adapter, host `GITHUB_TOKEN` secret and HumanApproval by default
- mcp.call
- browser read/navigation after the core Runtime is stable

Tool nodes may map external input/output field names to the Agent value space;
the Runtime applies these mappings before authorization and after the adapter
receipt is produced.

Browser, GitHub, OCR, Email, and databases are tools or providers, not separate control-flow component types.

### 5.5.1 Resource Catalog V1

Factory and Studio resolve capabilities only through one server-owned Resource
Catalog. The catalog is not a folder of arbitrary code and it is not populated
from model output. It exposes immutable, versioned descriptors for:

- **Component** — either a **primitive** graph node type (platform-owned fields,
  ports, compiler support, Runtime status) or a **composite** reusable assembly
  of primitive references. The two classes share the Component kind and
  marketplace, but they have different folders, palettes, and compile rules.
- **Tool** — an executable capability with exact version, input/output schema,
  permission requirements, secret references, receipts, and Runtime adapter
  status.
- **MCP server/tool** — a configured discovery source under Tools, not a
  product layer beside Agent, Workflow, Component, or Knowledge. An MCP
  tool must be normalized into a Tool descriptor and lands on the Canvas as
  a Tool node (`uses: resource_id@version`). Connection configuration and
  credentials remain outside Agent source. Server environment bindings may
  point to host environment names or opaque host Keychain references; values
  never enter Project or SQLite. Discovered descriptors are
  review-required, are not Factory-selectable by default, and require approval
  before a Runtime call. Stdio uses newline-delimited JSON-RPC with bounded
  message/timeout/process cleanup. Streamable HTTP uses a configured HTTPS
  endpoint, JSON/SSE responses, protocol/session headers, and host-bound header
  references; a discovered remote Tool records the endpoint host as a required
  Agent network permission. Architecture diagrams must not draw MCP as its own
  resource class.

The Resource Library accepts a standard JSON `mcpServers` object (and the
equivalent `servers` array) as a convenience import. The import normalizes
server names, stdio commands or HTTPS endpoints, arguments, header templates,
and host environment/Keychain references; it rejects plaintext credential
values and writes the validated batch atomically. Importing never discovers or
executes a server automatically.
The wire behavior follows the [MCP Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports).
- **Skill** — a non-executable, versioned instruction/method asset. Factory may
  compile Skill content into an Agent prompt, while the exact Skill reference
  and hash remain in the dependency lock.
- **Policy** — platform/project constraints for models, tools, network, files,
  approvals, budgets, and verification. Policy is an overlay enforced during
  resolution and Runtime authorization, not a free-form Canvas node.
- **Template** — a complete, Forkable Agent definition assembled from catalog
  resources. V1 ships a blank Starter plus three LLM-first work templates:
  document distiller, question researcher, and file-sort planner. They compile
  built-in Skills into the Agent prompt and declare no Tool nodes. The
  researcher does not browse; the file planner does not move files.

Each descriptor declares stable resource ID, kind, version, name/description,
origin, content hash, availability state, Factory selectability, Runtime
support, required permissions, and compatibility. Availability is explicit:
`ready`, `requires_configuration`, `design_only`, `quarantined`, `disabled`, or
`unavailable`. Factory cannot present a resource as runnable when its adapter or
provider is absent.

The first useful catalog contains the primitive graph Components, including
Model and the Workflow-only AgentCall, plus versioned
instruction Skills (research, document analysis, need extraction, evidence
ledger, content planning, file taxonomy) and default Policies, Forkable work
templates, and only Tool/MCP entries backed by real adapters. The UI may display
an unavailable Tool/MCP descriptor, but Factory cannot select it for a runnable
Agent.

If no registered resource satisfies a requirement, Factory returns a typed
`MissingCapabilityProposal`. With explicit user approval, Kimi may produce a
quarantined Resource Draft containing a declarative specification,
input/output schemas, permissions, documentation, test cases, and an adapter
scaffold. It may not register, authorize, install, or execute generated code.
Promotion into the catalog is a separate Resource Workshop flow with human
review, static/security checks, tests, and an immutable version.

### 5.6 Version hashes

Compute:

- `file_hash`: entire source including UI layout and documentation
- `behavior_hash`: execution semantics only
- `lock_hash`: resolved dependencies
- `package_hash`: immutable package bytes

Moving a Canvas node must not change `behavior_hash`. Changing prompt, tool, permission, transition, model, or verifier must change it.

---

## 6. Kimi Factory Agent

### 6.1 Official API baseline

```text
model           kimi-k3 (current configurable default)
base URL        https://api.moonshot.cn/v1
chat endpoint   /v1/chat/completions
models endpoint /v1/models
auth            Authorization: Bearer $MOONSHOT_API_KEY
```

The default base URL is the China Kimi Open Platform endpoint. Override
`VEYRA_FACTORY_MODEL_BASE_URL` to `https://api.moonshot.ai/v1` for the
international site.

Kimi Open Platform supports OpenAI-compatible Chat Completions, Structured
Output, tool calling, streaming, reasoning, and a large context window. The
client validates the configured model through `/v1/models` before generation.

### 6.2 Factory responsibility

Kimi produces a strict `AgentBlueprint` Draft containing:

- goal
- inputs/outputs
- required capabilities
- known component/tool references
- graph nodes and transitions
- approval points
- requested permissions
- verification checks
- UI suggestions

The server then resolves registered components and compiles canonical Agent source.

Kimi cannot:

- publish
- execute the Draft directly
- read secret values
- register unknown tools
- grant permissions
- claim verification
- create arbitrary executable code in V1

Factory receives a bounded snapshot of Resource Catalog descriptors and may
reference only resources in that snapshot. The server, not Kimi, resolves exact
versions, derives permissions/locks, applies Policies, and decides whether the
result is designable or runnable.

### 6.2.1 Factory conversation

Agent creation begins as a Project-scoped multi-turn Factory conversation. It
collects goal, inputs, outputs, environment, available data, desired tools,
risk, approval points, and success criteria before generation. The conversation
has explicit states: `collecting`, `ready`, `generating`, `review`,
`missing_capability`, `completed`, and `abandoned`.

Factory conversation messages and summaries live in the Veyra application data
store. They never enter `project.vproject.yaml` or `agent.vagent.yaml`.
Provider `reasoning_content` is request-chain-only and is not persisted. A
Factory conversation is distinct from the later Agent conversation used to run
an existing Agent and display its durable Run history.

The UI pairs a conversation transcript with a live Resource Plan showing chosen
Components, Tools/MCP, Skills, Policies, permissions, missing capabilities, and
run availability. Generation is enabled only after the server marks the
conversation `ready`.

### 6.3 Generation flow

```text
User requirement
→ bounded Factory conversation
→ server-selected Resource Catalog snapshot
→ Kimi JSON Schema AgentBlueprint
→ schema validation
→ component/tool resolution
→ Skill compilation and Policy application
→ exact resource lock and permission derivation
→ graph validation
→ bounded repair loop, maximum three attempts
→ user-visible Blueprint and Resource Plan
→ user edits and confirms
→ server creates or replaces an Agent Draft
→ immutable version
```

The repair loop receives only validation diagnostics and the same immutable
catalog snapshot. It cannot broaden permissions, replace the catalog, or invent
resource identifiers. After three failed attempts the session becomes a visible
generation failure or `missing_capability`; it never silently falls back to an
unvalidated graph.

### 6.4 Kimi configuration

```text
VEYRA_FACTORY_MODEL_BASE_URL=https://api.moonshot.cn/v1
VEYRA_FACTORY_MODEL_ID=kimi-k3
VEYRA_FACTORY_MODEL_API_KEY_ENV=MOONSHOT_API_KEY
VEYRA_FACTORY_REASONING_EFFORT=high
VEYRA_FACTORY_MAX_COMPLETION_TOKENS=16384
```

The key belongs in the host Keychain/environment, never SQLite, Agent source,
browser storage, logs, or packages. Desktop Settings can bind the model key to
`model.primary`; headless development may continue using `MOONSHOT_API_KEY`.

Blueprint generation uses `response_format.type=json_schema` with the committed
AgentBlueprint JSON Schema. Thinking-model `reasoning_content` may be retained
only inside one in-memory generation/repair request chain when required by the
provider protocol. It is never persisted in Factory messages, SQLite, logs, or
Agent source.

Kimi K3 always uses thinking mode. The client sends only supported
`reasoning_effort` values (`low`, `high`, `max`), omits fixed sampling
parameters, and applies a Veyra-owned completion-token bound rather than the
provider's very large default. Structured Output parses only final
`message.content`. Each repair request replays the complete prior assistant
message required by the provider protocol, including ephemeral
`reasoning_content`, then discards that reasoning data when the generation chain
ends.

### 6.5 Kimi acceptance

- `/v1/models` discovery
- structured-output probe
- mock streaming and tool calls
- malformed/partial output
- 401/429/5xx
- cancellation and timeout
- secret redaction
- injection attempts requesting unknown components
- 20 real requirements; at least 15 produce valid Drafts after bounded repair

Factory and user Runtime models use separate configuration, keys, and budgets.
Both may be unconfigured. Without a Factory provider the user can still create,
import, and edit Agents manually. Without a Runtime model profile the Agent can
still be generated, validated, versioned, and exported, but model-based Run is
disabled with an explicit configuration requirement. Provider secrets live in
Keychain/process environment and Agent source stores only `model_ref` or
`secretRef`.

Project and Agent creation may optionally save a non-secret Runtime API profile
(`provider`, API base URL, model ID, and API-key environment-variable name) in
application SQLite. An Agent profile overrides its Project profile; a Project
profile overrides the default Runtime profile. The API-key value itself remains
in the host Keychain/environment and is never written to a Project manifest,
Agent source, SQLite profile JSON, browser storage, or logs.

The Desktop Project and Agent dialogs expose a password field for the host
Runtime API key. A user action stores it under the opaque `model.primary`
Keychain reference and can immediately verify the selected profile. Verification
performs only the OpenAI-compatible `GET /models` request and returns a safe
status/code pair; it never sends a prompt or returns the key. The effective
Agent preflight also checks the model credential, locked dependencies, Tool
authorization, and configured MCP server without starting an MCP process.

Workflow has a matching no-effect preflight at
`GET /api/v1/projects/{project_id}/workflows/{workflow_id}/runtime-readiness`.
It resolves the immutable AgentCall targets, checks each pinned Agent's model
and dependency readiness, verifies that Workflow permissions cover child
permissions, and checks the Project node limit. It never commits a Workflow
version, contacts the model provider, or starts a child Run. Workflow execution
applies the same permission containment check, including
`shell_workspace_only`.

Local development may use the host process Runtime profile
(`VEYRA_RUNTIME_*` / `MOONSHOT_API_KEY`) so Agent nodes can run for testing.
Production and release modes do not use that shared host key for user-created
or Factory-generated Agents; those runs require a user-provided Runtime API.

---

## 7. Studio and Frontend Design

### 7.1 Preserved visual direction

Reuse the old Veyra visual language only:

- restrained light/dark themes
- typography and spacing
- sidebar/header/workspace shell
- neutral surfaces
- badges, freshness, errors, loading
- responsive desktop layout

Do not migrate old product pages, React state, APIs, Today, Situations, Reactions, Chat, or LegacyConsole.

### 7.2 Workspaces and navigation

Not every resource uses a Canvas. Shared editing means one matching
workspace per layer, not one Canvas for every page.

| Layer | Workspace | What the user does |
|---|---|---|
| Project | Dashboard | Status, resource counts, and settings. No graph editing. |
| Agent | Canvas | Declares its own inputs and outputs. Default skeleton Start → Model → Output. Left palette projects Model, Tool, Knowledge bindings, plus HumanApproval and Verifier. Condition, Transform, and AgentCall stay on the Workflow canvas. Right inspector edits parameters. Bottom panel test-runs. |
| Workflow | Same Canvas shell | Declares its own inputs and outputs. Palette is AgentCall plus control flow (Condition, Transform, HumanApproval, Verifier). No Model or Tool nodes. Existing Agents are not renamed into Workflows. |
| Component | Resource Catalog + Project Resource Library | Global Catalog owns description, version, examples, and references; Project Resource Library owns selected versions and usage. Not a flowchart. Primitive vs composite stays a required class. |
| Knowledge | Library + preview | Project documents, metadata, and citations. A document can be explicitly bound to an Agent from its detail page. Not a flowchart. |
| Files / Assets | File manager | Raw indexed files, separate from Knowledge documents; a file can open an Agent Studio run with its relative path prefilled. |
| Runs | List + timeline + logs | Inspect steps, outputs, and replay. No editing. |
| Community | Marketplace | Share and download versioned packages. Never execute remotely. |
| Settings | Control panel | Model providers, API keys, and runtime environment. Secrets stay out of Project directories. |

Home sidebar (no Project open). These items already exist and must not be
removed:

```text
New chat
Run workspace
Resource catalog
Knowledge base
Community
Projects tree
```

Catalog kinds are page tabs, not sidebar children. The Home Resource Catalog
is the full platform Catalog and does not change scope based on the last
Project. `#/components` remains a compatibility alias. Settings and Account
stay in the account menu.

Project sidebar (any route inside a Project, including Agent Canvas):

```text
New chat / Project resources / Analysis
```

Those three items are workspace surfaces, not resource kinds. Project
resources opens the current Project's selected and locked Catalog dependencies
while keeping Project chrome. The global Resource Catalog stays at
`#/resources`. Catalog kinds stay out of the Project tree. The Project tree
below the workspace list is the resource model:

```text
Project
  Agents            named runnable instances, plus to add
    <agent>
  Workflows         named orchestration instances, plus to add
    <workflow>
  Knowledge         long-lived documents, plus to add
    <document>
  Files             collection page; raw Project files
```

Do not list Agents as bare children of a Project. Agent and Workflow are
siblings. Knowledge documents nest under Knowledge; Files stay a collection
leaf because it is an index, not a Canvas instance. Run history is not a
Project-tree item. The header History control opens `#/runs` on the home
workspace and `#/projects/:projectId/runs` inside a Project.

Resource Catalog is a Home workspace surface for discovering all immutable
platform resources. Project Resource Library is a separate Project workspace
surface for bindings, usage locations, locks, configuration state, and
permission scope. MCP is grouped with Tools and is not a product layer beside
Agent, Workflow, Knowledge, or Component. The Agent/Workflow Canvas palette
projects the Project Resource Library plus built-in primitives.

The Project-to-resource tree lets users pin, edit, delete, and add Agents,
and add Workflows and Knowledge, without duplicating those kinds in the
fixed Project workspace list. Selecting an Agent opens its Canvas
(`.../agents/:agentId/design`). Selecting a Workflow opens the shared
Canvas shell (`.../workflows/:workflowId`). Conversation and analysis
routes remain reachable.

Routes:

```text
#/projects/:projectId
#/projects/:projectId/resources
#/projects/:projectId/agents
#/projects/:projectId/agents/:agentId
#/projects/:projectId/agents/:agentId/design
#/projects/:projectId/agents/:agentId/analysis
#/projects/:projectId/agents/:agentId/run
#/projects/:projectId/workflows
#/projects/:projectId/workflows/:workflowId
#/projects/:projectId/knowledge
#/projects/:projectId/files
#/projects/:projectId/runs
#/components
#/resources
#/components/:componentId
#/files
#/community
#/community/:owner/:slug
#/community/:owner/:slug/versions/:versionId
#/settings
#/account
```

`#/projects/:projectId` is the Project Dashboard. `#/resources` is the global
Resource Catalog; `#/components` remains a compatibility alias and a deep link
into Catalog detail. `#/projects/:projectId/resources` is the Project Resource
Library. It is not absorbed into the Agent palette and is not drawn as a
flowchart. The Desktop header uses one title for a root page and a horizontal,
linked breadcrumb for nested Project and Agent pages.

### 7.2.1 Information architecture lock

These decisions override earlier oscillating sentences in this document.
Do not hide Components, do not promote MCP into a product layer, and do
not rename Agent into Workflow.

1. **Agent is not renamed to Workflow.** An Agent remains a runnable
   capability whose graph may contain Model, Tool, and Knowledge. A
   Workflow is a separate source that only orchestrates AgentCall plus
   control flow. Both declare their own inputs and outputs.
2. **Shared editor does not mean every page is a Canvas.** Agent and
   Workflow share one Canvas shell. Components use Resource Library
   (list + detail). Knowledge uses document management. Runs use list +
   timeline. Files use the file manager.
3. **The Catalog and Project Resource Library stay separate.** `#/resources`
   is the global Catalog and `#/projects/:projectId/resources` is the selected
   Project dependency set. The left Studio palette projects Project resources
   plus built-in primitives for drag-and-drop.
4. **MCP is not a product layer.** Catalog kind `mcp_tool` is a discovery
   record under Tools. After normalization it lands on the Canvas as a
   Tool node. Studio groups MCP with Tools. Architecture diagrams must
   not draw MCP as a sibling of Agent, Workflow, Component, or Knowledge.

### 7.3 Studio layout

Agent and Workflow share one Canvas shell, with distinct source contracts,
node sets, dependency validation, interface mappings, and Runtime entry points.

Agent validation has two deliberately separate outcomes. The existing
`valid=true` result means that the source, graph, permissions, and lock shape
are structurally valid. When the Local Catalog is available, the same response
also includes dependency checks for every Tool/MCP, Skill, Policy, Template,
and explicit Knowledge reference. Those checks compare the exact content hash,
availability, runtime support, permission subset, MCP review state, and
Knowledge version/content hash. `runtime_ready` is scoped to these dependency
checks; the model provider credential and host-bound Tool secrets remain
execution-time checks and are never claimed to be configured by validation.
Studio shows this report after validation without turning a missing host
credential into a fake successful Run.

```text
Left      Catalog projection (Agent: Model / Tool / Knowledge;
          Workflow: AgentCall / control flow).
          MCP appears under Tools, not as its own product class.
          Canvas notes are UI-only annotations; they are not Flow nodes.
Center    Canvas. Hover a connection to insert a node; select it to
          delete or reconnect an endpoint. Notes can hold free text.
Right     parameter inspector
Top       name, version, validation, save
Bottom    local Agent / Workflow run, immutable version, events, approval and stop
```

The Resource Library's MCP tab shows a non-invasive server readiness check for
enabled state and host environment bindings. Discovery is an explicit action
that may start the configured MCP process; discovered tools remain review-gated
before they can be selected or run. The panel reloads discovered Tool descriptors
from the local Catalog so a page refresh does not discard the review queue. Agent Test Run inputs named like `path`,
`file`, or `document` may offer the current Project's indexed relative files as
suggestions, but the Runtime still reads them only through an authorized
Filesystem Tool.

### 7.4 Canonical state

Prompt, Form, Canvas, and Source edit the same normalized IR.

- React Query: persisted/server state
- Zustand or equivalent: Canvas selection/pan/zoom/transient inspector state
- revision/ETag: protect drafts from multi-window overwrite
- stable node IDs: map runtime events back to source
- Source/Canvas round-trip: behavior hash must remain stable when semantics do not change

Canvas may temporarily contain an incomplete graph while the user is editing.
That transient state does not replace the Project source: Studio writes only a
strictly valid `AgentSource`, so `agent.vagent.yaml` remains the last valid
definition. Conflicts use the Draft revision/ETag boundary and require an
explicit reload rather than a silent overwrite.

The component palette is a projection of the server-owned registry. Each entry
declares its editable fields, output ports, and Runtime support. A component can
be designable before it is executable, but Test Run must reject unsupported
nodes explicitly and must never skip them.

### 7.5 Run Canvas

The same graph switches from Design to Run mode:

- queued
- running
- waiting approval/input/external
- completed
- failed
- skipped
- cancelled
- verifying/verified/unverified

Show node duration, redacted inputs/outputs, tool calls, approvals, checkpoints, artifacts, verifier results, and final output.

Controls:

- Stop
- Approve/Reject
- Reply/Steer when supported
- Resume from checkpoint
- Retry safe node
- Open workspace/artifact

---

## 8. Local Runtime

### 8.1 Run state machine

```text
created → validating → queued → preparing → running
running → waiting_approval | waiting_input | waiting_external
running → verifying → verified | unverified | failed
running → cancelling → cancelled
process loss → interrupted
```

Terminal runs never return to running. Resume creates a child run referencing an explicit checkpoint.

Current local slice: a run may become `waiting` at `HumanApproval`, persist an
approval request plus checkpoint, and continue on the **same run** through
`approve` or `reject`. `stop` cancels the run. `retry` starts a new run from
stored inputs. `resume` is not used for approval waits. Node events are
persisted as they happen and can be replayed through
`GET /api/v1/projects/{project_id}/agents/{agent_id}/runs/{run_id}/events`.
POST `/run` returns a started run before completion. Ordered events are
persisted during execution. Workflow runs use a separate durable parent Run
and pinned child Agent runs; see ADR 0005 for supported controls and limits.

### 8.2 Runtime guarantees

- Every run uses an immutable Agent version.
- Every event has run ID, sequence, node ID, and timestamp.
- Every tool call has exact input digest, permission decision, result, and receipt.
- Unknown external effects are not retried blindly.
- Cancellation terminates the full child process group and revokes unused grants.
- Secrets are injected only into an authorized tool call.
- Model output is not proof of an external effect.
- Verification is separate from Agent-reported completion.

### 8.3 Events

```text
run.created
run.state_changed
node.queued
node.started
node.completed
node.failed
tool.requested
tool.started
tool.completed
approval.requested
approval.resolved
artifact.created
checkpoint.created
verification.completed
run.completed
run.interrupted
```

Persist append-only events using `(run_id, seq)`. Stream ephemeral token deltas to UI but persist only merged user-visible content/reasoning summaries.

### 8.4 Secret broker

- Agent contains `secretRef`, never a value.
- Values live in macOS Keychain/system keyring.
- Export/import preserves references only.
- Import requires rebinding.
- Logs/errors/artifacts/packages are scanned and redacted.

---

## 9. Deterministic Orchestrator and Monitor

### 9.1 Purpose

The Orchestrator connects work to Agent versions:

```text
Work Item defines what to accomplish
Agent Version defines how to accomplish it
Orchestrator schedules and reconciles
Monitor makes the state visible and controllable
```

### 9.2 Entities

- Project
- WorkItem
- WorkItemDependency
- AgentVersionBinding
- WorkspaceLease
- OrchestratedRun
- RunAttempt
- HumanInputRequest
- VerificationGate

### 9.3 Work item state

```text
backlog → ready → claimed → preparing_workspace → running
running → waiting_input | waiting_dependency | verifying | review
review → done
running/verifying → failed | cancelled
```

### 9.4 Scheduler

- deterministic, not LLM-owned
- global and per-project concurrency
- priority and dependency ordering
- CAS/lease claims
- one active attempt per WorkItem
- isolated Git worktree for code Agents
- workspace write lock
- retry only classified transient failures
- timeout-after-dispatch requires read-back
- non-idempotent lease loss becomes `needs_recovery`

### 9.5 Work item sources

1. Internal Veyra task board
2. GitHub Issues adapter
3. Linear adapter
4. Other tracker adapters later

Tracker credentials remain in host-side adapters and never enter Agent prompts.

### 9.6 Monitor

Monitor focuses on current operational attention:

- active
- blocked
- waiting approval/input
- stale
- failed
- verification gaps
- workspace/branch conflicts

The local implementation currently enforces four global and two per-Project
active WorkItems. Monitor exposes a stale signal after five minutes without a
Runtime event. An operator can explicitly recover a stale running item: the
local Runtime is stopped when still attached, the WorkItem is CAS-failed with a
`stall_recovered` classification, and the item can be retried. Lease expiry
remains the automatic failure/recovery boundary.

Runs remains immutable history. Monitor must not duplicate the full Run detail page.

---

## 10. Local Library and File Management

### 10.1 Data root

```text
<platform application data>/Veyra Agent Platform/v1/
  projects/
  db/app.sqlite3
  library/agents/
  library/components/
  packages/
  objects/sha256/
  workspaces/
  runs/
  logs/
  cache/
  trash/
```

Use `platformdirs`; never use the current working directory or the old Veyra state root as fallback.

### 10.2 File operations

- create
- generate
- import
- open source/open folder
- save immutable version
- duplicate
- Fork
- compare semantic diff
- export source/package
- validate
- run
- move to trash
- restore
- permanent delete with confirmation

Trash retention defaults to 30 days. Published or referenced versions are yanked, not hard-deleted.

### 10.3 External edits

- filesystem watch
- safe parse after change
- conflict prompt when Studio has unsaved edits
- Reload / Keep Local / Semantic Diff
- atomic save via temporary file, fsync, replace
- no silent Canvas overwrite

---

## 11. SQLite Data Model

Use application-generated UUIDv7 text IDs, UTC timestamps, foreign keys, WAL, and forward-only migrations.

### 11.1 Agent graph

- `agents`
- `agent_drafts`
- `agent_versions`
- `version_edges`
- `components`
- `component_versions`
- `agent_version_components`

Draft is mutable with revision. Version is immutable. Every run materializes or selects an immutable version.

### 11.2 Files and blobs

- `blobs`
- `files`
- `file_versions`
- `agent_version_files`
- `runtime_api_profiles` (non-secret Project/Agent provider metadata)
- `run_artifacts`

Actual bytes live at `objects/sha256/<hash>`. SQLite never stores large files or long stdout.

### 11.3 Runtime

- `work_items`
- `work_item_attempts` (CAS lease and classified local attempts)
- `runs`
- `run_tasks`
- `task_dependencies`
- `task_attempts`
- `run_events`
- `run_checkpoints`
- `tool_calls`
- `approval_requests`
- `run_commands`
- `agent_conversations`
- `agent_conversation_messages`
- `runtime_connections`
- `external_agent_sessions`
- `workspace_locks`

All frontend controls first write a durable `run_command`; they do not directly manipulate executors.

### 11.4 Local account/community cache

- `local_profiles`
- `account_links`
- `remote_bindings`
- `community_cache`
- `community_outbox`
- `local_stars`
- `local_reviews`

Logout does not delete or change local Agent IDs, versions, or Runs.

### 11.5 SQLite maintenance

- backup before migration
- recover stale leases on startup
- mark orphan runs interrupted
- periodic WAL checkpoint and ANALYZE
- VACUUM only in explicit maintenance window
- integrity checks
- mark-and-sweep unreferenced artifacts after grace period
- hash verification on blob reads

---

## 12. Account and Community

### 12.1 Modes

The desktop shell requires a Connected Account. Guest chrome is not shown.
Unauthenticated hash routes, including pasted Agent/Studio links, resolve to
`#/login` and the shell re-checks the Community session on every navigation.
Local Project files remain machine-scoped; signing in does not isolate them
by account.

Connected Account Mode also adds:

- publish
- download/import
- Fork
- Star
- Review
- Report
- organizations later
- optional private backup later

### 12.2 Authentication

V1 registration verifies an email code and then sets a password. Subsequent
login uses normalized email plus password. Password recovery verifies a new
email challenge. The implementation requires:

- Argon2id
- CSPRNG six-digit codes stored only as HMAC digests
- challenge purpose, expiry, resend, attempt, and consumed state
- opaque server sessions
- hashed rotating refresh/session tokens and reuse detection
- CSRF/Origin/SameSite/secure cookie. Desktop and Community Vite proxies
  rewrite loopback browser Origins to the Community service origin so local
  sign-in is same-origin to Community. Cross-site Origins are forwarded
  unchanged and rejected. Production still allows only the request origin
  and `VEYRA_COMMUNITY_ORIGIN`.
- password reset
- email/IP/device rate limits and anti-enumeration responses
- device/session revoke

Desktop tokens live in Keychain, not local SQLite plaintext. SMTP credentials
come from explicitly supplied process environment variables; the services never
auto-load a Project-directory `.env`.

### 12.3 Community service

Community is a separate FastAPI deployment. Never expose the local desktop service publicly.

The public V1 beta uses PostgreSQL plus S3-compatible object storage. SQLite is
permitted only for isolated development and tests.

The local development Community service currently uses SQLite plus a local
content-addressed package directory. This is the runnable registry slice; the
production PostgreSQL/object-storage deployment remains a release milestone.

Community data:

- users/profiles/email challenges/sessions/devices
- Agents and immutable versions
- version/Fork edges
- Stars
- version-bound Reviews
- downloads
- reports/moderation
- upload/scan jobs
- compatibility and verification claims

### 12.4 Upload pipeline

The current local Community registry implements the first runnable slice:
Desktop export plus authenticated multipart YAML upload, AgentSource validation,
size/UTF-8 checks, obvious credential-marker rejection, path/dependency scan
warnings, content-addressed storage, immutable version metadata, public
listing/detail, version download, local Project import, and Community Fork
edges. Development can publish directly after these checks; production can
quarantine the version for moderator review. This is still not the final
quarantine/moderation pipeline.

```text
explicit upload
→ quarantine
→ size/MIME/schema check
→ secret scan
→ permission/risk analysis
→ dependency lock/path/portability check
→ license/provenance check
→ preview
→ moderation/review
→ immutable published version or rejection
```

Downloaded content is not automatically installed or run. Import again validates locally and displays permission differences.

### 12.5 Community UI

Agent/template detail includes:

- source and behavior hashes
- author/organization
- license
- version list
- Canvas preview
- component lock
- permissions/secrets/network/shell requirements
- runtime compatibility
- conformance/evals
- verified claims
- Fork lineage
- Download/Import/Fork/Star/Review/Report

Star does not mean safe or effective.

---

## 13. Local API v1

### Bootstrap and settings

- `GET /api/v1/bootstrap`
- `GET /api/v1/health`
- `GET /api/v1/runtime/capabilities`
- `GET /api/v1/factory/status`

### Projects and Agents

- `GET/POST /api/v1/projects`
- `POST /api/v1/projects/open`
- `GET /api/v1/projects/{project_id}`
- `PATCH/DELETE /api/v1/projects/{project_id}`
- `GET /api/v1/projects/{project_id}/export`
- `POST /api/v1/system/select-directory`
- `POST /api/v1/system/select-archive`
- `POST /api/v1/system/reveal-project`
- `GET/POST /api/v1/projects/{project_id}/agents`
- `GET /api/v1/projects/{project_id}/agent-templates`
- `POST /api/v1/projects/{project_id}/agents/import`
- `GET /api/v1/projects/{project_id}/agents/{agent_id}`
- `GET/PATCH /api/v1/projects/{project_id}/agents/{agent_id}/draft`
- `POST /api/v1/projects/{project_id}/agents/{agent_id}/generate`
- `POST /api/v1/projects/{project_id}/agents/{agent_id}/validate`
- `POST /api/v1/projects/{project_id}/agents/{agent_id}/commit`
- `GET /api/v1/projects/{project_id}/agents/{agent_id}/versions`
- `GET/POST /api/v1/projects/{project_id}/agents/{agent_id}/conversations`
- `GET /api/v1/projects/{project_id}/agents/{agent_id}/conversations/{conversation_id}`
- `POST /api/v1/projects/{project_id}/agents/{agent_id}/fork`
- `POST /api/v1/import`
- `GET /api/v1/projects/{project_id}/agents/{agent_id}/export`

### Components and files

- `GET /api/v1/resources?kind=&availability=`
- `GET /api/v1/resources/{resource_id}/versions/{version}`
- `POST /api/v1/resources/resolve`
- `POST /api/v1/resources/drafts` (quarantined Resource Workshop intake)
- `GET /api/v1/projects/{project_id}/resources`
- `POST /api/v1/projects/{project_id}/resources`
- `DELETE /api/v1/projects/{project_id}/resources/{resource_id}/versions/{version}`
- `GET /api/v1/mcp/servers/{server_id}/readiness`
- `POST /api/v1/mcp/servers/import`
- `GET /api/v1/components` (compatibility projection of Component resources)
- `GET /api/v1/files`
- `POST /api/v1/files/import`
- `GET/DELETE /api/v1/files/{id}`
- `POST /api/v1/files/{id}/restore`
- `GET /api/v1/artifacts/{id}`

### Factory

- `POST /api/v1/projects/{project_id}/factory/sessions`
- `GET /api/v1/projects/{project_id}/factory/sessions/{session_id}`
- `POST /api/v1/projects/{project_id}/factory/sessions/{session_id}/messages`
- `POST /api/v1/projects/{project_id}/factory/sessions/{session_id}/generate`
- `POST /api/v1/projects/{project_id}/factory/sessions/{session_id}/apply-draft`

### Runtime

- `POST /api/v1/runtime/profile/validate`
- `GET /api/v1/projects/{project_id}/agents/{agent_id}/runtime-readiness`
- `GET /api/v1/projects/{project_id}/workflows/{workflow_id}/runtime-readiness`
- `POST /api/v1/projects/{project_id}/agents/{agent_id}/run`
- `GET /api/v1/runs`
- `GET /api/v1/runs/{id}`
- `GET /api/v1/runs/{id}/events?after_seq=N`
- `GET /api/v1/runs/{id}/events/stream`
- `POST /api/v1/runs/{id}/commands`
- `POST /api/v1/runs/{id}/cancel`
- `POST /api/v1/approvals/{id}/decision`
- `GET /api/v1/monitor`
- `GET /api/v1/monitor/stream`

### Orchestrator

- `GET/POST /api/v1/projects`
- `GET/POST /api/v1/projects/{id}/work-items`
- `PATCH /api/v1/work-items/{id}`
- `POST /api/v1/work-items/{id}/dispatch`
- `POST /api/v1/work-items/{id}/cancel`
- `GET /api/v1/orchestrator/status`
- `GET /api/v1/orchestrator/stream`

### Account and Community

- `POST /api/v1/auth/verification-codes`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/password-reset/request`
- `POST /api/v1/auth/password-reset/confirm`
- `GET/PATCH /api/v1/account/me`
- `GET/DELETE /api/v1/account/sessions/{id}`
- `GET /api/v1/registry/agents`
- `GET /api/v1/registry/agents/{owner_handle}/{slug}`
- `GET /api/v1/registry/agents/{owner_handle}/{slug}/versions/{version}`
- `GET /api/v1/registry/agents/{owner_handle}/{slug}/versions/{version}/download`
- `POST /api/v1/registry/agents` (authenticated multipart YAML publish)
- Existing local import: `POST /api/v1/projects/{project_id}/agents/import` accepts optional Community owner/slug/version/source-hash fields; the local service revalidates the source, creates a new local Agent identity, and stores the origin separately.
- Community quarantine and moderation are now configurable: development keeps direct publication, while production can require a moderator queue, persisted scan reports, and append-only decisions. Version-bound stars, reviews, and reports remain part of the runnable local Community slice, including persisted current-user Star state. Path/dependency warning scans are present; license scanning and long-lived moderation operations remain future work.

---

## 14. Legacy Asset Migration

The old Veyra repository remains unchanged and read-only for the new project.

### 14.1 Extract or rewrite

- AgentAdapter/ExecutionResult provider boundary
- task lifecycle/status/cancel semantics
- DurableCase revision/checkpoint/replay concepts
- EventInbox sequence/dedupe/recovery concepts
- Receipt/VerifiedEffect/Verifier contracts
- ExecutionTrace and replay concepts
- OpenClaw send/status/wait/cancel adapter behavior
- Ed25519 signing primitives
- canonical JSON/digest/idempotency helpers
- React visual tokens and small shared UI primitives
- Tauri sidecar lifecycle pattern

### 14.2 Do not migrate

- Living Context/Situation/Need/Reaction
- Today/Home/Chat product
- Weather/Calendar/Public Web/App Activity
- Belief/Attention/Commitment/Cognitive pipeline
- Feishu/channel integrations
- Project Guardian special cases
- old `main.py`
- WorldStateStore JSON layout
- old UI bundles/pages
- old state, `.env`, logs, snapshots, data
- old documentation and roadmaps
- old smoke suite wholesale

### 14.3 Provenance rule

Every extracted behavior must record:

- old repository
- source SHA
- source file/symbol
- copied vs rewritten
- new contract and tests
- reason for migration

No old directory may be added to `PYTHONPATH` or package search paths.

---

## 15. Repository Structure

```text
backend/
  app.py
  config.py
  api/
  domain/
    agent.py
    component.py
    run.py
    event.py
    receipt.py
  compiler/
  factory/
  runtime/
  orchestrator/
  components/
  storage/
  community/

web/
  src/
    app/
    ui/
    features/
      studio/
      agents/
      runs/
      monitor/
      components/
      files/
      community/
      account/

apps/desktop/
docs/
tests/
  unit/
  contracts/
  integration/
  security/
  e2e/
  live/
  fixtures/
```

Avoid generic top-level packages named `core`, `runtime`, or `interface` without product scope.

---

## 16. Testing and Quality Gates

### Backend

- pytest unit/contracts
- SQLite migrations from empty and previous versions
- restart/replay/checkpoint
- cancellation process group
- receipt/verifier
- secret leak
- malicious YAML/package
- path/symlink escape
- concurrency/lease/idempotency
- deterministic Kimi mock
- optional Kimi live lane

### Frontend

- TypeScript strict
- Vitest/React Testing Library
- Source/Canvas round-trip
- Run event reducer
- permission diff
- auth states
- Playwright desktop and responsive sizes
- production build

### Desktop

- sidecar start/stop
- new data root
- health/build identity
- isolated temporary SQLite
- package contains exact sidecar
- macOS arm64 validation first

### CI order

1. format/lint/typecheck
2. unit/contracts
3. SQLite/restart integration
4. security/adversarial
5. Studio → Kimi Draft → Runtime → Monitor → Verifier E2E with fake model
6. optional live provider/community lanes
7. frontend build
8. desktop package lane

Historical smoke counts are not a quality goal.

---

## 17. Development Roadmap

### R0 — Environment and contracts

- confirm this document
- isolate Python/Node environment
- project package structure
- SQLite configuration and migration baseline
- three handwritten Agent fixtures
- migration provenance ledger

### R1 — Agent/Component kernel

- schemas
- parser/canonicalizer
- hashes and semantic diff
- component registry
- file library
- import/export

### R2 — Kimi Factory and Studio

- Resource Catalog and availability projection
- built-in Component, Skill, Policy, and honest Tool/MCP descriptors
- Project-scoped Factory conversation persistence
- model discovery/settings
- AgentBlueprint
- generator and repair
- resource resolution, permission derivation, and missing-capability proposals
- Form/Source
- React Flow Canvas
- permission preview
- save version

### R3 — Local Runtime and Run Canvas

- graph executor
- tools and MCP
- secret broker
- approvals/checkpoints
- cancel/resume
- event store/SSE
- verifier/evidence
- Run Canvas

### R4 — Deterministic Orchestrator and Monitor

- projects/work items/dependencies
- scheduler/reconciler
- isolated workspaces
- concurrency/retries/stall
- Monitor and Orchestrator Canvas
- GitHub Issues adapter

### R5 — Account and Community Public Beta

- separate Community service
- email verification, password login, recovery, and session management
- PostgreSQL Community database and object storage
- upload quarantine
- Agent/template versions
- download/import/Fork/Star/Review/Report
- Community UI

### R6 — Desktop release candidate

- Tauri shell
- PyInstaller sidecar
- setup/settings
- three official Agents
- full security/test gate
- documentation
- user trial

### R7 — New repository main release

- clean branch
- reviewed changes
- exact-revision tests/build/package
- PR `codex/agent-platform → main`
- retain old Veyra repository as legacy reference

---

## 18. Acceptance Metrics

Local V1:

- median time from requirement to first valid Draft
- generated Draft validation rate
- import/export behavior-hash stability
- Source/Canvas round-trip stability
- run completion rate
- verified completion rate
- stop/approval/resume success
- same Agent second-run rate
- percentage creating a second version

Community:

- successful download/import rate
- successful first local run rate
- Fork lineage correctness
- version upgrade regression rate
- permission escalation detection
- repeat publisher rate
- external creator count

North star:

> **Weekly Agent versions that are run repeatedly and produce at least one verified result.**

### Kill criteria

Stop expanding if:

- target users do not want file ownership/versioning
- generation still requires extensive manual repair
- Source/Canvas round-trip is unstable
- local setup is too difficult
- users run each Agent only once
- downloaded Agents depend on hidden platform state
- product only visualizes nodes without producing verified output

---

## 19. Maintainability Rules

- This document is the single current authority.
- Every public JSON contract has `schema_version`.
- Every write has revision and idempotency.
- Every run event has run ID, sequence, and node ID.
- Model output is always untrusted until validated.
- External effects require receipts and independent verification.
- Drafts are mutable; committed/published versions are immutable.
- SQLite access goes through repositories and migrations.
- Large files are content-addressed objects, not database blobs.
- Secrets never enter source, SQLite plaintext, logs, artifacts, or packages.
- Desktop UI requires a Community session; local Project files remain machine-scoped.
- Community server and desktop sidecar are separate deployments.
- No giant `main.py`, `LegacyConsole.tsx`, or global raw-dict state store.
- Every feature owns contracts, services, routes, UI, tests, and docs.
- Any compatibility degradation is explicit.
- Deletion is recoverable by default.

---

## 20. Immediate Next Documentation/Implementation Tasks

The current resource-boundary decision, migration corrections, executable
Workflow slice, package limits, and next acceptance stages are recorded in
[ADR 0005](adr/0005-resource-boundaries-and-pinned-workflows.md). Its explicit
compatibility and execution boundaries supersede earlier ambiguous wording.


1. Resource Catalog node definitions are file-backed packages at
   `resources/nodes/<family>/<id>/node.yaml`; Factory resolves only those records.
2. Project and Agent child relationships use stable `parent_agent_id` references
   while keeping the filesystem flat.
3. Project/Agent Runtime API profiles are optional, editable, non-secret, and
   selected in the order Agent override → Project profile → default profile.
4. Local development may run Agent nodes through a host Runtime model profile;
   production still requires a user-provided Runtime API before Agent runs.

All new work retains the clean-room legacy boundary. No implementation phase
copies legacy Veyra directories or loads a Project `.env` automatically.
The local sidecar may load a repository-root gitignored `.env` at process
start for development credentials.
