import { Check, Moon, Palette, Settings2, Sun } from "lucide-react";
import { Button, Panel, SectionHeading, StatusBadge, useTheme, type ThemeChoice } from "@veyra/ui";

const choices: Array<{ value: ThemeChoice; label: string; icon: typeof Sun }> = [
  { value: "system", label: "System", icon: Settings2 },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
];

export function SettingsPage() {
  const { theme, setTheme } = useTheme();
  return <div className="page-stack"><div className="page-intro"><div><span className="ui-eyebrow">Workspace preferences</span><h2>Make the control surface fit your work.</h2><p>Appearance and layout are convenience preferences. Product truth remains in projects, definitions, and runs.</p></div><StatusBadge label="Saved locally" tone="good" /></div><div className="content-grid two-thirds"><Panel><SectionHeading eyebrow="Appearance" title="Theme" detail="Choose a calm light, dark, or system surface." /><div className="choice-list">{choices.map(({ value, label, icon: Icon }) => <button className={theme === value ? "choice active" : "choice"} key={value} type="button" onClick={() => setTheme(value)}><Icon size={17} /><span>{label}</span>{theme === value ? <Check size={15} /> : null}</button>)}</div></Panel><Panel><SectionHeading eyebrow="Workspace" title="Local boundary" detail="The desktop shell stays useful without remote access." /><div className="settings-facts"><div><span>Execution</span><strong>Local only</strong></div><div><span>External effects</span><strong>Guarded</strong></div><div><span>Source files</span><strong>User-owned</strong></div><div><span>Run evidence</span><strong>Replayable</strong></div></div><div className="settings-note"><Palette size={16} /><span>Layout preferences are the only browser storage used by this shell.</span></div></Panel></div><Panel><SectionHeading eyebrow="Accessibility" title="Comfort defaults" detail="The shell follows reduced-motion preferences and keeps focus states visible." /><div className="accessibility-row"><Button variant="secondary">Reset layout</Button><span>Sidebar width and theme can be changed any time.</span></div></Panel></div>;
}
