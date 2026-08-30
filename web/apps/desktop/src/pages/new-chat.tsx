import { Sparkles } from "lucide-react";
import { Panel, useLocale } from "@veyra/ui";

export function NewChatPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">Veyra</span><h2>{zh ? "新聊天" : "New chat"}</h2><p>{zh ? "请先进入项目，再通过 Factory 创建 Agent。" : "Open a Project first, then use Factory to create an Agent."}</p></div></div><Panel className="project-capability-note"><Sparkles size={17} aria-hidden="true" /><span>{zh ? "Agent 对话会在进入具体 Agent 后启用；Factory 只负责生成可审核草稿。" : "Agent conversations open inside a concrete Agent; Factory only produces reviewable drafts."}</span></Panel></div>;
}
