import * as React from "react";
import type { ProjectSummaryResponse } from "@veyra/api-contracts";
import { ConversationComposer, ConversationStage } from "./conversation-stage";
import { assembleGreeting, ConversationGreetingTitle, ConversationHeroMark } from "./conversation-greeting";
import { ConversationScopePicker } from "./conversation-scope";
import { ConversationGuides } from "./conversation-guides";
import { ConversationAttachmentList } from "./conversation-attachments";
import { composeFactoryPrompt, ensureClipboardFileName, isConversationFile, MAX_CONVERSATION_FILE_BYTES, readConversationFile, type ConversationAttachment } from "./conversation-attachment";
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
    skipped: "可添加文本、PDF、Word 和图片；Builder 不会读取图片像素。",
    imageGoal: "请先写一句目标说明；Builder 不会分析图片内容。",
    pathIgnored: "剪贴板里的本机文件路径不会发送；请在消息中另写说明。",
    tooLarge: "单个附件不能超过 25 MB。",
    tooLong: "目标文字和附件内容合计超过 10,000 个字符，请缩短说明或移除一些附件。",
    createFailed: "无法创建项目。",
  },
  en: {
    input: "Type freely",
    send: "Send",
    message: "Message",
    starting: "Opening…",
    attach: "Attach files",
    skipped: "Attach text, PDF, Word, or images. Builder cannot analyze image pixels.",
    imageGoal: "Add a text goal first; Builder cannot analyze image content.",
    pathIgnored: "Local file paths from the clipboard are not sent. Add a separate caption if needed.",
    tooLarge: "A single attachment cannot exceed 25 MB.",
    tooLong: "The goal and extracted files exceed 10,000 characters. Shorten the goal or remove some files.",
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
    if (!draft.trim() && attachments.length > 0 && attachments.every((item) => item.kind === "image")) {
      setHint(text.imageGoal);
      return;
    }
    if (prompt.length > 10_000) {
      setHint(text.tooLong);
      return;
    }
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
    const withinLimit = files.filter((file) => file.size <= MAX_CONVERSATION_FILE_BYTES);
    const accepted = withinLimit.filter((file) => isConversationFile(file.name, file.type)).map(ensureClipboardFileName);
    if (withinLimit.length !== files.length) setHint(text.tooLarge);
    else if (accepted.length !== files.length) setHint(text.skipped);
    else setHint("");
    const next = await Promise.all(accepted.map((file) => {
      attachmentSeq.current += 1;
      return readConversationFile(file, `att-${attachmentSeq.current}`);
    }));
    setAttachments((current) => [...current, ...next]);
  };

  const projectName = target.kind === "project" ? target.name : target.kind === "agent" ? target.projectName : undefined;
  const agentName = target.kind === "agent" ? target.name : undefined;
  const imageOnlyWithoutGoal = !draft.trim() && attachments.length > 0 && attachments.every((item) => item.kind === "image");

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
          disabled={(!draft.trim() && attachments.length === 0) || imageOnlyWithoutGoal || starting}
          placeholder={text.input}
          sendLabel={starting ? text.starting : text.send}
          sending={starting}
          textboxLabel={text.message}
          attachLabel={text.attach}
          fileAccept=".txt,.md,.markdown,.json,.csv,.tsv,.yaml,.yml,.html,.xml,.log,.pdf,.docx,.png,.jpg,.jpeg,.webp,.gif,text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,image/png,image/jpeg,image/webp,image/gif"
          onAttachFiles={(files) => void attach(files)}
          onPasteFiles={(files) => void attach(files)}
          onPasteNotice={() => setHint(text.pathIgnored)}
          extraFields={<>{imageOnlyWithoutGoal ? <p className="agent-convo-hint" role="status">{text.imageGoal}</p> : null}<ConversationAttachmentList items={attachments} locale={locale} onRemove={(id) => setAttachments((current) => current.filter((item) => item.id !== id))} /></>}
        />
      )}
    />
  );
}
