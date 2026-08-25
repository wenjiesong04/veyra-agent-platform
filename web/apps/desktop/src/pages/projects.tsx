import { ArrowUpRight, Bot, Boxes, CircleCheck, FolderKanban, Plus, Sparkles, Wrench } from "lucide-react";
import { projectRoutePaths, type AgentSummary, type ProjectSummary } from "@veyra/api-contracts";
import { Button, LinkButton, MetricCard, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";

export const projects: ProjectSummary[] = [
  { id: "signal-review", name: "Signal Review", description: "Turn incoming work into a traceable review queue.", state: "active", agentCount: 3, activeRuns: 2, updatedAt: "12 min ago" },
  { id: "release-room", name: "Release Room", description: "Keep release preparation visible from draft to verified result.", state: "ready", agentCount: 2, activeRuns: 0, updatedAt: "Yesterday" },
];

export const agents: AgentSummary[] = [
  { id: "reviewer", projectId: "signal-review", name: "Review Companion", description: "Collect evidence and prepare a concise review brief.", state: "ready", version: "v0.4", componentCount: 7, lastRun: "14 min ago" },
  { id: "release-check", projectId: "release-room", name: "Release Check", description: "Walk a release checklist and pause at approval gates.", state: "running", version: "v0.2", componentCount: 5, lastRun: "Now" },
  { id: "workspace-guide", projectId: "signal-review", name: "Workspace Guide", description: "Explain the next safe action for a project workspace.", state: "draft", version: "Draft", componentCount: 3, lastRun: "Not run" },
];

export function defaultAgentForProject(projectId: string): AgentSummary | undefined {
  return agents.find((agent) => agent.projectId === projectId);
}

const toneForState = (state: ProjectSummary["state"] | AgentSummary["state"]) => state === "active" || state === "ready" ? "good" : state === "running" ? "warn" : "neutral";

export function ProjectsPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const copy = zh ? {
    controlSurface: "控制面",
    title: "让工作可以重复执行。",
    description: "项目把 Agent 版本、工作区、运行记录和验证证据组织在一起。",
    startRequirement: "从需求开始",
    newProject: "新建项目",
    workspace: "Veyra 工作区",
    pathTitle: "从想法到已验证运行，始终沿着清晰路径。",
    pathDetail: "让定义可检查、控制过程可见，并为每个重要结果留下可信依据。",
    openStudio: "打开 Studio",
    activeWork: "查看正在进行的工作",
    define: "定义",
    run: "运行",
    verify: "验证",
    source: "源定义",
    events: "事件",
    evidence: "证据",
    projects: "项目",
    projectMetric: "本周 1 个活跃项目",
    versions: "Agent 版本",
    versionMetric: "2 个需要复核",
    activeRuns: "运行中",
    runMetric: "1 个等待审批",
    verified: "已验证结果",
    verifiedMetric: "最近 30 天",
    currentWork: "当前项目",
    currentWorkDetail: "每个项目都拥有自己的源定义、运行记录和工作区边界。",
    add: "添加",
    attention: "需要关注",
    nextActions: "下一步",
    readyTitle: "Review Companion 已就绪",
    readyDetail: "确认 schema 后即可保存 Draft 版本。",
    waitingTitle: "Release Check 正在等待",
    waitingDetail: "有一个审批节点需要决定。",
    unlockedTitle: "有两个组件尚未锁定版本",
    unlockedDetail: "下次运行前请固定组件版本。",
    library: "组件库",
    agentVersions: "Agent 版本",
    agentVersionsDetail: "可移植定义与可变运行状态彼此分离。",
    viewAll: "查看全部",
    agents: "个 Agent",
    runs: "个运行中",
    updated: "更新于",
    components: "个组件",
  } : {
    controlSurface: "Control surface",
    title: "Make work repeatable.",
    description: "Projects keep Agent versions, workspaces, runs, and evidence together.",
    startRequirement: "Start from a requirement",
    newProject: "New project",
    workspace: "Veyra workspace",
    pathTitle: "Build with a clear path from idea to verified run.",
    pathDetail: "Keep definitions inspectable, make control visible, and leave every meaningful result with a reason to trust it.",
    openStudio: "Open Studio",
    activeWork: "See active work",
    define: "Define",
    run: "Run",
    verify: "Verify",
    source: "source",
    events: "events",
    evidence: "evidence",
    projects: "Projects",
    projectMetric: "1 active this week",
    versions: "Agent versions",
    versionMetric: "2 need review",
    activeRuns: "Active runs",
    runMetric: "1 waiting for approval",
    verified: "Verified results",
    verifiedMetric: "Across the last 30 days",
    currentWork: "Current work",
    currentWorkDetail: "Each project owns its source, runs, and workspace boundary.",
    add: "Add",
    attention: "Attention",
    nextActions: "Next actions",
    readyTitle: "Review Companion is ready",
    readyDetail: "Commit the draft when the schema looks right.",
    waitingTitle: "Release Check is waiting",
    waitingDetail: "One approval gate needs a decision.",
    unlockedTitle: "Two components are unlocked",
    unlockedDetail: "Pin versions before the next run.",
    library: "Library",
    agentVersions: "Agent versions",
    agentVersionsDetail: "Portable definitions stay separate from mutable run state.",
    viewAll: "View all",
    agents: "agents",
    runs: "active runs",
    updated: "updated",
    components: "components",
  };
  const stateLabel = (state: ProjectSummary["state"] | AgentSummary["state"]): string => {
    if (!zh) return state;
    const labels: Record<ProjectSummary["state"] | AgentSummary["state"], string> = {
      active: "活跃",
      paused: "已暂停",
      ready: "就绪",
      running: "运行中",
      draft: "草稿",
      attention: "需关注",
    };
    return labels[state];
  };
  const projectDetail = (project: ProjectSummary) => zh
    ? ({
      "signal-review": "把新工作整理成可追踪的评审队列。",
      "release-room": "让发布准备从草稿到验证结果始终清晰可见。",
    } as const)[project.id as "signal-review" | "release-room"] ?? project.description
    : project.description;
  const agentDetail = (agent: AgentSummary) => zh
    ? ({
      reviewer: "收集证据并生成简洁的评审简报。",
      "release-check": "执行发布检查清单，并在审批节点暂停。",
      "workspace-guide": "说明项目工作区下一步可安全执行的操作。",
    } as const)[agent.id as "reviewer" | "release-check" | "workspace-guide"] ?? agent.description
    : agent.description;

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">{copy.controlSurface}</span>
          <h2>{copy.title}</h2>
          <p>{copy.description}</p>
        </div>
        <div className="intro-actions">
          <LinkButton href={projectRoutePaths.factory(projects[0].id)} icon={Sparkles} variant="primary">{copy.startRequirement}</LinkButton>
          <Button icon={Plus}>{copy.newProject}</Button>
        </div>
      </div>

      <section className="hero-panel">
        <div className="hero-copy">
          <span className="hero-kicker">{copy.workspace}</span>
          <h2>{copy.pathTitle}</h2>
          <p>{copy.pathDetail}</p>
          <div className="hero-actions"><LinkButton href={projectRoutePaths.agentDesign("signal-review", "reviewer")} icon={Wrench} variant="secondary">{copy.openStudio}</LinkButton><LinkButton href="#/monitor" icon={ArrowUpRight} variant="ghost">{copy.activeWork}</LinkButton></div>
        </div>
        <div className="hero-diagram" aria-label="Build, run, verify flow">
          <div><span>01</span><strong>{copy.define}</strong><small>{copy.source}</small></div>
          <div><span>02</span><strong>{copy.run}</strong><small>{copy.events}</small></div>
          <div><span>03</span><strong>{copy.verify}</strong><small>{copy.evidence}</small></div>
        </div>
      </section>

      <div className="metric-grid">
        <MetricCard label={copy.projects} value="2" detail={copy.projectMetric} />
        <MetricCard label={copy.versions} value="6" detail={copy.versionMetric} tone="good" />
        <MetricCard label={copy.activeRuns} value="2" detail={copy.runMetric} tone="warn" />
        <MetricCard label={copy.verified} value="18" detail={copy.verifiedMetric} tone="good" />
      </div>

      <div className="content-grid two-thirds">
        <Panel>
          <SectionHeading eyebrow={copy.projects} title={copy.currentWork} detail={copy.currentWorkDetail} action={<LinkButton href={projectRoutePaths.factory(projects[0].id)} icon={Plus} size="sm">{copy.add}</LinkButton>} />
          <div className="project-list">
            {projects.map((project) => <a className="project-row" href={projectRoutePaths.project(project.id)} key={project.id}>
              <span className="row-icon"><FolderKanban size={18} aria-hidden="true" /></span>
              <span className="row-copy"><strong>{project.name}</strong><small>{projectDetail(project)}</small><em>{project.agentCount} {copy.agents} · {project.activeRuns} {copy.runs} · {copy.updated} {project.updatedAt}</em></span>
              <StatusBadge label={stateLabel(project.state)} tone={toneForState(project.state)} />
              <ArrowUpRight size={16} className="row-arrow" aria-hidden="true" />
            </a>)}
          </div>
        </Panel>

        <Panel>
          <SectionHeading eyebrow={copy.attention} title={copy.nextActions} />
          <div className="attention-list">
            <div className="attention-item"><span className="attention-icon good"><CircleCheck size={16} /></span><span><strong>{copy.readyTitle}</strong><small>{copy.readyDetail}</small></span></div>
            <div className="attention-item"><span className="attention-icon warn"><Bot size={16} /></span><span><strong>{copy.waitingTitle}</strong><small>{copy.waitingDetail}</small></span></div>
            <div className="attention-item"><span className="attention-icon"><Boxes size={16} /></span><span><strong>{copy.unlockedTitle}</strong><small>{copy.unlockedDetail}</small></span></div>
          </div>
        </Panel>
      </div>

      <Panel>
        <SectionHeading eyebrow={copy.library} title={copy.agentVersions} detail={copy.agentVersionsDetail} action={<LinkButton href={projectRoutePaths.project("signal-review")} size="sm">{copy.viewAll}</LinkButton>} />
        <div className="agent-grid">
          {agents.map((agent) => <a className="agent-card" href={projectRoutePaths.agentDesign(agent.projectId, agent.id)} key={agent.id}><div className="agent-card-top"><span className="row-icon"><Bot size={17} /></span><StatusBadge label={stateLabel(agent.state)} tone={toneForState(agent.state)} /></div><strong>{agent.name}</strong><p>{agentDetail(agent)}</p><div className="agent-card-meta"><Tag>{agent.version}</Tag><span>{agent.componentCount} {copy.components}</span><span>{agent.lastRun}</span></div></a>)}
        </div>
      </Panel>
    </div>
  );
}
