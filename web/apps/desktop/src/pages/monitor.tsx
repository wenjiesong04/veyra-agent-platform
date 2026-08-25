import { Check, CircleStop, Clock3, ExternalLink, MessageSquare, Pause, ShieldCheck, SkipForward } from "lucide-react";
import { Button, LinkButton, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";

const timeline = [
  { time: "14:08:04", title: "Run queued", detail: "Release Check v0.2 pinned", state: "verified" as const },
  { time: "14:08:06", title: "Workspace prepared", detail: "Lease acquired for Release Room", state: "verified" as const },
  { time: "14:09:18", title: "Checklist completed", detail: "5 checks returned structured results", state: "verified" as const },
  { time: "14:16:46", title: "Approval requested", detail: "Publish release note?", state: "waiting" as const },
];

export function MonitorPage() {
  const { locale } = useLocale();
  const copy = locale === "zh" ? {
    eyebrow: "实时工作流", title: "看见工作，也保留控制权。", description: "Monitor 聚焦现在需要关注的内容：等待、阻塞、过期和失败的工作。", waiting: "1 个等待中", run: "运行", runMeta: "Release Room · run-1042 · 版本 v0.2", waitingApproval: "等待审批", running: "已运行 08:42", verifierPending: "验证器待处理", stop: "停止", approve: "批准", reply: "回复", canvas: "运行 Canvas", events: "有序事件", streamDetail: "当前状态由事件流推导。", currentNode: "当前节点", needsDecision: "需要你的决策", approvalGate: "审批门", sideDetail: "下一次外部写入会保持暂停，直到记录人工决策。", approveGate: "批准门", reject: "拒绝并停止", evidence: "证据", verifierState: "验证器状态", notEstablished: "尚未建立", afterGate: "门禁解决后运行验证。", openRuns: "打开不可变运行记录", timeline: ["运行已排队", "工作区已准备", "检查清单已完成", "已请求审批"], timelineDetail: ["Release Check v0.2 已固定", "已为 Release Room 获取租约", "5 项检查返回结构化结果", "发布版本说明？"],
  } : {
    eyebrow: "Live workflow", title: "See the work. Keep the controls.", description: "Monitor focuses on what needs attention now: waiting, blocked, stale, and failed work.", waiting: "1 waiting", run: "Run", runMeta: "Release Room · run-1042 · version v0.2", waitingApproval: "Waiting for approval", running: "running for 08:42", verifierPending: "verifier pending", stop: "Stop", approve: "Approve", reply: "Reply", canvas: "Run canvas", events: "Ordered events", streamDetail: "The current state is derived from the event stream.", currentNode: "Current node", needsDecision: "Needs your decision", approvalGate: "Approval gate", sideDetail: "The next external write remains paused until a human decision is recorded.", approveGate: "Approve gate", reject: "Reject and stop", evidence: "Evidence", verifierState: "Verifier state", notEstablished: "Not established", afterGate: "Verification runs after the gate resolves.", openRuns: "Open immutable runs", timeline: ["Run queued", "Workspace prepared", "Checklist completed", "Approval requested"], timelineDetail: ["Release Check v0.2 pinned", "Lease acquired for Release Room", "5 checks returned structured results", "Publish release note?"],
  };
  return (
    <div className="page-stack">
      <div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><StatusBadge label={copy.waiting} tone="warn" /></div>
      <Panel className="monitor-hero"><div><div className="monitor-title"><span className="run-state-icon active"><Pause size={16} /></span><div><h2>Release Check</h2><p>{copy.runMeta}</p></div></div><div className="monitor-meta"><Tag tone="warn">{copy.waitingApproval}</Tag><span><Clock3 size={13} /> {copy.running}</span><span><ShieldCheck size={13} /> {copy.verifierPending}</span></div></div><div className="monitor-actions"><Button icon={CircleStop} variant="danger">{copy.stop}</Button><Button icon={Check} variant="primary">{copy.approve}</Button><Button icon={MessageSquare}>{copy.reply}</Button></div></Panel>
      <div className="content-grid two-thirds"><Panel><SectionHeading eyebrow={copy.canvas} title={copy.events} detail={copy.streamDetail} /><div className="timeline">{timeline.map((event, index) => <div className="timeline-item" key={event.time}><div className={`timeline-dot ${event.state}`}><Check size={12} /></div>{index < timeline.length - 1 ? <span className="timeline-line" aria-hidden="true" /> : null}<div className="timeline-copy"><span>{event.time}</span><strong>{copy.timeline[index]}</strong><p>{copy.timelineDetail[index]}</p></div></div>)}</div></Panel><div className="monitor-side"><Panel><SectionHeading eyebrow={copy.currentNode} title={copy.approvalGate} /><StatusBadge label={copy.needsDecision} tone="warn" /><p className="side-detail">{copy.sideDetail}</p><div className="button-stack"><Button icon={Check} variant="primary">{copy.approveGate}</Button><Button icon={SkipForward}>{copy.reject}</Button></div></Panel><Panel><SectionHeading eyebrow={copy.evidence} title={copy.verifierState} /><div className="evidence-row"><ShieldCheck size={17} /><span><strong>{copy.notEstablished}</strong><small>{copy.afterGate}</small></span></div><LinkButton href="#/runs" icon={ExternalLink} size="sm">{copy.openRuns}</LinkButton></Panel></div></div>
    </div>
  );
}
