import { BookOpen, Files, ShieldCheck, Wrench, type LucideIcon } from "lucide-react";

type Locale = "zh" | "en";

export type ConversationGuide = {
  id: string;
  title: string;
  prompt: string;
  icon: LucideIcon;
};

export function factoryGuides(locale: Locale, revising: boolean): ConversationGuide[] {
  if (locale === "zh") {
    return [
      {
        id: "brief",
        title: "组装研究简报 Agent",
        prompt: "组装一个 Agent：阅读本地文档，写出一份研究简报，并在写出文件前请求审批。",
        icon: BookOpen,
      },
      {
        id: "approval",
        title: "写文件前先审批",
        prompt: "做一个会改本地文件的 Agent，但每次写入前必须人工审批，并说明成功标准。",
        icon: ShieldCheck,
      },
      {
        id: "documents",
        title: "根据文档整理输出",
        prompt: "根据项目里的本地文档整理结构化输出。只使用资源库里已登记的能力。",
        icon: Files,
      },
      revising
        ? {
            id: "revise",
            title: "修订这个 Agent 的流程",
            prompt: "修订当前 Agent：保持现有目标，补上必要的审批、验证和资源库里已有的能力。",
            icon: Wrench,
          }
        : {
            id: "internal",
            title: "做一个带验证的内部工具",
            prompt: "组装一个内部工具 Agent：输入明确、输出可验证，权限尽量小，不要发明未登记的工具。",
            icon: Wrench,
          },
    ];
  }
  return [
    {
      id: "brief",
      title: "Assemble a research-brief Agent",
      prompt: "Assemble an Agent that reads local documents, writes a research brief, and requests approval before writing a file.",
      icon: BookOpen,
    },
    {
      id: "approval",
      title: "Require approval before writing files",
      prompt: "Build an Agent that can change local files, but every write needs human approval, and define what success looks like.",
      icon: ShieldCheck,
    },
    {
      id: "documents",
      title: "Distill local documents",
      prompt: "Distill local Project documents into a structured output. Use only registered catalog capabilities.",
      icon: Files,
    },
    revising
      ? {
          id: "revise",
          title: "Revise this Agent's workflow",
          prompt: "Revise the current Agent: keep its goal, and add the approvals, verification, and catalog capabilities it still needs.",
          icon: Wrench,
        }
      : {
          id: "internal",
          title: "Build a verified internal tool",
          prompt: "Assemble an internal-tool Agent with clear inputs, a verifiable output, and minimal permissions. Do not invent unregistered tools.",
          icon: Wrench,
        },
  ];
}

export function ConversationGuides({
  locale,
  revising = false,
  onPick,
}: {
  locale: Locale;
  revising?: boolean;
  onPick: (prompt: string) => void;
}) {
  return (
    <ul className="agent-convo-guides">
      {factoryGuides(locale, revising).map((guide) => {
        const Icon = guide.icon;
        return (
          <li key={guide.id}>
            <button className={`agent-convo-guide is-${guide.id}`} type="button" onClick={() => onPick(guide.prompt)}>
              <span className="agent-convo-guide-icon" aria-hidden="true"><Icon size={18} strokeWidth={1.7} /></span>
              <span className="agent-convo-guide-label">{guide.title}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
