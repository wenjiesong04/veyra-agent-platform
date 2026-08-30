import { createContext, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";

export type LanguageChoice = "system" | "zh" | "en";
export type Locale = "zh" | "en";

type Dictionary = Record<string, { zh: string; en: string }>;

/**
 * The shell dictionary is intentionally small and product-facing. Feature
 * pages can keep their domain copy while shared chrome stays consistent in
 * both languages.
 */
export const dictionary: Dictionary = {
  workspace: { zh: "工作区", en: "Workspace" },
  agentPlatform: { zh: "Agent 平台", en: "Agent Platform" },
  readyToBuild: { zh: "已准备构建", en: "Ready to build" },
  localControlSurface: { zh: "本机控制面", en: "Local control surface" },
  localFirst: { zh: "本机优先", en: "Local first" },
  localOnly: { zh: "仅限本机", en: "Local only" },
  noAutomaticExecution: { zh: "不会自动执行", en: "No automatic execution" },
  localWorkspace: { zh: "本机工作区", en: "Local workspace" },
  notSignedIn: { zh: "未连接账号", en: "Not signed in" },
  accountInfo: { zh: "账号信息", en: "Account" },
  signInOrRegister: { zh: "登录或注册", en: "Sign in or register" },
  signOut: { zh: "退出登录", en: "Sign out" },
  openAccountMenu: { zh: "打开账号菜单", en: "Open account menu" },
  closeAccountMenu: { zh: "关闭账号菜单", en: "Close account menu" },
  build: { zh: "构建", en: "Build" },
  features: { zh: "功能", en: "Features" },
  operate: { zh: "运行", en: "Operate" },
  library: { zh: "组件库", en: "Library" },
  connect: { zh: "连接", en: "Connect" },
  identity: { zh: "身份", en: "Identity" },
  explore: { zh: "探索", en: "Explore" },
  yourSpace: { zh: "我的空间", en: "Your space" },
  projects: { zh: "项目", en: "Projects" },
  newChat: { zh: "新聊天", en: "New chat" },
  runWorkspace: { zh: "运行工作台", en: "Run workspace" },
  resourceLibrary: { zh: "资源库", en: "Resource library" },
  knowledgeBase: { zh: "知识库", en: "Knowledge base" },
  moreProjects: { zh: "显示更多项目", en: "Show more Projects" },
  collapseProjects: { zh: "收起项目列表", en: "Collapse Projects" },
  manageProjects: { zh: "管理项目", en: "Manage Projects" },
  createProjectShortcut: { zh: "新建项目", en: "Create Project" },
  openExistingProject: { zh: "打开已有项目", en: "Open existing project" },
  importProject: { zh: "导入项目", en: "Import Project" },
  exportProject: { zh: "导出项目", en: "Export Project" },
  exportProjectDetail: { zh: "下载可移植的项目压缩包", en: "Download a portable Project archive" },
  projectActions: { zh: "项目操作", en: "Project actions" },
  agentActions: { zh: "Agent 操作", en: "Agent actions" },
  openAgent: { zh: "打开 Agent", en: "Open Agent" },
  orchestration: { zh: "编排", en: "Orchestration" },
  dataAnalysis: { zh: "数据分析", en: "Data analysis" },
  pinned: { zh: "置顶", en: "Pinned" },
  home: { zh: "主页", en: "Home" },
  agent: { zh: "Agent", en: "Agent" },
  factory: { zh: "Factory", en: "Factory" },
  version: { zh: "版本", en: "Version" },
  run: { zh: "运行", en: "Run" },
  back: { zh: "返回", en: "Back" },
  breadcrumb: { zh: "面包屑", en: "Breadcrumb" },
  pinProject: { zh: "置顶项目", en: "Pin Project" },
  unpinProject: { zh: "取消置顶", en: "Unpin Project" },
  editProject: { zh: "编辑", en: "Edit" },
  deleteProject: { zh: "删除", en: "Delete" },
  pinProjectDetail: { zh: "固定在项目列表顶部", en: "Keep this Project at the top" },
  editProjectDetail: { zh: "修改项目名称和描述", en: "Change the Project name and description" },
  deleteProjectDetail: { zh: "移到 Veyra 回收区", en: "Move to Veyra Trash" },
  pinAgent: { zh: "置顶", en: "Pin" },
  editAgent: { zh: "编辑", en: "Edit" },
  deleteAgent: { zh: "删除", en: "Delete" },
  pinAgentDetail: { zh: "固定在项目下方顶部", en: "Keep this Agent at the top" },
  editAgentDetail: { zh: "修改 Agent 名称和描述", en: "Change the Agent name and description" },
  deleteAgentDetail: { zh: "移到 Veyra 回收区", en: "Move to Veyra Trash" },
  addAgent: { zh: "添加 Agent", en: "Add Agent" },
  addChildAgent: { zh: "添加子 Agent", en: "Add child Agent" },
  expandProject: { zh: "展开项目", en: "Expand Project" },
  collapseProject: { zh: "收起项目", en: "Collapse Project" },
  recent: { zh: "最近", en: "Recent" },
  loadingProjects: { zh: "正在加载项目…", en: "Loading Projects…" },
  noProjects: { zh: "暂无项目", en: "No Projects yet" },
  noRecentProjects: { zh: "暂无最近项目", en: "No recent Projects" },
  projectsUnavailable: { zh: "项目暂时不可用", en: "Projects unavailable" },
  runs: { zh: "运行记录", en: "Runs" },
  monitor: { zh: "监控", en: "Monitor" },
  components: { zh: "组件", en: "Components" },
  files: { zh: "文件", en: "Files" },
  community: { zh: "社区", en: "Community" },
  account: { zh: "账号", en: "Account" },
  settings: { zh: "设置", en: "Settings" },
  catalog: { zh: "目录", en: "Catalog" },
  history: { zh: "历史", en: "History" },
  language: { zh: "中", en: "EN" },
  day: { zh: "白昼", en: "Light" },
  night: { zh: "暗夜", en: "Dark" },
  openNavigation: { zh: "打开导航", en: "Open navigation" },
  closeNavigation: { zh: "关闭导航", en: "Close navigation" },
  expandSidebar: { zh: "展开侧栏", en: "Expand sidebar" },
  collapseSidebar: { zh: "收起侧栏", en: "Collapse sidebar" },
  switchToChinese: { zh: "切换到中文", en: "Switch to Chinese" },
  switchToEnglish: { zh: "切换到英文", en: "Switch to English" },
  switchToLight: { zh: "切换到白昼模式", en: "Switch to light mode" },
  switchToDark: { zh: "切换到暗夜模式", en: "Switch to dark mode" },
  routeNotFound: { zh: "找不到页面", en: "Route not found" },
  versionAwareCatalog: { zh: "版本化目录", en: "Version-aware catalog" },
  historyPage: { zh: "历史", en: "History" },
  discover: { zh: "发现", en: "Discover" },
  preferences: { zh: "偏好", en: "Preferences" },
  createProject: { zh: "创建 / 项目", en: "Create / Project" },
  project: { zh: "项目", en: "Project" },
  agents: { zh: "Agent 列表", en: "Agents" },
  agentProject: { zh: "Agent / 项目", en: "Agent / Project" },
  versionProject: { zh: "版本 / 项目", en: "Version / Project" },
  runProject: { zh: "运行 / 项目", en: "Run / Project" },
  designProject: { zh: "设计 / 项目", en: "Design / Project" },
  studio: { zh: "Studio", en: "Studio" },
  component: { zh: "组件", en: "Component" },
  file: { zh: "文件", en: "File" },
  entryDetail: { zh: "条目详情", en: "Entry detail" },
};

type LocaleContextValue = {
  language: LanguageChoice;
  locale: Locale;
  setLanguage: (language: LanguageChoice) => void;
  t: (key: string, fallback?: string) => string;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);
const languageStorageKey = "veyra.language";

function readLanguage(): LanguageChoice {
  try {
    const value = window.localStorage.getItem(languageStorageKey);
    return value === "zh" || value === "en" || value === "system" ? value : "system";
  } catch {
    return "system";
  }
}

function systemLocale(): Locale {
  return typeof navigator !== "undefined" && navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export function LocaleProvider({ children }: PropsWithChildren) {
  const [language, setLanguage] = useState<LanguageChoice>(readLanguage);
  const [system, setSystem] = useState<Locale>(systemLocale);
  const locale = language === "system" ? system : language;

  useEffect(() => {
    try {
      window.localStorage.setItem(languageStorageKey, language);
    } catch {
      // Language is a convenience preference; the product remains usable without storage.
    }
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [language, locale]);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(language: zh)");
    // Browsers do not consistently expose a language media query. The
    // navigator value is still the stable system fallback for this shell.
    const onLanguageChange = () => setSystem(systemLocale());
    media.addEventListener?.("change", onLanguageChange);
    return () => media.removeEventListener?.("change", onLanguageChange);
  }, []);

  const value = useMemo<LocaleContextValue>(() => ({
    language,
    locale,
    setLanguage,
    t: (key, fallback) => dictionary[key]?.[locale] ?? fallback ?? key,
  }), [language, locale]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleContextValue {
  const context = useContext(LocaleContext);
  if (!context) throw new Error("useLocale must be used inside LocaleProvider");
  return context;
}
