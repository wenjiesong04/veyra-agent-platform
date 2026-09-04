import * as React from "react";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { ConversationComposer, ConversationStage } from "./conversation-stage";
import { assembleGreeting, ConversationGreetingTitle, ConversationHeroMark } from "./conversation-greeting";
import { ConversationScopePicker } from "./conversation-scope";
import { ConversationGuides } from "./conversation-guides";
import { ConversationAttachmentList } from "./conversation-attachments";
import { composeFactoryPrompt, isConversationFile, readConversationFile, type ConversationAttachment } from "./conversation-attachment";
import type { ChatTarget } from "./chat-scope";

export type { ChatTarget } from "./chat-scope";

type Locale = "zh" | "en";

const landingCopy = {
  zh: {
    input: "随心输入",
    send: "发送",
    message: "消息",
    starting: "正在打开…",
    attach: "添加文件",
    skipped: "只能添加文本、PDF 或 Word 文档。",
    createFailed: "无法创建项目。",
  },
  en: {
    input: "Type freely",
    send: "Send",
    message: "Message",
    starting: "Opening…",
    attach: "Attach files",
    skipped: "Attach text, PDF, or Word documents only.",
    createFailed: "The Project could not be created.",
  },
} as const;

export function ChatLanding({
  locale,
  projects,
  onSelect,
  onCreateProject,
  onStart,
}: {
  locale: Locale;
  projects: ProjectSummaryResponse[];
  onSelect: (target: ChatTarget) => void | Promise<void>;
  onCreateProject: () => void | Promise<void>;
  onStart: (target: ChatTarget, prompt: string) => void | Promise<void>;
}) {
  const text = landingCopy[locale];
  const [target, setTarget] = React.useState<ChatTarget>({ kind: "new" });
  const [draft, setDraft] = React.useState("");
  const [hint, setHint] = React.useState("");
  const [starting, setStarting] = React.useState(false);
  const [attachments, setAttachments] = React.useState<ConversationAttachment[]>([]);
  const attachmentSeq = React.useRef(0);

  const send = async () => {
    const prompt = composeFactoryPrompt(draft, attachments, locale);
    if (!prompt || starting) return;
    setStarting(true);
    setHint("");
    try {
      await onStart(target, prompt);
    } catch {
      setHint(text.createFailed);
      setStarting(false);
    }
  };

  const attach = async (files: File[]) => {
    const accepted = files.filter((file) => isConversationFile(file.name));
    if (accepted.length !== files.length) setHint(text.skipped);
    else setHint("");
    const next = await Promise.all(accepted.map((file) => {
      attachmentSeq.current += 1;
      return readConversationFile(file, `att-${attachmentSeq.current}`);
    }));
    setAttachments((current) => [...current, ...next]);
  };

  const projectName = target.kind === "project" ? target.name : target.kind === "agent" ? target.projectName : undefined;
  const agentName = target.kind === "agent" ? target.name : undefined;

  return (
    <ConversationStage
      empty
      canvasOpen={false}
      mark={<ConversationHeroMark />}
      greetingTitle={<ConversationGreetingTitle locale={locale} projectName={projectName} agentName={agentName} />}
      greetingLabel={assembleGreeting(locale, projectName, agentName)}
      suggestions={(
        <>
          <ConversationGuides locale={locale} onPick={setDraft} />
          {hint ? <p className="agent-convo-hint" role="status">{hint}</p> : null}
        </>
      )}
      contextBar={(
        <ConversationScopePicker
          locale={locale}
          current={target}
          projects={projects}
          onSelect={(next) => {
            setTarget(next);
            return onSelect(next);
          }}
          onCreateProject={onCreateProject}
        />
      )}
      composer={(
        <ConversationComposer
          locale={locale}
          value={draft}
          onChange={setDraft}
          onSubmit={() => void send()}
          disabled={(!draft.trim() && attachments.length === 0) || starting}
          placeholder={text.input}
          sendLabel={starting ? text.starting : text.send}
          sending={starting}
          textboxLabel={text.message}
          attachLabel={text.attach}
          onAttachFiles={(files) => void attach(files)}
          extraFields={<ConversationAttachmentList items={attachments} locale={locale} onRemove={(id) => setAttachments((current) => current.filter((item) => item.id !== id))} />}
        />
      )}
    />
  );
}
