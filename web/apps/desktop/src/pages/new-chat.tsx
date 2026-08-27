import { Sparkles } from "lucide-react";
import { Panel, useLocale } from "@veyra/ui";

export function NewChatPage() {
  const { locale } = useLocale();
  const zh = locale === "zh";
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">Veyra</span><h2>{zh ? "新聊天" : "New chat"}</h2><p>{zh ? "聊天与 Agent 生成会在 Factory 阶段启用。" : "Chat and Agent generation will be enabled in the Factory phase."}</p></div></div><Panel className="project-capability-note"><Sparkles size={17} aria-hidden="true" /><span>{zh ? "此入口暂不创建会话，也不会模拟 Agent 行为。" : "This entry does not create a conversation or simulate Agent behavior yet."}</span></Panel></div>;
}
