# Veyra Agent Platform — Canonical Development Design

> Status: **ONLY CURRENT PRODUCT AND ENGINEERING AUTHORITY**
> Revision: 1.6
> Date: 2026-09-14
> Repository: `/Users/spectre/PycharmProjects/veyra-agent-platform`
> Development branch: `codex/agent-platform`
> Legacy source: `/Users/spectre/PycharmProjects/veyra @ 1ffb4cdd45c798556390c20e53fc2d265cd56471`
> Implementation status: Local design/runtime and Community registry slices exist; current evidence and remaining user loops are maintained in [DEVELOPMENT.md](DEVELOPMENT.md). This document includes target requirements, not a claim that every described capability exists.

This document starts from a new, independent project. It does not assume that the old Veyra repository will be cleaned, merged, or used as a runtime dependency. The old repository is read-only migration evidence. Every extracted behavior must be re-namespaced, simplified, tested, and recorded in this document or a later migration ledger.

---

## 0. Executive Decision

Veyra is an **Agent + Workflow AI studio**. Local Desktop (`5173` + `8771`) is
the working product. Community (`5174` + `8772`) is accounts and a public
registry, not a cloud workspace.

The two first-class Project objects are peers:

```text
Project
├── Agents
├── Workflows
├── Knowledge
├── Files
└── Runs
```

**Agent** is an autonomous capability unit. It is not a fixed DAG.

```text
Agent = Model + Instructions + Tools + Knowledge + Memory/Context
      + Skills + Policies/Guardrails + Input/Output contract
      + Agent Runtime Loop (max_turns)
```

At run time an Agent receives a task, decides whether to call a permitted
Tool / Knowledge / Skill, observes the result, and continues until it returns
a final output or hits `max_turns`. Users do not have to draw those turns as
nodes. HumanApproval inside an Agent Run is a **tool-permission gate**, not a
business DAG node.

**Workflow** is an explicit typed execution graph. It owns Start, AgentCall,
Tool, Condition, Transform, HumanApproval, Verifier, Output, typed ports, and
`data_edges`. AgentCall must pin `agent_id@version_id` (never Draft).
HumanApproval here is a **business step**.

They share Provider, Tools, Knowledge, Files/Artifacts, Credentials, runtime
infrastructure, Runs/Events/Receipts, and Resource Library. They do **not**
share Builder compilers, Studio semantics, source files, or schedulers.

Core product loop:

```text
Describe requirement
→ Builder classifies create_agent or create_workflow
→ Agent: specification → capability resolution → canonical AgentSource
  Workflow: specification → typed graph compile → WorkflowSource
→ user reviews the matching Proposal
→ apply Draft (Workflow may also commit companion Agents)
→ edit in Agent Studio (capability map) or Workflow Studio (typed DAG)
→ run locally
→ Agent Run shows a model/tool timeline; Workflow Run shows node overlay
→ stop / approve / reject / resume
→ export a version without secrets
```

Product promise:

> **Describe it. Design it. Run it. Share it.**

Chinese promise:

> **描述你的需求，得到真正属于你的 Agent 或 Workflow；看见它如何工作，并把可靠版本分享给别人。**

Historical Flow graphs (Start → Model → Condition → Approval → Output) remain
openable as `execution_kind=graph` Agents. They are not silently migrated.
Simple Start→Model→Output graphs are loop-Agent candidates; graphs with
Condition / HumanApproval / multiple Models are Workflow candidates.

### 0.1 Legacy graph Agent migration plan

Existing committed Agent versions keep their bytes, hashes, and
`execution_kind=graph` runtime. Studio continues to open them as DAG editors.
No automatic rewrite runs in this slice.

Deterministic classification (`classify_legacy_graph_agent`) is:

| Classification | Typical graph | Planned action |
|---|---|---|
| `loop_agent` | already `execution_kind=loop` | keep |
| `simple_graph_loop_candidate` | Start → Model → Output (optional Tool bindings) | convert to loop Agent in a later explicit migration |
| `multi_model_graph_candidate` | two or more Model/Agent stages | convert to Workflow |
| `orchestration_workflow_candidate` | Condition, HumanApproval, Transform, Verifier, or AgentCall | convert to Workflow |
| `legacy_graph` | anything else | keep readable as a graph Agent |

`silent_migrate` is always false. Users must opt in before any rewrite.

---

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

### 3.3 Desktop, Web, Community service, and Showcase boundary

The four local development ports are distinct product surfaces, not four names
for one Community application:

- `5173` is Veyra Desktop, the authenticated day-to-day workspace. It owns
  Project work and the interactive Community discovery, publish, release
  inspection, Star, and import-preview flows.
- `8771` is the loopback-only Local API and trusted local execution boundary
  for Project files, Agent/Workflow source, Builder, Runtime, Knowledge,
  Resources, Import, approvals, receipts, and Orchestration.
- `8772` is the separate Community service for accounts and the existing
  immutable Agent/Plugin release registry, metadata, moderation, feedback, and
  artifact downloads. It never executes a downloaded Agent.
- `5174` is the public site. The default route is the anonymous product
  Showcase. `#/community`, login, and account are the Community catalog. It
  does not provide Cloud Projects, Cloud Conversations, Cloud Files, Cloud
  Runs, or Cloud Credentials.

The Registry is a service capability, not a second execution host. The
`web/apps/community` package name is retained. Desktop Community discovery,
publish, Star, and import stay on `5173`. Generation and Chat stay on the
Local API. A Cloud data plane is not part of the current product.

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

Studio Test Run executes the current Agent Draft. The Agent App / Run surface
(`#/projects/:projectId/agents/:agentId`, and `/run` without `run_id`) executes
only a committed immutable Agent version. Conversations pin that version; a later
commit does not silently upgrade an existing conversation. `interaction_mode`
(`auto|chat|form|hybrid`) chooses the product surface only; Runtime still receives
typed inputs, conversation context, and artifacts. The App reuses the same local
Runtime preflight as Studio and can offer indexed Project file paths for
explicitly declared path-like inputs. A suggestion only fills a relative path
value; it does not turn the Files page into implicit model context or bypass the
Agent's Filesystem Tool permission. Run Detail (`?run_id=`) keeps the technical
timeline. Project Runs remains the project-level history.

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

### 5.3.1 Typed I/O

Agent and Workflow `inputs` / `outputs` are typed by user intent. They are not
a default `string → string` contract.

Canonical runtime value kinds:

- **Scalar** — `string`, `number`, `integer`, `boolean`
- **JSON** — `object`, `array`, `table`
- **ArtifactRef** — `image`, `pdf`, `document`, `file`, `audio`, `video`

The compact wire form remains valid and is the default round-trip:

```yaml
inputs:
  text: string
outputs:
  result: string
```

Rich descriptors are used when compact strings cannot express the field:

```yaml
inputs:
  product-image:
    type: artifact
    artifact_kind: image
    required: true
    multiple: false
    accepted_media_types: ["image/*"]
```

Legacy Agents that declare `text: string` continue to parse and run without a
YAML migration. Compact fields that are required, single-valued, and otherwise
default still serialize as type strings so existing `behavior_hash` values stay
stable.

Declared modality is not a runtime capability claim. An Agent may declare
`image` input or `pdf` output and still be designable. Running it requires a
compatible Runtime model or adapter. Missing capability must remain a truthful
blocker. Values must not silently collapse to strings.

Binary values are `ArtifactRef` records, not inline Run JSON. Bytes live in the
existing content-addressed object store (`objects/sha256/<digest>`). Metadata
is Project-scoped in `project_artifacts`. Upload, read, resolve, and download
all require `project_id` plus `artifact_id`. Host paths are never exposed to
models, APIs, or UI.

Runtime model modality truth is `RuntimeModelCapabilities` on the Agent
Runtime profile. It is not `ProviderCapabilityProfile` and is not inferred in
the UI from a model id substring. Exact model ids only. Known text-only
Moonshot models (`kimi-k2`, `moonshot-v1-8k`, `moonshot-v1-32k`) keep
`image_input=unsupported`. Moonshot vision models including `kimi-k3`, and any
other user-bound Runtime model, keep `image_input=supported`; the Provider may
still reject a request. `unknown` is not used to fail-close vision. Audio and
video adapters remain unsupported until they exist. PDF, document, Office
(`docx`/`xlsx`), and generic file inputs extract bounded plain text into the
model prompt; bytes, host paths, and `artifact://` URLs never enter Run JSON
or Provider HTTP. Folders are filesystem tools, not ArtifactRef kinds.
Provider HTTP calls may use OpenAI-compatible `image_url` data URLs; they
must not send `file://`, host paths, or raw `artifact://` URLs. PDF, document, and file inputs compile as designable graphs; Runtime extracts
bounded text into the prompt. Image outputs compile onto `model.image` and
need a bound User Runtime image model at Run time. Missing PDF renderers stay
a truthful `missing_capability`. Audio and video adapters remain unsupported.

Agent Playground is not implemented. Workflow Builder Compiler is not
implemented. Conversation restore still returns the latest canvas;
multi-artifact Workbench remains limited.

### 5.4 Components: primitive vs composite

Components are one resource kind with two required classes. They must not
collapse into a single palette bag.

**Primitive** — platform-owned graph node types. These are the only nodes a
Canvas may persist. V1 primitives:

- Start, Model, Tool, Condition, Transform, HumanApproval, Verifier, Output
  (Agent canvas palette: a self-contained executable capability graph)
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

### 5.5.2 Declarative Plugin Packs

Veyra accepts a bounded `.vplugin.zip` format as a convenience bundle for
external extensions. A pack contains a strict `plugin.vplugin.yaml`, optional
`skills/<slug>/SKILL.md` files, and an optional standard `mcp.json`. It cannot
contain Python/Node code, symlinks, encrypted members, arbitrary paths, or
plaintext environment values. The pack is stored in application data with a
content hash and a `quarantined` state; importing never starts a process,
contacts a URL, or changes the Catalog.

Activation is a separate, explicit user action. It promotes the declared Skills
through Resource Workshop into the Catalog, while MCP server definitions are
registered with `enabled=false`; the user must enable the server and explicitly
discover its tools in the Tools/MCP panel. Discovered tools retain the normal
review gate. This gives a useful Codex/OpenClaw-style bundle entrypoint without
executing untrusted plugin code inside the desktop process.

For multiple installed versions of one `plugin_id`, activation is exclusive:
activating one version disables the other versions' Skills and MCP servers.
Activating an older version is the rollback operation; the previous package
remains installed and is not overwritten.

The reference tree is under `examples/plugin-packs/research/`. A pack can be
assembled with `zip -r research.vplugin.zip plugin.vplugin.yaml skills mcp.json`.

### 5.5.3 Project-owned Custom Component V1

Custom Components are Project-owned composite resources, not new hard-coded
`ComponentType` values. The Resource Library owns their drafts and immutable
versions; AgentSource refers to a published component by exact
`component_id@semver` and locks its content hash. They are available to Agent
Canvas only when the matching version is present in that Project's Library.
They are not Workflow nodes, global Catalog entries, or executable code
packages.

V1 accepts four declarative implementation kinds:

- `model_recipe` — an instruction that uses the configured Runtime
  `model.primary`;
- `tool_wrapper` — a typed facade over one exact Project-bound Tool reference
  and content hash; its permissions/readiness are derived from that Tool;
- `transform` — a bounded string-template mapping over typed inputs/outputs;
- `composite_graph` — a declarative graph definition, reported as
  `design_only` until graph composition is supported by the Runtime.

Arbitrary Python, JavaScript, Shell, WASM, or eval/script implementations are
rejected. Metadata is string-only and rejects secret-like values, secret-named
keys, and absolute host paths. Dependency pins are exact and Project-scoped;
Catalog lookup alone is not enough to publish a Tool wrapper.

The lifecycle is `draft → validate → publish → deprecate`. Editing a published
component creates a draft based on the selected latest version; it never
mutates a published version or silently upgrades an Agent. Publishing creates
an immutable semver reference and hash. Deprecation disables that version for
new resolution without deleting its source; only a draft may be deleted, and
the service checks existing references before removing an unpublished-only
component. Resource readiness is recomputed from the effective Runtime and
Project-bound dependencies; saving or binding a resource does not configure
host credentials or make an unsupported implementation runnable.

Studio projects each current Project-bound Custom Component as a dynamic
`CustomComponent` node whose `uses` value and lock are the exact version
reference and bound hash. Selecting it declares the component's derived
permissions in AgentSource; the backend remains authoritative for dependency
resolution and Runtime authorization. No automatic latest-version selection,
Catalog install, or silent permission widening is allowed.

Builder capability composition follows a strict resolution order: use a core
primitive where it directly expresses the duty; otherwise reuse the unique,
ready compatible capability already in the current Project Resource Library;
clarify if multiple candidates match; and report `requires_configuration`
without creating a duplicate when a matching capability is not ready. Only a
missing capability that the bounded Custom Component contract can honestly
implement may become a Component Proposal. Unsupported modalities such as
image or PDF parsing remain missing capabilities; they must not be disguised
as text-only `model_recipe` implementations.

A Component Proposal reuses the persisted Builder operation and existing
proposal/Workbench protocol. It is one explicit mutation: review the typed
inputs/outputs, implementation, exact dependencies, derived permissions,
readiness, and Agent step; then explicitly confirm or reject. Reject creates
nothing and cannot silently downgrade the Agent. Confirm runs the existing
`draft → validate → publish` lifecycle. Validation or continuation failure is
recorded on the operation and stops that continuation. Builder provenance
stores conversation/operation/proposal identity only, never the full
conversation or hidden prompt.

For Agent creation, the server re-reads Project resources after Component
publication and recompiles the original stored Semantic Plan. The resulting
Agent Blueprint is a separate review and requires a separate confirmation
before any Agent Draft is created. Its `CustomComponent` node pins the exact
published `component_id@version` and content hash. A direct `create_component`
request follows the same proposal and lifecycle but has no Agent continuation.
`tool_wrapper` is allowed only over an exact, already Project-bound Tool;
`transform` stays within the current bounded grammar; `composite_graph` remains
`design_only`. No arbitrary code generation, Tool creation, or Catalog
auto-install is permitted.

### 5.5.4 External Agent Import V1

External Agent import has three input forms: a generic YAML file, a selected
folder, and a ZIP archive. ZIP is only a transport; it is validated and then
sent through the same bounded file scanner as a folder. The importer does not
execute Python/Node/Shell code, install dependencies, or reuse a foreign
Runtime.

```text
YAML / Folder / ZIP
        ↓
bounded scanner + format detector
        ↓
generic Import IR
        ↓
capability mapping + compatibility report
        ↓
user preview and confirmation
        ↓
standard Veyra Agent Source
        ↓
Canvas / validate / Runtime
```

V1 maps prompt/instructions, model metadata, inputs, outputs, selected
read-only Veyra Tools, and installed Skill references. Unknown tools, inline
Skills, Knowledge files, external workflow steps, and raw permission claims
remain visible as `partial` or `unsupported` findings; they are never silently
discarded or granted. The applied Agent keeps `import/manifest.json` beside
its source so the original mapping decision remains inspectable. Model API
credentials are never imported; the user configures the device credential
profile through the normal Runtime settings. Device credentials use the host
system credential service through `SecretStore`; the concrete backend may be
macOS Keychain, Windows Credential Manager, or Linux Secret Service/KWallet.
The Agent contract does not depend on any one operating system.

The import record is persisted in local application data so analysis and
application are separate actions:

- `POST /api/v1/agent-imports` — analyze an uploaded YAML/ZIP or folder path.
- `GET /api/v1/agent-imports/{import_id}` — read the compatibility preview.
- `POST /api/v1/agent-imports/{import_id}/apply` — explicitly create a local
  Agent Draft in a selected Project.

This is a generic adapter boundary, not a promise to reproduce Dify, Coze,
CrewAI, AutoGen, or LangGraph runtimes. Platform-specific adapters can be
added later without changing Canvas or Runtime contracts.
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

If no registered resource satisfies a required capability, Resource Resolver
returns `missing_required`. Resource Factory V1 classifies that gap with
`ResourceFactoryStrategy` (`generatable`, `requires_user_configuration`,
`requires_external_integration`, `unsupported`) and persists a
`ResourceFactoryPlan` on the canonical Proposal. It may generate a quarantined
Skill instruction or a declarative Tool Wrapper over an existing Runtime
adapter (`http.request`, filesystem read/search/list). It does not write
Python, shell, eval, MCP, Policy-enforced, Template, or image-generation
runtimes. User review is mandatory: Draft → validate → approve exact snapshot
→ immutable published overlay. Resolver rediscovers the resource from Catalog
metadata; Factory never `force_select`s it.

### 5.6 Version hashes

Compute:

- `file_hash`: entire source including UI layout and documentation
- `behavior_hash`: execution semantics only
- `lock_hash`: resolved dependencies
- `package_hash`: immutable package bytes

Moving a Canvas node must not change `behavior_hash`. Changing prompt, tool, permission, transition, model, or verifier must change it.

---

## 6. Veyra Builder Agent / Harness

### 6.0 Chat-first product decision (2026-09-14)

Veyra Chat is the natural-language construction entrance. Studio is not a second AI
conversation surface: it owns structure inspection, manual Canvas/Form/Source edits,
configuration, validation, Run, and inspection of Builder results. The existing
Factory name/API remains a creation adapter, not a competing product intelligence.
Runtime Agent conversations remain version-bound executions, not project writers.

| Context | Behavior and authority |
| --- | --- |
| Global / New Chat | Collect the goal without assuming a Project; explicitly select/create one before writes. Automatic Project planning/creation proposals remain future work. |
| Project Chat | Discover the actual Project and library; create via the existing Blueprint adapter or select an existing Agent/Workflow for a source-change proposal. |
| Agent / Workflow focus | Narrow the same Project Harness to the selected source, identity, revision/ETag, permissions, locks and bindings. Never infer authority over other objects. |

The shared implementation boundary is `local/builder`: a stable system prompt
owns Veyra semantics and trust rules; a dynamic Harness assembles bounded structured
context from server-owned Project and Resource Catalog services. Factory interview,
Blueprint generation and edit-source generation share this boundary with explicit
output modes. Existing compiler/resolvers, EditProposal storage, Draft writer,
validation and Runtime preflight remain the authoritative execution boundaries.
The model has no write, registration, permission-grant or execution tool.

Long-term generation rule: models express and plan semantics; Veyra compiles
semantics into canonical, validated, authorized and executable objects. The
default provider-facing create contract is `AgentSemanticPlanV1`. A full
`AgentBlueprint` is compiled server-side and remains the canonical review/Apply
object. The Moonshot MFJS projection of AgentBlueprint is a compatibility
bridge, not the default model contract.

Builder Conversation History and Runtime Run History are different canonical
domains.

Conversation Message ≠ Builder Operation Event ≠ BuilderHarnessReceipt ≠
Proposal ≠ Runtime Run.

- Conversation messages are the user-facing chat: user input, understanding,
  clarification, recoverable failure summaries, and a single final result.
  They never carry Provider protocol facts, snapshot hashes, or receipts.
- Builder Operation Events answer “what happened in this operation?” They
  persist a bounded event stream (`builder.intent.*`,
  `builder.semantic_plan.*`, `builder.compile.*`, `builder.proposal.*`,
  `builder.apply.*`) so Activity stages can be collapsed, refreshed, and
  audited. They are not chat bubbles and are not receipts.
- BuilderHarnessReceipt answers “under what controlled harness/provider
  context did this model invocation happen?” One receipt per real provider
  request (`resolve_intent`, `interview`, `semantic_plan`,
  `semantic_plan_repair`). Persist `prepared` before the request; finalize
  `success` or `failed`. Failures still have receipts. Typed
  `strict_json_schema` → `json_object` fallback is two invocations. Receipts
  store only safe metadata (policy/schema hashes, bounded snapshot hashes,
  included/excluded context categories, provider/profile facts). They never
  persist prompts, Knowledge/File bodies, credentials, headers, provider
  bodies, or hidden reasoning. Historical receipts are immutable after
  finalize; later Recheck / Project / Catalog changes must not rewrite them.
  Deterministic operations with no model call have no receipt.
- Proposals / compiled artifacts belong to the Workbench review surface
  (Canvas, resource plan, Diff/Impact, readiness). Chat may link to them.
- Runtime Run records what actually executed. Builder operations may later
  reference `run_id`; receipts do not store Runtime evidence.

Chat must not copy full Run event streams; at most a `run_id` reference.
The desktop header “历史” page remains Runtime Run History only. The left
“最近” list is Builder Conversation history, like a GPT/Codex chat list;
it does not include Runtime Runs. Conversation titles are concise and
persisted (prefer Semantic Plan `suggested_name`), not the raw prompt.

Context includes Project identity/inventory, library bindings, available resource
descriptors with exact hashes, readiness and permissions, plus the selected saved
source/revision/ETag when editing. Knowledge and Files are metadata/bindings only;
file presence does not consent to content ingestion. No secrets, host paths or
unselected file contents are injected. A size limit fails visibly rather than
silently dropping unsupported capabilities or source fields. Runtime descriptor
support is not host configuration readiness or a successful Run.

Resource resolution is reuse-first: prefer already-bound Project resources, then
registered Catalog resources, then report a missing capability. Never invent refs
or downgrade requested capabilities silently. Future native resource proposals
must carry source/type/version, permissions, dependencies, runtime readiness,
compatibility, validation and provenance; executable/high-privilege resources need
stricter review and cannot be installed from arbitrary model output. Project-only
objects belong to the Project; reusable resources require the user's explicit
Project-only versus Library choice. Community publication is outside this slice.

The safety protocol is User Request → Intent/Plan → Candidate → persisted Proposal
→ actual Diff/Impact → explicit Confirm → Apply → Validate → Result. Source-edit
mode returns a complete typed Source; the server builds the Proposal envelope and
derives impact, never trusting a model claim of success. For canonical Builder
`create_agent`, the reviewed `AgentBlueprint`, compiled `AgentSource`, resource
plan, semantic plan and provenance are persisted as one `create_agent` Proposal
snapshot before review. The operation link and `builder.proposal.ready` event are
written in the same transaction. Confirm resolves the Proposal by `proposal_id`,
verifies its source/behavior/lock hashes and current Project dependencies, then
installs exactly that persisted source while preserving its reviewed identity;
the mutable Factory session Blueprint is not recompiled or used as Apply authority.
Duplicate Apply returns the persisted result without another Agent, while rejected,
cross-operation, cross-Project, conflicting-identity, or tampered Proposals fail
closed. The Factory session remains the review/workbench lifecycle and is closed
after canonical Apply. Reject, guarded Undo and conflict recovery are retained.
The first Chat editing slice targets one existing Agent/Workflow; automatic intent
routing, multi-object transactions, resource authoring and auto-approval are deferred.
The legacy direct Factory session apply endpoint remains a compatibility adapter;
the canonical Builder create-agent path must use the persisted Proposal command.

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

The model produces a small `AgentSemanticPlanV1` describing user intent:

- goal, suggested name, description
- inputs/outputs
- summary steps
- optional `step_intents` graph intent (`semantic_key`, `name`, `purpose`,
  `operation_kind`, `depends_on`, optional `capability_requirement`, semantic
  Condition `branches`, executable `condition_expression`, branch-local
  `branch_condition` / `branch_key`, and deterministic `output_mapping`). A
  Condition declares exactly two `{key, label}` branches; the compiler maps
  them in declaration order to Runtime `true` / `false` ports and preserves
  labels. `purpose` is human-readable intent; `condition_expression` is the
  only executable predicate. V1 accepts only a bounded `field == literal` or
  `field != literal` comparison over a declared Agent input, with string,
  boolean, or integer literals. A branch-local step depends only on its own
  branch or its parent Condition. `depends_on` is ordering/control, not
  inter-step value transfer. Only the last Model on each path to Output
  emits the declared top-level Agent outputs. Earlier Model steps write a
  working note named by `semantic_key`; Runtime may pass those notes in the
  shared run values bag, but Transform and Condition cannot read them.
  Human confirmation is `approval`. Later duties may set `branch_condition`
  to that approval and `branch_key` to `approved` or `rejected`; rejected
  may continue a revise Model instead of jumping to Output. A Condition
  still compares only a declared Agent input supplied at Run start. Do not
  represent the same confirmation as both approval and a Condition on a
  synthetic `decision` field. Transform mappings may read only declared
  Agent inputs or
  literals and target declared Agent outputs. Step-level typed I/O is reserved
  for `reusable_capability=true` Model, Transform, or capability steps; it
  defines that reusable component contract and does not define general step
  dataflow. A natural-language classification that cannot be represented by
  this predicate grammar is unsupported and must fail closed; the server must
  not invent a non-empty check or hidden Model call. `capability_requirement` names a Project-bound tool;
  it is not a node ID, hash, version pin, or canvas coordinate.
- capability intents and knowledge intents
- approval points, success criteria, user constraints

It must not emit resource hashes, `source.lock`, Knowledge/Resource UUIDs,
permission sets, node/edge IDs, canvas positions, filesystem roots, Project
paths, runtime adapters, or credentials.

`SemanticPlanCompiler` then compiles a canonical `AgentBlueprint` candidate by
reusing the deterministic Project Knowledge and Project Resource resolvers.
A V1 plan without `step_intents` stays a simple Start → optional Project Tool →
one Model → Output graph only when it has a single summary step. Multiple
summary steps are sequential Model duties, not one collapsed prompt. V2
`step_intents` compile real Model, Tool, Transform, Condition, HumanApproval,
Verifier, and Output nodes. Bound, ready, uniquely matching Project Resource
Library capabilities are reused; Catalog-only resources are never
auto-installed. The compiler never emits AgentCall inside an Agent, never
hallucinates Tools, never silently upgrades pins, and never overgrants
permissions. HumanApproval becomes a real node when the plan asks for
confirmation. Verifier is emitted only when a check maps to an existing
contract (`output.not_empty`); unmapped verification becomes a Model plus a
warning, never a fake Verifier. If `step_intents` already expressed approval,
condition, verification, transform, capability, or more than one Model duty,
generation must not silently fall back to a V1 one-model graph. Unready
bindings compile as designable graphs with a truthful readiness warning.
The server owns node/edge IDs, Tool/Knowledge refs, `source.lock`, required
permissions, graph wiring and verification defaults. Ambiguous mentions become
clarification. Unbound capabilities become `missing_capability`. Catalog
auto-add, silent upgrades and permission overgrant are forbidden.

An invalid Transform that only tries to rename/copy a prior Model output is not
a user-required deterministic Transform: that dataflow is not represented by
this contract. Repair may remove only that mapping step and preserve the
producing Model duty by returning the declared Agent output fields. A genuine
input/literal-to-output Transform remains a required duty. Both paths fail
closed if the remaining semantic graph cannot be compiled truthfully.

The compiled Blueprint still goes through `AgentBlueprint.from_dict`, schema and
graph validation, dependency checks, Factory review, Proposal/Diff/Impact, and
explicit confirmation before Apply. Compiler output is never a second canonical
store; `AgentBlueprint` / `AgentSource` remain source of truth.

A provider-specific AgentBlueprint JSON Schema projection may still exist as a
compatibility bridge. It is not the default generate contract.

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

Existing Agent and Workflow edits also require a review boundary. A natural-language
request produces a persisted proposal against a specific Draft revision and ETag.
The server computes the actual source diff, permission changes, dependency checks,
and affected objects. Only explicit confirmation applies that stored candidate via
the existing Draft writer. A stale proposal cannot overwrite a newer edit. Reject
leaves source intact; undo restores the previous source as a new revision only when
the applied Draft has not changed since. Provider reasoning stays in memory. The
first editing surface targets one Agent or Workflow at a time; multi-object Project
transactions remain a subsequent module, tracked in the development document.

```text
User requirement
→ persist Builder user message
→ bounded Factory conversation
→ server-selected Resource Catalog snapshot
→ Kimi JSON Schema AgentSemanticPlanV1
→ SemanticPlanCompiler
→ canonical AgentBlueprint
→ schema validation
→ component/tool/knowledge resolution
→ Skill compilation and Policy application
→ exact Project pin and permission derivation
→ graph validation
→ bounded repair loop, maximum three attempts
→ user-visible Blueprint and Resource Plan
→ persist canonical `create_agent` Proposal snapshot
→ user confirms the Proposal identity
→ server installs the exact persisted AgentSource as an Agent Draft
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

The Platform key belongs in server/deployment configuration and is never
exposed through User Runtime Credential APIs. User Runtime keys are added through
the Provider Credentials surface and are resolved only through an explicit
binding or User default; `MOONSHOT_API_KEY` is not an implicit Runtime path.
The current local implementation supports `credential_scope=device`; the
`cloud` scope is a future contract seam, not an implemented Cloud Vault.

Blueprint generation uses the `ProviderCapabilityProfile` attached to
`GET /api/v1/factory/status`. The profile is a request-protocol fact for one
Provider + Model + Endpoint identity. It does not define Veyra Agent
semantics; those remain AgentSemanticPlanV1 → SemanticPlanCompiler →
AgentBlueprint / AgentSource.

Known Moonshot hosts send `response_format.type=json_schema` with the
committed AgentSemanticPlanV1 JSON Schema after the Moonshot MFJS
projection. A single `json_object` fallback is allowed only when that
profile permits it and the provider rejects the schema/`response_format`
itself. Unknown OpenAI-compatible hosts fail closed to `json_object` with
no MFJS projection and no schema fallback. 401, 403, 429, unknown 4xx and
5xx do not fallback and do not infer `strict_json_schema=false`. Markdown
scraping is forbidden. Thinking-model `reasoning_content` may be retained
only inside one in-memory generation/repair request chain when required by the
provider protocol. It is never persisted in Factory messages, SQLite, logs, or
Agent source.

Kimi K3 always uses thinking mode. The client sends `reasoning_effort` only
when the capability profile declares it (`low`, `high`, `max`), omits fixed
sampling parameters, and applies a Veyra-owned completion-token bound rather
than the provider's very large default. Structured Output parses only final
`message.content`. Each repair request replays the complete prior assistant
message required by the provider protocol, including ephemeral
`reasoning_content`, then discards that reasoning data when the generation chain
ends.

### 6.4.1 ProviderCapabilityProfile

Factory structured output is a declared capability of one Provider + Model +
Endpoint, not an implicit Moonshot assumption and not a Veyra Agent contract.

`GET /api/v1/factory/status.capability_profile` is keyed by `provider_id`,
`model`, `endpoint_kind`, a `base_url` fingerprint (scheme+host+port+path,
never query strings or credentials), and `probe_version`. `/v1/models`
listing only proves a model id is visible. It is not evidence of strict JSON
Schema, `json_object`, `reasoning_effort`, or any schema keyword.

A cached profile is reused for ordinary Builder generate. Probe is synthetic
only (`ok: boolean`, no Project / Knowledge / Files / Conversation / user
prompt) and runs on explicit Recheck (`POST /api/v1/factory/capability-probe`),
not every Builder turn. Probe order is bounded: minimal strict JSON Schema,
then `json_object` only after `schema_incompatible` or
`response_format_unsupported`. 401/403/429/5xx/unknown 4xx stop probing and
leave prior capability truth unchanged (`429` → `status=inconclusive`, never
unsupported).

Static host defaults remain the generate strategy until a matching probe
exists:

| Host | Family | Generate format | Schema profile | `json_object` fallback | `reasoning_effort` |
| --- | --- | --- | --- | --- | --- |
| `api.moonshot.cn`, `api.moonshot.ai`, and their subdomains | `moonshot` | `json_schema` strict | `mfjs` | yes, once, schema/`response_format` 400 only | sent |
| any other OpenAI-compatible base URL | `openai_compatible` | `json_object` | `unknown` | no | omitted |

After a successful probe, generate follows `strict_json_schema_support` then
`json_object_support`. Both unsupported is a typed
`factory_structured_output_unsupported` failure. The Moonshot MFJS projection
of AgentBlueprint remains a compatibility bridge, not the default
provider-facing contract. Probe targets SemanticPlan-sized structured output,
not a full AgentBlueprint schema.

A lookalike host such as `api.moonshot.example` is not Moonshot. Same model
name on a different endpoint fingerprint is a different profile.

### 6.4.2 BuilderHarnessReceipt

A receipt is the safe execution evidence of one Builder model invocation.
It is not a second `ProviderCapabilityProfile`, not an operation timeline,
not a chat message, and not a request archive.

`GET /api/v1/projects/{project_id}/builder/conversations/{conversation_id}/operations/{operation_id}`
includes `receipts`. The same list is also available at
`.../operations/{operation_id}/receipts`. Lookups are Project-scoped: a
receipt_id alone is not a global key. Cross-project reads 404.

Desktop Activity shows collapsed “Build details” / 「构建详情」from those
receipts. Chat does not render receipt bubbles. Hashes stay under Technical
details. Operations with no model call show no Provider section rather than
an error.

Receipts copy only the profile facts used for that invocation (`provider_id`,
`model`, `endpoint_kind`, status/source, `schema_profile`, structured mode).
They do not clone the profile row. Recheck updates the live profile cache
only.

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
The Platform Builder Provider is deployment-owned: it is used for Builder Chat,
intent detection, Semantic Plan generation, repair, and Proposal generation. It
is never exposed through the local User Credential API. User Runtime Providers
are local credential metadata plus a device-system secret, and are selected by a
Project/Agent binding slot. A Runtime resolver applies the precedence
`explicit Agent binding → Project binding → User default → missing`.

`provider_credentials` stores only local metadata (`provider_type`, label, base
URL, status, `credential_scope`, capabilities, masked hint, timestamps and an
opaque `secret_ref`). The actual API key is stored in the device system
credential service through the existing
`SecretStore`; it is never stored in SQLite, Agent source, Project YAML,
Proposals, Builder events, Run evidence, exports, or Community payloads.
`runtime_bindings` stores the local Project/Agent binding slot and model ID.
This is a call mapping, not Agent source. Studio Model/Agent node inspectors
map `model_ref` (currently `model.primary`) onto a User Runtime Provider and
model ID. The node keeps the slot; the API key never enters Agent YAML,
Draft, or the inspector form. Disabled, invalid, deleted, or missing
credentials cannot resolve for a Run.

The Desktop Settings Provider Credentials surface supports Add/Test & Save,
replace, enable/disable, delete, and User default selection. Validation uses a
provider model-list request only; it never sends a generation prompt. The
Platform credential is not editable from this surface. A Builder `create_agent`
operation performs a durable Runtime preflight before Semantic generation: it
waits for a User credential or explicit credential/model binding confirmation.
Ordinary chat and non-Runtime operations remain usable without a Runtime key.

Workflow has a matching no-effect preflight at
`GET /api/v1/projects/{project_id}/workflows/{workflow_id}/runtime-readiness`.
It resolves the immutable AgentCall targets, checks each pinned Agent's model
and dependency readiness, verifies that Workflow permissions cover child
permissions, and checks the Project node limit. It never commits a Workflow
version, contacts the model provider, or starts a child Run. Workflow execution
applies the same permission containment check, including
`shell_workspace_only`.

Local development tests may inject a Runtime transport. The normal Local app does
not use `MOONSHOT_API_KEY` or the Platform Builder secret as an implicit Runtime
fallback. User Runtime execution requires an active credential and binding (or
an explicit User default); production and release modes have the same boundary.

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
| Agent | Canvas | Declares its own inputs and outputs. Default skeleton Start → Model → Output plus an optional canvas Note. Left palette projects Model, Project-bound Tool and Custom Component nodes, Condition, Transform, HumanApproval, Verifier, Knowledge bindings, and Notes. AgentCall is not an Agent node. Right inspector edits parameters and shows component type; canvas titles prefer semantic labels. Bottom panel test-runs. |
| Workflow | Same Canvas shell | Declares its own inputs and outputs. Palette is AgentCall plus control flow (Condition, Transform, HumanApproval, Verifier). No Model or Tool nodes. Blank Workflows also receive a default optional Note. Existing Agents are not renamed into Workflows. |
| Component | Resource Catalog + Project Resource Library | Global Catalog owns platform resources; Project Resource Library owns selected versions and usage, plus Project-owned Custom Component drafts and immutable lifecycle. Primitive vs composite stays a required class. Not a separate flowchart editor. |
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
  Files             collection page; indexed Project files
  Runs              collection page; Agent and Workflow run history
```

Do not list Agents as bare children of a Project. Agent and Workflow are
siblings. Knowledge documents nest under Knowledge; Files and Runs stay
collection leaves because they are indexes, not Canvas instances. Clicking
Files opens `#/projects/:projectId/files`. Clicking Runs opens
`#/projects/:projectId/runs`. The header History control still opens
`#/runs` on the home workspace and `#/projects/:projectId/runs` inside a
Project.

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

1. **Agent is not renamed to Workflow, and Agent is not a DAG.** An Agent is a
   runnable capability (model, instructions, tools, knowledge, skills,
   policies, typed I/O, bounded runtime loop). New Builder-created Agents use
   `execution_kind=loop`. The Agent Canvas is a **capability map**, not
   Start→Condition→Model→Output. A Workflow is a separate source that
   orchestrates immutable Agent versions via AgentCall plus typed dataflow and
   control flow. AgentCall is Workflow-only and pins `agent_id@version_id`.
   Typed ports, `data_edges`, structural simulation, and quality validation
   belong to Workflow infrastructure; Artifact / multimodal types remain shared.
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
5. **Studio Test is Draft; Agent App is a committed version.** Tree click
   opens Studio (`/design`). Open App is a secondary action to the Agent
   App. Never run Draft from the App, and never auto-commit an unconfirmed
   Draft to open the App. Legacy Agents without `interaction_mode` default
   to `auto`.

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
Left      Agent (loop): Tools / Knowledge / Skills / Policies (capability map).
          Agent (legacy graph): Model / Tool / Condition / Transform /
          HumanApproval / Verifier. AgentCall never appears on the Agent palette.
          Workflow: Agents / Tools / Logic / Human / Data / Output.
          MCP appears under Tools, not as its own product class.
          Canvas notes are UI-only annotations; they are default, not required,
          and they are not Flow nodes.
Center    Agent Canvas is a capability map. Workflow Canvas is a typed DAG.
          Hover a Workflow connection to insert a node.
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
Model node start evidence may include provider type, model ID, `credential_type=user`,
and a safe credential alias; it never includes the secret or secret reference value.

### 8.4 Secret broker

- Agent contains `secretRef`, never a value.
- Values live in the device system credential service (macOS Keychain, Windows
  Credential Manager, or Linux Secret Service/KWallet through the system-keyring
  adapter).
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
- `provider_credentials` (local User Runtime credential metadata only)
- `runtime_bindings` (local Project/Agent slot → credential/model binding)
- `project_artifacts` (Project-scoped ArtifactRef metadata; bytes stay in the object store)

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
- `builder_conversations`
- `builder_messages`
- `builder_operations`
- `runtime_connections`
- `external_agent_sessions`
- `workspace_locks`

All frontend controls first write a durable `run_command`; they do not directly manipulate executors.

`agent_conversations` are Runtime Agent chat, bound to an existing Agent version.
`builder_conversations` are Project Chat construction history. They are not the
same entity as Runtime Run History (`runs` / `run_events`). Factory
`factory_sessions` remain the create-agent subflow under a Builder operation.

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

Desktop tokens live in the host system credential service, not local SQLite
plaintext. SMTP credentials
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

The Community registry also has a Plugin Pack lane. Authenticated publishers
upload a declarative `.vplugin.zip`; Community keeps an immutable content hash,
public Skill/MCP manifest summary, version history, and optional moderation
state. Public download returns the original bytes, but Community never starts
an MCP process or interprets Skill instructions. Desktop downloads can be sent
straight to the local Plugin Pack importer for quarantine and explicit activation.

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
- `POST /api/v1/agent-imports` (analyze YAML, folder path, or ZIP)
- `GET /api/v1/agent-imports/{import_id}` (compatibility preview)
- `POST /api/v1/agent-imports/{import_id}/apply` (create a local Agent Draft)

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
- `GET /api/v1/plugins`
- `POST /api/v1/plugins/import` (quarantined declarative `.vplugin.zip`)
- `POST /api/v1/plugins/{plugin_id}/versions/{version}/activate`
- `POST /api/v1/plugins/{plugin_id}/versions/{version}/disable`
- `POST /api/v1/plugins/{plugin_id}/versions/{version}/uninstall` (moves to recoverable trash)
- `GET /api/v1/plugins/trash`
- `POST /api/v1/plugins/trash/{trash_id}/restore`
- `GET /api/v1/plugins/{plugin_id}/versions/{version}/download`
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
- `GET /api/v1/registry/plugins`
- `GET /api/v1/registry/plugins/{owner_handle}/{slug}`
- `GET /api/v1/registry/plugins/{owner_handle}/{slug}/versions`
- `GET /api/v1/registry/plugins/{owner_handle}/{slug}/versions/{version}`
- `GET /api/v1/registry/plugins/{owner_handle}/{slug}/versions/{version}/download`
- `POST /api/v1/registry/plugins` (authenticated multipart Plugin Pack publish)
- `GET /api/v1/registry/plugins/moderation/queue`
- `POST /api/v1/registry/plugins/{owner_handle}/{slug}/versions/{version}/moderate`
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
- declarative Plugin Pack import, quarantine, review, and explicit activation
- generic external Agent YAML/folder/ZIP import with compatibility preview
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
- Plugin Pack versions and local re-import
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

## Project Sync Foundation

Veyra treats a Project as one logical identity rather than separate Local and
Cloud products. The Desktop creates a Local Working Copy first and uses its
UUIDv7 `project_id` when it ensures a Cloud Replica. Cloud persistence is a
server-side account-owned replica; it is not a second Project shown in the
Project picker and it does not access the local Project directory.

Project Sync Foundation #1 synchronizes only Project metadata: identity, name,
description, lifecycle state, and schema metadata. Agent and Workflow
definitions, Knowledge, Files, Runs, Chat, Provider Credentials, and Runtime
Bindings remain outside this slice. Local sync state is stored in the
`project_sync_states` SQLite table and records the Cloud revision, metadata
hash, pending operation, and conflict information. It never stores a Cloud
session or secret.

The local sidecar does not read the Cloud HttpOnly session cookie. A Desktop
ProjectSyncCoordinator coordinates the 8771 Local API and authenticated 8772
Cloud API. Create is Local-first: Cloud failure leaves the Project usable and
records `pending_upload`; retry is bounded and event-driven. Cloud mutations
use a monotonic revision and expected revision. A stale push returns a
conflict and never silently overwrites the newer replica.

Cloud payloads must not contain local paths, device identifiers, Keychain
references, credential IDs, API keys, or Local Runtime configuration. Provider
secrets and device-local Runtime bindings remain outside Project Sync.

## Project Artifact Sync #2

Project Artifact Sync extends the same Logical Project and project_id. It uses
one portable Project Artifact envelope with a domain kind, stable artifact ID,
canonical payload, content hash, revision, immutable flag, deleted flag, and
schema version. V1 kinds are agent, agent_version, workflow, custom_component,
and knowledge_metadata. Files, raw Knowledge content, Runs, Chat, Credentials,
Runtime Binding implementations, and Cloud Runtime are not Artifact Sync
payloads.

Cloud stores envelopes in project_artifacts, owner-scoped through the Cloud
Project Replica. Mutable artifacts use their own optimistic revision; an
immutable Agent version is idempotent only when its identity and hash match.
Reusing an immutable ID with different content is an integrity conflict. A
deleted mutable artifact is represented by a tombstone rather than a row
delete. The Project revision remains separate from per-artifact revisions.

Local discovery serializes the existing AgentSource, WorkflowSource,
CustomComponentDefinition, immutable Agent version, and Knowledge metadata
contracts. It never serializes local paths, raw Knowledge content, credentials,
or Runtime state. Pulls pass through the existing domain validators and
canonical writers; Cloud data is treated as untrusted even when owned by the
same account.

## Cloud Files & Library Foundation #1

Cloud Files are a separate private Account Library domain. A `CloudFile` has a
server-issued UUIDv7 `file_id`, owner identity, display filename, MIME metadata,
byte size, SHA-256, lifecycle state, and timestamps. Metadata is stored in the
Cloud/Community database lineage (`cloud_files`); bytes are never stored in the
primary database. `ProjectFileReference` rows connect one account-owned file
to one or more Cloud Project replicas without copying the blob.

The Cloud Host exposes authenticated list, upload, metadata get, streaming
download, delete, Project attach, Project detach, and Project File list
operations. Upload is an explicit multipart action only; opening a Project
does not scan or upload its Local directory. Ownership is checked for every
operation and a non-owner receives a non-disclosing 404. Library deletion is
separate from Project detach and returns `file_in_use` while any Project
reference remains.

`BlobStore` is intentionally narrow: stream put, open/read, stat, delete, and
readiness. The development/self-host adapter is `FilesystemBlobStore`, whose
root is a server-owned Cloud data directory configured by Cloud settings, not a
Desktop Project root. The protocol is the seam for a future S3, MinIO, or R2
adapter; this slice does not add a production cloud SDK.

Cloud File responses never expose storage keys, server paths, Local Project
paths, credentials, sessions, or secrets. Downloads stream as safe
`Content-Disposition: attachment` responses with `nosniff`, length, and hash
headers. Local materialization is an explicit Local API operation restricted to
safe `assets/` or `knowledge/` paths, with traversal/symlink checks and
hash/size verification.

Knowledge remains Local-first and is not indexed by Cloud Files. An explicit
Cloud File source reference may be stored as Knowledge metadata and carried by
the existing metadata-only Project Artifact envelope. It is a `cloud_file`
identity seam, not raw source bytes and not an index-success claim. Project
Artifact Sync continues to exclude Cloud File bytes.

Web and Desktop share the Cloud File contracts and connected-account client;
this foundation adds no new page, Sidebar entry, Cloud Library redesign,
Community publication, or Cloud Runtime behavior.

## Existing Chat Server Authority & Cross-Client Persistence #1

Veyra's existing Chat is not duplicated as a second Cloud Chat product. The
account-owned Conversation and Message domain is persisted in the Cloud Host
database lineage (`conversations`, `conversation_messages`). Web and Desktop
consume the same server `conversation_id` and `message_id`; Recent
Conversations is a view of that server list when the account session is
available.

The server Conversation record keeps the optional `project_id` and `agent_id`,
title, status, revision, and activity timestamps. Project binding is accepted
only when the Cloud Project belongs to the same account. Message append is
sequence-backed and locks the Conversation row on the server; a client-supplied
message ID makes network retry idempotent. Reusing that ID with different
content is a conflict, not a second Message.

Builder operation and event references are stored beside the Conversation so
`operation_id`, `proposal_id`, retry lineage, and event identity survive the
authority transition. The existing Builder UI, Proposal identity, Confirm,
Reject, and Apply semantics are unchanged. Desktop Local Host remains the
execution bridge for the current Local Project Working Copy; it is not a
second authoritative Chat store. During the transition, a thin Desktop
bridge imports the existing Local Builder snapshot to the server by stable
identities and leaves the old Local rows intact as legacy/cache execution
state.

Message attachments contain only an owned `cloud_file_id` plus server-derived
metadata snapshots. Bytes remain in the Cloud File domain. Conversation
payloads reject credentials, secrets, session tokens, Keychain references,
local paths, and storage keys. The server never accesses `8771`, a Tauri API,
or a Desktop filesystem.

Offline Chat may show the Local cached view or an unavailable state, but the
Desktop Local Project, Studio, Git, Shell, MCP, and Local Runtime do not become
dependent on the Chat server. No Chat layout, composer, Sidebar, or new Chat
page is introduced by this slice.

## Server Execution Plane V1

The Cloud Host is the execution authority for Web and Desktop. The domains are
separate: Platform Provider credentials serve Builder/intent/semantic/proposal
generation; User Runtime Credentials serve Cloud Agent Runs; Device
Credentials remain Local Host state. Cloud Runtime never reads the Platform
Builder key, Local SQLite, a Project `.env`, or `DeviceSecretStore` as a
fallback.

Cloud credential metadata and binding slots are stored in
`cloud_credentials` and `cloud_runtime_bindings`. The API key is stored only
as an authenticated AES-GCM ciphertext envelope; the deployment master key is
outside SQLite (`VEYRA_CLOUD_CREDENTIAL_MASTER_KEY` in production). No
plaintext secret is returned by API, written to AgentSource, Project Artifact,
Proposal, Conversation, Run input/result, event, receipt, or evidence. Runtime
binding resolution is Agent > Project > account default > missing, and
disabled/unverified/deleted credentials cannot resolve.

Cloud Runs load an exact immutable `agent_version` and verify AgentSource,
source/behavior/lock hashes, Project ownership, and Cloud File references.
V1 reuses the existing Agent contracts for Start, Model, Transform, Condition,
Verifier, Output, and HumanApproval. Local-only Tool nodes fail closed with
`local_host_required`; the Cloud Host does not access Desktop filesystem,
Shell, Git, MCP, or Local Runtime state. Cloud Run records, ordered events,
SSE cursors, idempotent commands, approvals, and checkpoints are durable.
Approval pauses as `waiting`; stop cancels, retry creates a child attempt,
resume requires an explicit checkpoint, and a restart marks lost `running`
attempts `interrupted` without rewriting history.

Forward-only migrations are `community_0014_server_credentials` and
`community_0015_cloud_runs`. Web and Desktop share the Cloud contracts and
connected-account API; the existing Settings Provider card prefers Cloud
Credentials without introducing a new page or redesign. Workflow provider
routing, shared/team vaults, billing, quotas, load balancing, and Community
credential sync remain out of scope.
