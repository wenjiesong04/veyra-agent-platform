type Locale = "zh" | "en";

export function ConversationHeroMark() {
  return (
    <span className="agent-convo-mark" aria-hidden="true">
      <img src="/veyra-icon.png" alt="" />
    </span>
  );
}

export function greetingScopeName(projectName?: string, agentName?: string, locale: Locale = "en"): string {
  if (agentName) return agentName;
  if (projectName) return projectName;
  return locale === "zh" ? "新项目" : "a new project";
}

export function assembleGreeting(locale: Locale, projectName?: string, agentName?: string): string {
  const name = greetingScopeName(projectName, agentName, locale);
  return locale === "zh" ? `你想在 ${name} 实现什么？` : `What do you want to achieve in ${name}?`;
}

export function ConversationGreetingTitle({
  locale,
  projectName,
  agentName,
}: {
  locale: Locale;
  projectName?: string;
  agentName?: string;
}) {
  const name = greetingScopeName(projectName, agentName, locale);
  if (locale === "zh") {
    return <>你想在 <span className="agent-convo-scope-name">{name}</span> 实现什么？</>;
  }
  return <>What do you want to achieve in <span className="agent-convo-scope-name">{name}</span>?</>;
}
