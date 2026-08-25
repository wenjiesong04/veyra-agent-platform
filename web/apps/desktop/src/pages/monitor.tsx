import { Check, CircleStop, Clock3, ExternalLink, MessageSquare, Pause, ShieldCheck, SkipForward } from "lucide-react";
import { Button, LinkButton, Panel, SectionHeading, StatusBadge, Tag } from "@veyra/ui";

const timeline = [
  { time: "14:08:04", title: "Run queued", detail: "Release Check v0.2 pinned", state: "verified" as const },
  { time: "14:08:06", title: "Workspace prepared", detail: "Lease acquired for Release Room", state: "verified" as const },
  { time: "14:09:18", title: "Checklist completed", detail: "5 checks returned structured results", state: "verified" as const },
  { time: "14:16:46", title: "Approval requested", detail: "Publish release note?", state: "waiting" as const },
];

export function MonitorPage() {
  return (
    <div className="page-stack">
      <div className="page-intro"><div><span className="ui-eyebrow">Live workflow</span><h2>See the work. Keep the controls.</h2><p>Monitor focuses on what needs attention now: waiting, blocked, stale, and failed work.</p></div><StatusBadge label="1 waiting" tone="warn" /></div>
      <Panel className="monitor-hero"><div><div className="monitor-title"><span className="run-state-icon active"><Pause size={16} /></span><div><h2>Release Check</h2><p>Release Room · run-1042 · version v0.2</p></div></div><div className="monitor-meta"><Tag tone="warn">Waiting for approval</Tag><span><Clock3 size={13} /> running for 08:42</span><span><ShieldCheck size={13} /> verifier pending</span></div></div><div className="monitor-actions"><Button icon={CircleStop} variant="danger">Stop</Button><Button icon={Check} variant="primary">Approve</Button><Button icon={MessageSquare}>Reply</Button></div></Panel>
      <div className="content-grid two-thirds"><Panel><SectionHeading eyebrow="Run canvas" title="Ordered events" detail="The current state is derived from the event stream." /><div className="timeline">{timeline.map((event, index) => <div className="timeline-item" key={event.time}><div className={`timeline-dot ${event.state}`}><Check size={12} /></div>{index < timeline.length - 1 ? <span className="timeline-line" aria-hidden="true" /> : null}<div className="timeline-copy"><span>{event.time}</span><strong>{event.title}</strong><p>{event.detail}</p></div></div>)}</div></Panel><div className="monitor-side"><Panel><SectionHeading eyebrow="Current node" title="Approval gate" /><StatusBadge label="Needs your decision" tone="warn" /><p className="side-detail">The next external write remains paused until a human decision is recorded.</p><div className="button-stack"><Button icon={Check} variant="primary">Approve gate</Button><Button icon={SkipForward}>Reject and stop</Button></div></Panel><Panel><SectionHeading eyebrow="Evidence" title="Verifier state" /><div className="evidence-row"><ShieldCheck size={17} /><span><strong>Not established</strong><small>Verification runs after the gate resolves.</small></span></div><LinkButton href="#/runs/run-1042" icon={ExternalLink} size="sm">Open immutable run</LinkButton></Panel></div></div>
    </div>
  );
}
