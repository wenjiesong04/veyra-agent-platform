import { ArrowRight, Check, FileCode2, LockKeyhole, Sparkles } from "lucide-react";
import { projectRoutePaths } from "@veyra/api-contracts";
import { Button, LinkButton, LoadingState, Panel, SectionHeading, StatusBadge, Tag } from "@veyra/ui";
import { useState } from "react";
import { NotFoundPage } from "./not-found";
import { defaultAgentForProject, projects } from "./projects";

const initialPrompt = "Create a review Agent that gathers evidence, pauses before publishing, and leaves a verifiable result.";

export function FactoryPage({ projectId }: { projectId: string }) {
  const [prompt, setPrompt] = useState(initialPrompt);
  const [submitted, setSubmitted] = useState(false);
  const [generating, setGenerating] = useState(false);
  const project = projects.find((item) => item.id === projectId);
  const scopedAgent = defaultAgentForProject(projectId);

  if (!project || !scopedAgent) return <NotFoundPage backHref="#/projects" backLabel="Back to Projects" />;

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
        <div><span className="ui-eyebrow">Requirement to draft</span><h2>Give the Factory a job to shape.</h2><p>The result is a typed draft you can inspect before it becomes an immutable version.</p></div>
        <StatusBadge label={submitted ? "Draft ready" : "Waiting for requirement"} tone={submitted ? "good" : "neutral"} />
      </div>

      <div className="factory-layout">
        <Panel className="factory-prompt-panel">
          <SectionHeading eyebrow="01 / Describe" title="What should this Agent do?" detail="Keep the requirement concrete. Permissions and verification remain under your control." />
          <label className="field-label" htmlFor="factory-prompt">Requirement</label>
          <textarea id="factory-prompt" className="factory-textarea" value={prompt} onChange={(event) => setPrompt(event.target.value)} rows={8} />
          <div className="factory-form-footer"><span><LockKeyhole size={14} />No credentials are included in the source draft.</span><Button icon={Sparkles} variant="primary" onClick={generateDraft} disabled={!prompt.trim() || generating}>Generate draft</Button></div>
          <div className="prompt-chips"><Tag>Evidence first</Tag><Tag>Approval gate</Tag><Tag>Local run</Tag></div>
        </Panel>

        <Panel className="factory-result-panel">
          <SectionHeading eyebrow="02 / Inspect" title="Draft outline" action={<LinkButton href={projectRoutePaths.agentDesign(project.id, scopedAgent.id)} icon={ArrowRight} size="sm">Open Studio</LinkButton>} />
          {generating ? <LoadingState label="Compiling a typed draft…" /> : submitted ? <div className="draft-outline">
            <div className="draft-header"><span className="draft-icon"><FileCode2 size={18} /></span><span><strong>{scopedAgent.name}</strong><small>Draft / behavior not yet committed</small></span><StatusBadge label="Schema valid" tone="good" /></div>
            <div className="draft-node"><span>01</span><div><strong>Collect evidence</strong><small>Read from the selected project scope.</small></div><Check size={16} /></div>
            <div className="draft-connector" />
            <div className="draft-node"><span>02</span><div><strong>Prepare a review brief</strong><small>Summarize findings with source references.</small></div><Check size={16} /></div>
            <div className="draft-connector" />
            <div className="draft-node waiting"><span>03</span><div><strong>Request approval</strong><small>Pause before any external write.</small></div><LockKeyhole size={16} /></div>
            <div className="draft-note"><strong>Next</strong><span>Open Studio to edit the Form, Canvas, or Source representation.</span></div>
          </div> : <div className="factory-empty"><span><Sparkles size={22} /></span><strong>Your outline appears here.</strong><p>Generate a draft to see nodes, permissions, and verification points before saving.</p></div>}
        </Panel>
      </div>

      <Panel className="factory-boundary"><div className="boundary-mark"><LockKeyhole size={17} /></div><div><strong>Authority stays explicit.</strong><p>The Factory can suggest a graph. It cannot grant permissions, execute work, or claim verification.</p></div></Panel>
    </div>
  );
}
