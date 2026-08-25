import { ArrowUpRight, Bot, Boxes, CircleCheck, FolderKanban, Plus, Sparkles, Wrench } from "lucide-react";
import { projectRoutePaths, type AgentSummary, type ProjectSummary } from "@veyra/api-contracts";
import { Button, LinkButton, MetricCard, Panel, SectionHeading, StatusBadge, Tag } from "@veyra/ui";

export const projects: ProjectSummary[] = [
  { id: "signal-review", name: "Signal Review", description: "Turn incoming work into a traceable review queue.", state: "active", agentCount: 3, activeRuns: 2, updatedAt: "12 min ago" },
  { id: "release-room", name: "Release Room", description: "Keep release preparation visible from draft to verified result.", state: "ready", agentCount: 2, activeRuns: 0, updatedAt: "Yesterday" },
];

export const agents: AgentSummary[] = [
  { id: "reviewer", projectId: "signal-review", name: "Review Companion", description: "Collect evidence and prepare a concise review brief.", state: "ready", version: "v0.4", componentCount: 7, lastRun: "14 min ago" },
  { id: "release-check", projectId: "release-room", name: "Release Check", description: "Walk a release checklist and pause at approval gates.", state: "running", version: "v0.2", componentCount: 5, lastRun: "Now" },
  { id: "workspace-guide", projectId: "signal-review", name: "Workspace Guide", description: "Explain the next safe action for a project workspace.", state: "draft", version: "Draft", componentCount: 3, lastRun: "Not run" },
];

const toneForState = (state: ProjectSummary["state"] | AgentSummary["state"]) => state === "active" || state === "ready" ? "good" : state === "running" ? "warn" : "neutral";

export function ProjectsPage() {
  return (
    <div className="page-stack">
      <div className="page-intro">
        <div>
          <span className="ui-eyebrow">Control surface</span>
          <h2>Make work repeatable.</h2>
          <p>Projects keep Agent versions, workspaces, runs, and evidence together.</p>
        </div>
        <div className="intro-actions">
          <LinkButton href={projectRoutePaths.factory(projects[0].id)} icon={Sparkles} variant="primary">Start from a requirement</LinkButton>
          <Button icon={Plus}>New project</Button>
        </div>
      </div>

      <section className="hero-panel">
        <div className="hero-copy">
          <span className="hero-kicker">Veyra workspace</span>
          <h2>Build with a clear path from idea to verified run.</h2>
          <p>Keep definitions inspectable, make control visible, and leave every meaningful result with a reason to trust it.</p>
          <div className="hero-actions"><LinkButton href={projectRoutePaths.agentDesign("signal-review", "reviewer")} icon={Wrench} variant="secondary">Open Studio</LinkButton><LinkButton href="#/monitor" icon={ArrowUpRight} variant="ghost">See active work</LinkButton></div>
        </div>
        <div className="hero-diagram" aria-label="Build, run, verify flow">
          <div><span>01</span><strong>Define</strong><small>source</small></div>
          <div><span>02</span><strong>Run</strong><small>events</small></div>
          <div><span>03</span><strong>Verify</strong><small>evidence</small></div>
        </div>
      </section>

      <div className="metric-grid">
        <MetricCard label="Projects" value="2" detail="1 active this week" />
        <MetricCard label="Agent versions" value="6" detail="2 need review" tone="good" />
        <MetricCard label="Active runs" value="2" detail="1 waiting for approval" tone="warn" />
        <MetricCard label="Verified results" value="18" detail="Across the last 30 days" tone="good" />
      </div>

      <div className="content-grid two-thirds">
        <Panel>
          <SectionHeading eyebrow="Projects" title="Current work" detail="Each project owns its source, runs, and workspace boundary." action={<LinkButton href={projectRoutePaths.factory(projects[0].id)} icon={Plus} size="sm">Add</LinkButton>} />
          <div className="project-list">
            {projects.map((project) => <a className="project-row" href={projectRoutePaths.project(project.id)} key={project.id}>
              <span className="row-icon"><FolderKanban size={18} aria-hidden="true" /></span>
              <span className="row-copy"><strong>{project.name}</strong><small>{project.description}</small><em>{project.agentCount} agents · {project.activeRuns} active runs · updated {project.updatedAt}</em></span>
              <StatusBadge label={project.state} tone={toneForState(project.state)} />
              <ArrowUpRight size={16} className="row-arrow" aria-hidden="true" />
            </a>)}
          </div>
        </Panel>

        <Panel>
          <SectionHeading eyebrow="Attention" title="Next actions" />
          <div className="attention-list">
            <div className="attention-item"><span className="attention-icon good"><CircleCheck size={16} /></span><span><strong>Review Companion is ready</strong><small>Commit the draft when the schema looks right.</small></span></div>
            <div className="attention-item"><span className="attention-icon warn"><Bot size={16} /></span><span><strong>Release Check is waiting</strong><small>One approval gate needs a decision.</small></span></div>
            <div className="attention-item"><span className="attention-icon"><Boxes size={16} /></span><span><strong>Two components are unlocked</strong><small>Pin versions before the next run.</small></span></div>
          </div>
        </Panel>
      </div>

      <Panel>
        <SectionHeading eyebrow="Library" title="Agent versions" detail="Portable definitions stay separate from mutable run state." action={<LinkButton href={projectRoutePaths.project("signal-review")} size="sm">View all</LinkButton>} />
        <div className="agent-grid">
          {agents.map((agent) => <a className="agent-card" href={projectRoutePaths.agentDesign(agent.projectId, agent.id)} key={agent.id}><div className="agent-card-top"><span className="row-icon"><Bot size={17} /></span><StatusBadge label={agent.state} tone={toneForState(agent.state)} /></div><strong>{agent.name}</strong><p>{agent.description}</p><div className="agent-card-meta"><Tag>{agent.version}</Tag><span>{agent.componentCount} components</span><span>{agent.lastRun}</span></div></a>)}
        </div>
      </Panel>
    </div>
  );
}
