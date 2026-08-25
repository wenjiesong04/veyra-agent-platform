import { Check, Moon, Palette, Settings2, Sun } from "lucide-react";
import { Button, Panel, SectionHeading, StatusBadge, useLocale, useTheme, type ThemeChoice } from "@veyra/ui";

const choices: Array<{ value: ThemeChoice; icon: typeof Sun }> = [
  { value: "system", icon: Settings2 },
  { value: "light", icon: Sun },
  { value: "dark", icon: Moon },
];

export function SettingsPage() {
  const { locale } = useLocale();
  const { theme, setTheme } = useTheme();
  const copy = locale === "zh" ? {
    eyebrow: "工作区偏好", title: "让控制面适应你的工作。", description: "外观和布局只是便利偏好；产品真实状态仍在项目、定义和运行记录中。", saved: "已保存到本机", appearance: "外观", theme: "主题", themeDetail: "选择舒适的白昼、暗夜或跟随系统界面。", system: "系统", light: "白昼", dark: "暗夜", workspace: "工作区", boundary: "本机边界", boundaryDetail: "没有远程访问时，桌面壳层仍然可用。", execution: "执行", localOnly: "仅限本机", effects: "外部效果", guarded: "受控", source: "源文件", userOwned: "用户拥有", evidence: "运行证据", replayable: "可重放", storage: "布局偏好是此壳层唯一使用的浏览器存储。", accessibility: "无障碍", comfort: "舒适默认值", comfortDetail: "壳层遵循减少动态效果偏好，并保持焦点状态可见。", reset: "重置布局", change: "侧栏宽度和主题随时可以更改。",
  } : {
    eyebrow: "Workspace preferences", title: "Make the control surface fit your work.", description: "Appearance and layout are convenience preferences. Product truth remains in projects, definitions, and runs.", saved: "Saved locally", appearance: "Appearance", theme: "Theme", themeDetail: "Choose a calm light, dark, or system surface.", system: "System", light: "Light", dark: "Dark", workspace: "Workspace", boundary: "Local boundary", boundaryDetail: "The desktop shell stays useful without remote access.", execution: "Execution", localOnly: "Local only", effects: "External effects", guarded: "Guarded", source: "Source files", userOwned: "User-owned", evidence: "Run evidence", replayable: "Replayable", storage: "Layout preferences are the only browser storage used by this shell.", accessibility: "Accessibility", comfort: "Comfort defaults", comfortDetail: "The shell follows reduced-motion preferences and keeps focus states visible.", reset: "Reset layout", change: "Sidebar width and theme can be changed any time.",
  };
  const labels: Record<ThemeChoice, string> = { system: copy.system, light: copy.light, dark: copy.dark };
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">{copy.eyebrow}</span><h2>{copy.title}</h2><p>{copy.description}</p></div><StatusBadge label={copy.saved} tone="good" /></div><div className="content-grid two-thirds"><Panel><SectionHeading eyebrow={copy.appearance} title={copy.theme} detail={copy.themeDetail} /><div className="choice-list">{choices.map(({ value, icon: Icon }) => <button className={theme === value ? "choice active" : "choice"} key={value} type="button" onClick={() => setTheme(value)}><Icon size={17} /><span>{labels[value]}</span>{theme === value ? <Check size={15} /> : null}</button>)}</div></Panel><Panel><SectionHeading eyebrow={copy.workspace} title={copy.boundary} detail={copy.boundaryDetail} /><div className="settings-facts"><div><span>{copy.execution}</span><strong>{copy.localOnly}</strong></div><div><span>{copy.effects}</span><strong>{copy.guarded}</strong></div><div><span>{copy.source}</span><strong>{copy.userOwned}</strong></div><div><span>{copy.evidence}</span><strong>{copy.replayable}</strong></div></div><div className="settings-note"><Palette size={16} /><span>{copy.storage}</span></div></Panel></div><Panel><SectionHeading eyebrow={copy.accessibility} title={copy.comfort} detail={copy.comfortDetail} /><div className="accessibility-row"><Button variant="secondary">{copy.reset}</Button><span>{copy.change}</span></div></Panel></div>;
}
