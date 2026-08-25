import { ArrowRight, Check, FileCode2, LockKeyhole, Sparkles } from "lucide-react";
import { projectRoutePaths } from "@veyra/api-contracts";
import { Button, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge, Tag, useLocale } from "@veyra/ui";
import { useState } from "react";
import { NotFoundPage } from "./not-found";
import { defaultAgentForProject, projects } from "./projects";

const initialPrompt = "Create a review Agent that gathers evidence, pauses before publishing, and leaves a verifiable result.";
const factoryCopy = {
  zh: {
    prompt: "创建一个收集证据、发布前暂停，并留下可验证结果的评审 Agent。", missingProject: "返回项目", eyebrow: "需求生成草稿", title: "告诉 Factory 要完成什么。", description: "结果是一份类型化草稿，你可以在它成为不可变版本前检查。", ready: "草稿就绪", waiting: "等待需求", describe: "01 / 描述", what: "这个 Agent 应该做什么？", detail: "让需求保持具体。权限和验证始终由你控制。", requirement: "需求", noCredentials: "源草稿不包含凭据。", generate: "生成草稿", evidence: "先收集证据", approval: "审批门", localRun: "本机运行", inspect: "02 / 检查", outline: "草稿概要", openStudio: "打开 Studio", draftStatus: "草稿 / 行为尚未提交", schema: "Schema 有效", collect: "收集证据", collectDetail: "从选定的项目范围读取。", prepare: "准备评审简报", prepareDetail: "使用来源引用总结发现。", request: "请求审批", requestDetail: "任何外部写入前暂停。", next: "下一步", nextDetail: "打开 Studio，编辑表单、Canvas 或源码表示。", emptyTitle: "概要会显示在这里。", emptyDetail: "生成草稿后，可以在保存前查看节点、权限和验证点。", boundary: "权限边界保持明确。", boundaryDetail: "Factory 可以建议图，但不能授予权限、执行工作或声称已验证。",
  },
  en: {
    prompt: initialPrompt, missingProject: "Back to Projects", eyebrow: "Requirement to draft", title: "Give the Factory a job to shape.", description: "The result is a typed draft you can inspect before it becomes an immutable version.", ready: "Draft ready", waiting: "Waiting for requirement", describe: "01 / Describe", what: "What should this Agent do?", detail: "Keep the requirement concrete. Permissions and verification remain under your control.", requirement: "Requirement", noCredentials: "No credentials are included in the source draft.", generate: "Generate draft", evidence: "Evidence first", approval: "Approval gate", localRun: "Local run", inspect: "02 / Inspect", outline: "Draft outline", openStudio: "Open Studio", draftStatus: "Draft / behavior not yet committed", schema: "Schema valid", collect: "Collect evidence", collectDetail: "Read from the selected project scope.", prepare: "Prepare a review brief", prepareDetail: "Summarize findings with source references.", request: "Request approval", requestDetail: "Pause before any external write.", next: "Next", nextDetail: "Open Studio to edit the Form, Canvas, or Source representation.", emptyTitle: "Your outline appears here.", emptyDetail: "Generate a draft to see nodes, permissions, and verification points before saving.", boundary: "Authority stays explicit.", boundaryDetail: "The Factory can suggest a graph. It cannot grant permissions, execute work, or claim verification.",
  },
} as const;

export function FactoryPage({ projectId }: { projectId: string }) {
  const { locale } = useLocale();
  const copy = factoryCopy[locale];
  const [prompt, setPrompt] = useState<string>(copy.prompt);
  const [submitted, setSubmitted] = useState(false);
  const [generating, setGenerating] = useState(false);
  const project = projects.find((item) => item.id === projectId);
  const scopedAgent = defaultAgentForProject(projectId);

  if (!project || !scopedAgent) return <NotFoundPage backHref="#/projects" backLabel={copy.missingProject} />;

  const generateDraft = () => {
    if (!prompt.trim()) return;
    setGenerating(true);
    window.setTimeout(() => {
      setGenerating(false);
      setSubmitted(true);
    }, 280);
  };

  return (
    <div className="page-stack">
      <div className="page-intro">
        <div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div>
        <StatusBadge label={submitted ? copy.ready : copy.waiting} tone={submitted ? "good" : "neutral"} />
      </div>

      <div className="factory-layout">
        <Panel className="factory-prompt-panel">
          <SectionHeading eyebrow={copy.describe} title={copy.what} detail={copy.detail} />
          <label className="field-label" htmlFor="factory-prompt">{copy.requirement}</label>
          <textarea id="factory-prompt" className="factory-textarea" value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={8} />
          <div className="factory-form-footer"><span><LockKeyhole size={14} />{copy.noCredentials}</span><Button icon={Sparkles} variant="primary" onClick={generateDraft} disabled={!prompt.trim() || generating}>{copy.generate}</Button></div>
          <div className="prompt-chips"><Tag>{copy.evidence}</Tag><Tag>{copy.approval}</Tag><Tag>{copy.localRun}</Tag></div>
        </Panel>

        <Panel className="factory-result-panel">
          <SectionHeading eyebrow={copy.inspect} title={copy.outline} action={<LinkButton href={projectRoutePaths.agentDesign(project.id, scopedAgent.id)} icon={ArrowRight} size="sm">{copy.openStudio}</LinkButton>} />
          {generating ? <LoadingState label={locale === "zh" ? "正在编译类型化草稿…" : "Compiling a typed draft…"} /> : submitted ? <div className="draft-outline">
            <div className="draft-header"><span className="draft-icon"><FileCode2 size={18} /></span><span><strong>{scopedAgent.name}</strong><small>{copy.draftStatus}</small></span><StatusBadge label={copy.schema} tone="good" /></div>
            <div className="draft-node"><span>01</span><div><strong>{copy.collect}</strong><small>{copy.collectDetail}</small></div><Check size={16} /></div>
            <div className="draft-connector" />
            <div className="draft-node"><span>02</span><div><strong>{copy.prepare}</strong><small>{copy.prepareDetail}</small></div><Check size={16} /></div>
            <div className="draft-connector" />
            <div className="draft-node waiting"><span>03</span><div><strong>{copy.request}</strong><small>{copy.requestDetail}</small></div><LockKeyhole size={16} /></div>
            <div className="draft-note"><strong>{copy.next}</strong><span>{copy.nextDetail}</span></div>
          </div> : <div className="factory-empty"><span><Sparkles size={22} /></span><strong>{copy.emptyTitle}</strong><p>{copy.emptyDetail}</p></div>}
        </Panel>
      </div>

      <Panel className="factory-boundary"><div className="boundary-mark"><LockKeyhole size={17} /></div><div><strong>{copy.boundary}</strong><p>{copy.boundaryDetail}</p></div></Panel>
    </div>
  );
}
