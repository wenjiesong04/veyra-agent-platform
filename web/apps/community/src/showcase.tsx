import {
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  Blocks,
  BookOpen,
  Check,
  ExternalLink,
  FileText,
  FolderKanban,
  Github,
  LockKeyhole,
  Menu,
  Moon,
  Play,
  ShieldCheck,
  Sun,
  Workflow,
  X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { ThemeProvider, useLocale, useTheme, type Locale } from "@veyra/ui";

const repository = "https://github.com/wenjiesong04/veyra-agent-platform";
const branchDocs = `${repository}/blob/codex/agent-platform`;

const messages = {
  en: {
    skip: "Skip to content",
    brand: "Veyra",
    subtitle: "LOCAL-FIRST AGENT PLATFORM",
    navProduct: "Product",
    navHow: "How it works",
    navSafety: "Safety",
    navDocs: "Docs",
    navDownload: "Download",
    headerCta: "Build instructions",
    openMenu: "Open navigation",
    closeMenu: "Close navigation",
    language: "Switch to Chinese",
    themeDark: "Switch to dark theme",
    themeLight: "Switch to light theme",
    heroEyebrow: "A workspace for AI you can inspect",
    heroTitle: "Build, inspect, run and share AI agents from a local-first workspace.",
    heroBody: "Turn an idea into an editable Agent. Review its structure, resources and permissions, then run it locally and inspect what happened.",
    heroPrimary: "See how Veyra works",
    heroSecondary: "Visit the project repository",
    repoAccess: "Repository links may require GitHub access.",
    previewLabel: "PRODUCT PREVIEW · ILLUSTRATIVE, NOT A LIVE RUN",
    previewTitle: "A workflow you can inspect",
    previewProject: "Research workspace",
    previewAgent: "Briefing Agent · draft",
    previewInput: "Input",
    previewModel: "Model",
    previewApproval: "Human approval",
    previewOutput: "Output",
    previewNote: "Structure illustration only. No live Project or Run data.",
    previewFooter: "ILLUSTRATIVE",
    featuresEyebrow: "PRODUCT",
    featuresTitle: "One workspace from idea to evidence.",
    featuresBody: "Veyra connects the parts of Agent work without hiding the definition, dependencies or execution record.",
    features: [
      { icon: FolderKanban, title: "Project workspace", body: "Keep Agents, Workflows, Knowledge and files organized in local Projects." },
      { icon: Blocks, title: "Builder with review", body: "Start from a request, inspect the proposed structure, and confirm before it changes a Draft." },
      { icon: Workflow, title: "Visual Studio", body: "Move between Form, Canvas and Source views of the same Agent definition." },
      { icon: BookOpen, title: "Resources and Knowledge", body: "Bind explicit resources and text Knowledge to a Project; inspect readiness and version locks." },
      { icon: Play, title: "Local Runtime", body: "Run versioned Agents locally with approval gates and inspectable Run events and receipts." },
      { icon: ShieldCheck, title: "Share by release", body: "Publish an immutable release to Community; importing previews it and creates a local Draft, not an automatic Run." },
    ],
    howEyebrow: "HOW IT WORKS",
    howTitle: "A reviewable path, not a black box.",
    howBody: "The product keeps the definition, human decision and actual execution as separate steps.",
    steps: [
      { title: "Describe", body: "Start with the work you want an Agent to do." },
      { title: "Review a proposal", body: "Inspect the candidate graph, inputs, dependencies and permissions." },
      { title: "Edit and version", body: "Use Studio to adjust the source, validate it and save an immutable version." },
      { title: "Run locally", body: "Execute on your machine and review events, approvals and results." },
      { title: "Share when ready", body: "Optionally publish a version; another user previews it before importing a local Draft." },
    ],
    safetyEyebrow: "LOCAL-FIRST · EXPLICIT CONTROL",
    safetyTitle: "Local-first does not mean network-free.",
    safetyBody: "Project work is local by default. Model providers, connected Tools and Community publishing can make network requests, so Veyra keeps those boundaries visible instead of promising that no data ever leaves the device.",
    safetyPoints: [
      "Project source stays inspectable and versioned.",
      "Resource references use explicit versions and dependency locks.",
      "Sensitive actions can pause for human approval.",
      "Community imports are reviewed locally and do not execute automatically.",
    ],
    safetyFoot: "Choose the context and permissions appropriate to each provider or external Tool. A successful Run is not automatically a verified outcome.",
    sharingEyebrow: "OPTIONAL SHARING",
    sharingTitle: "A release is not permission to run.",
    sharingBody: "Community is a separate sharing service. Desktop users can publish and discover immutable Agent releases; an import is checked against the destination Project and becomes a local Draft only after confirmation.",
    shareSteps: ["Immutable release", "Inspect version and permissions", "Preview dependencies", "Create a local Draft"],
    startEyebrow: "GETTING STARTED",
    startTitle: "Explore the project, then build from source.",
    startBody: "The repository contains the current README, product design and macOS packaging instructions. These links point to the active development branch and may require GitHub access.",
    startReadme: "README and setup",
    startDesign: "Product and architecture",
    startPackaging: "Desktop build instructions",
    downloadEyebrow: "DESKTOP DISTRIBUTION",
    downloadTitle: "Public installer is not available yet.",
    downloadBody: "There is no verified public DMG or download URL in this release. Build instructions are available in the repository; do not treat local build artifacts as public downloads.",
    downloadButton: "Build from source",
    repositoryButton: "Open repository",
    footerLine: "A local-first workspace for inspectable AI agents.",
    footerDocs: "Documentation",
    footerRepo: "GitHub repository",
    footerAccess: "Some project links require repository access.",
  },
  zh: {
    skip: "跳转到正文",
    brand: "Veyra",
    subtitle: "本机优先的 Agent 平台",
    navProduct: "产品",
    navHow: "工作方式",
    navSafety: "安全边界",
    navDocs: "文档",
    navDownload: "下载",
    headerCta: "构建说明",
    openMenu: "打开导航",
    closeMenu: "关闭导航",
    language: "切换到英文",
    themeDark: "切换到暗色主题",
    themeLight: "切换到浅色主题",
    heroEyebrow: "一个可检查的 AI 工作空间",
    heroTitle: "在本机优先的工作空间中构建、检查、运行和分享 Agent。",
    heroBody: "把想法变成可编辑的 Agent。先检查结构、资源和权限，再在本机运行并查看实际执行记录。",
    heroPrimary: "了解 Veyra 如何工作",
    heroSecondary: "访问项目仓库",
    repoAccess: "仓库链接可能需要 GitHub 访问权限。",
    previewLabel: "产品示意 · 非真实运行画面",
    previewTitle: "工作流结构可供检查",
    previewProject: "研究工作区",
    previewAgent: "简报 Agent · 草稿",
    previewInput: "输入",
    previewModel: "模型",
    previewApproval: "人工审批",
    previewOutput: "输出",
    previewNote: "仅为结构示意，不包含实时 Project 或 Run 数据。",
    previewFooter: "结构示意",
    featuresEyebrow: "产品能力",
    featuresTitle: "从想法到执行证据，一个工作空间贯通。",
    featuresBody: "Veyra 把 Agent 工作的各个环节连接起来，同时保留定义、依赖和执行记录的可见性。",
    features: [
      { icon: FolderKanban, title: "Project 工作区", body: "在本机 Project 中组织 Agents、Workflows、Knowledge 和文件。" },
      { icon: Blocks, title: "可审阅的 Builder", body: "从需求开始，检查候选结构，并在修改 Draft 前明确确认。" },
      { icon: Workflow, title: "可视化 Studio", body: "在 Form、Canvas 和 Source 视图中编辑同一份 Agent 定义。" },
      { icon: BookOpen, title: "资源与 Knowledge", body: "显式绑定资源与文本 Knowledge，并检查运行就绪状态和版本锁。" },
      { icon: Play, title: "本机 Runtime", body: "在本机运行有版本的 Agent，通过审批节点控制操作，并查看 Run 事件与回执。" },
      { icon: ShieldCheck, title: "按版本分享", body: "向 Community 发布不可变版本；导入前先预览，确认后创建本机 Draft，不会自动运行。" },
    ],
    howEyebrow: "工作方式",
    howTitle: "每一步都可审阅，而不是黑箱。",
    howBody: "定义、人的决策和实际执行被清楚分成不同步骤。",
    steps: [
      { title: "描述需求", body: "从你希望 Agent 完成的工作开始。" },
      { title: "审阅提案", body: "检查候选图、输入、依赖和权限。" },
      { title: "编辑并版本化", body: "在 Studio 中修改 source、验证并保存不可变版本。" },
      { title: "本机运行", body: "在自己的设备执行，并查看事件、审批和结果。" },
      { title: "准备好再分享", body: "可选发布版本；其他用户先预览，再导入为本机 Draft。" },
    ],
    safetyEyebrow: "本机优先 · 显式控制",
    safetyTitle: "本机优先，不代表完全离线。",
    safetyBody: "Project 工作默认在本机。模型供应商、已连接的 Tool 和 Community 发布可能会发起网络请求，因此 Veyra 会展示这些边界，而不承诺数据永远不会离开设备。",
    safetyPoints: [
      "Project source 可检查、可版本化。",
      "资源引用使用明确版本和依赖锁。",
      "敏感操作可以暂停并等待人工审批。",
      "Community 导入在本机审查，不会自动执行。",
    ],
    safetyFoot: "请为每个 Provider 或外部 Tool 选择合适的上下文与权限。Run 成功不等于结果已被验证。",
    sharingEyebrow: "可选分享",
    sharingTitle: "发布版本不等于获得运行权限。",
    sharingBody: "Community 是独立的分享服务。Desktop 用户可发布和发现不可变 Agent 版本；导入时会针对目标 Project 检查，确认后只创建本机 Draft。",
    shareSteps: ["不可变发布版本", "检查版本与权限", "预览依赖", "创建本机 Draft"],
    startEyebrow: "开始使用",
    startTitle: "先了解项目，再从源码构建。",
    startBody: "仓库包含当前 README、产品设计和 macOS 打包说明。链接指向开发分支，可能需要 GitHub 访问权限。",
    startReadme: "README 与环境配置",
    startDesign: "产品与架构设计",
    startPackaging: "桌面版构建说明",
    downloadEyebrow: "桌面发行",
    downloadTitle: "目前尚无公开安装包。",
    downloadBody: "当前没有经过验证的公开 DMG 或下载地址。仓库提供源码构建说明；本机生成的构建产物不等于公开下载。",
    downloadButton: "从源码构建",
    repositoryButton: "打开项目仓库",
    footerLine: "一个用于构建可检查 AI Agent 的本机优先工作空间。",
    footerDocs: "项目文档",
    footerRepo: "GitHub 仓库",
    footerAccess: "部分项目链接需要仓库访问权限。",
  },
} satisfies Record<Locale, Record<string, unknown>>;

type Copy = (typeof messages)[Locale];

const features = {
  en: messages.en.features,
  zh: messages.zh.features,
};

const steps = {
  en: messages.en.steps,
  zh: messages.zh.steps,
};

const docs = {
  readme: `${branchDocs}/README.md`,
  design: `${branchDocs}/docs/PROJECT_DESIGN.md`,
  packaging: `${branchDocs}/docs/desktop_packaging.md`,
};

function ShowcasePage() {
  const { locale, setLanguage } = useLocale();
  const { effectiveDark, setTheme } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const copy = messages[locale] as Copy;

  useEffect(() => {
    document.title = `${copy.brand} — ${copy.subtitle}`;
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [copy.brand, copy.subtitle, locale]);

  useEffect(() => {
    const normalizeLegacyWorkspaceRoute = () => {
      if (window.location.hash.startsWith("#/")) {
        window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#home`);
      }
    };
    normalizeLegacyWorkspaceRoute();
    window.addEventListener("hashchange", normalizeLegacyWorkspaceRoute);
    return () => window.removeEventListener("hashchange", normalizeLegacyWorkspaceRoute);
  }, []);

  const navItems = [
    ["#product", copy.navProduct],
    ["#how-it-works", copy.navHow],
    ["#safety", copy.navSafety],
    ["#docs", copy.navDocs],
    ["#download", copy.navDownload],
  ] as const;

  return (
    <div className="showcase-site">
      <a className="showcase-skip" href="#main">{copy.skip}</a>
      <header className="showcase-header">
        <div className="showcase-header__inner">
          <a className="showcase-brand" href="#home" aria-label="Veyra home">
            <span className="showcase-brand__mark" aria-hidden="true">V</span>
            <span className="showcase-brand__copy"><strong>{copy.brand}</strong><small>{copy.subtitle}</small></span>
          </a>
          <button className="showcase-menu-toggle" type="button" aria-label={menuOpen ? copy.closeMenu : copy.openMenu} aria-expanded={menuOpen} aria-controls="showcase-navigation" onClick={() => setMenuOpen((open) => !open)}>
            {menuOpen ? <X size={19} aria-hidden="true" /> : <Menu size={19} aria-hidden="true" />}
          </button>
          <nav id="showcase-navigation" className={`showcase-nav${menuOpen ? " is-open" : ""}`} aria-label={locale === "zh" ? "主导航" : "Primary navigation"}>
            {navItems.map(([href, label]) => <a key={href} href={href} onClick={() => setMenuOpen(false)}>{label}</a>)}
          </nav>
          <div className="showcase-header__actions">
            <button className="showcase-icon-button" type="button" aria-label={copy.language} onClick={() => setLanguage(locale === "zh" ? "en" : "zh")}>{locale === "zh" ? "EN" : "中文"}</button>
            <button className="showcase-icon-button" type="button" aria-label={effectiveDark ? copy.themeLight : copy.themeDark} onClick={() => setTheme(effectiveDark ? "light" : "dark")}>
              {effectiveDark ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
            </button>
            <a className="showcase-header-cta" href="#download">{copy.headerCta}<ArrowUpRight size={15} aria-hidden="true" /></a>
          </div>
        </div>
      </header>

      <main id="main">
        <section className="showcase-hero" id="home" aria-labelledby="showcase-title">
          <div className="showcase-container showcase-hero__grid">
            <div className="showcase-hero__copy">
              <p className="showcase-eyebrow"><span />{copy.heroEyebrow}</p>
              <h1 id="showcase-title">{copy.heroTitle}</h1>
              <p className="showcase-lede">{copy.heroBody}</p>
              <div className="showcase-actions">
                <a className="showcase-button showcase-button--primary" href="#how-it-works">{copy.heroPrimary}<ArrowRight size={16} aria-hidden="true" /></a>
                <a className="showcase-button showcase-button--secondary" href={repository} target="_blank" rel="noreferrer">{copy.heroSecondary}<ExternalLink size={15} aria-hidden="true" /></a>
              </div>
              <p className="showcase-access-note">{copy.repoAccess}</p>
            </div>
            <div className="showcase-preview" role="group" aria-label={copy.previewTitle}>
              <div className="showcase-preview__topline"><span>{copy.previewLabel}</span><span className="showcase-preview__dots" aria-hidden="true"><i /><i /><i /></span></div>
              <div className="showcase-preview__window">
                <div className="showcase-preview__sidebar"><b>V</b><span /><span /><span /><span /></div>
                <div className="showcase-preview__workspace">
                  <div className="showcase-preview__crumb"><span>{copy.previewProject}</span><ArrowRight size={13} aria-hidden="true" /><strong>{copy.previewTitle}</strong></div>
                  <div className="showcase-preview__agent"><span className="showcase-preview__agent-icon"><Workflow size={17} aria-hidden="true" /></span><span><b>{copy.previewAgent}</b><small>{copy.previewNote}</small></span></div>
                  <div className="showcase-flow" aria-label={copy.previewLabel}>
                    {[copy.previewInput, copy.previewModel, copy.previewApproval, copy.previewOutput].map((label, index) => <div className="showcase-flow__item" key={label}>
                      {index > 0 ? <span className="showcase-flow__connector" aria-hidden="true" /> : null}
                      <div className={`showcase-flow__node showcase-flow__node--${index}`}><span>{index === 0 ? <FileText size={16} aria-hidden="true" /> : index === 1 ? <Blocks size={16} aria-hidden="true" /> : index === 2 ? <LockKeyhole size={16} aria-hidden="true" /> : <Check size={16} aria-hidden="true" />}</span><b>{label}</b></div>
                    </div>)}
                  </div>
                  <div className="showcase-preview__footer"><span><span className="showcase-preview__status" />{copy.previewFooter}</span><span>Veyra Studio</span></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="showcase-section showcase-features" id="product" aria-labelledby="features-title">
          <div className="showcase-container">
            <div className="showcase-section-heading">
              <p className="showcase-eyebrow">{copy.featuresEyebrow}</p>
              <h2 id="features-title">{copy.featuresTitle}</h2>
              <p>{copy.featuresBody}</p>
            </div>
            <div className="showcase-feature-grid">
              {features[locale].map(({ icon: Icon, title, body }) => <article className="showcase-feature" key={title}>
                <span className="showcase-feature__icon"><Icon size={18} aria-hidden="true" /></span>
                <h3>{title}</h3>
                <p>{body}</p>
              </article>)}
            </div>
          </div>
        </section>

        <section className="showcase-section showcase-how" id="how-it-works" aria-labelledby="how-title">
          <div className="showcase-container showcase-how__layout">
            <div className="showcase-section-heading">
              <p className="showcase-eyebrow">{copy.howEyebrow}</p>
              <h2 id="how-title">{copy.howTitle}</h2>
              <p>{copy.howBody}</p>
            </div>
            <ol className="showcase-steps">
              {steps[locale].map(({ title, body }, index) => <li key={title}>
                <span className="showcase-step__number">0{index + 1}</span>
                <div><h3>{title}</h3><p>{body}</p></div>
                {index < steps[locale].length - 1 ? <ArrowDown className="showcase-step__arrow" size={17} aria-hidden="true" /> : null}
              </li>)}
            </ol>
          </div>
        </section>

        <section className="showcase-section showcase-safety" id="safety" aria-labelledby="safety-title">
          <div className="showcase-container showcase-safety__grid">
            <div className="showcase-safety__intro">
              <p className="showcase-eyebrow"><LockKeyhole size={14} aria-hidden="true" />{copy.safetyEyebrow}</p>
              <h2 id="safety-title">{copy.safetyTitle}</h2>
              <p>{copy.safetyBody}</p>
            </div>
            <div className="showcase-safety__list">
              {copy.safetyPoints.map((point) => <p key={point}><Check size={16} aria-hidden="true" /><span>{point}</span></p>)}
              <p className="showcase-safety__foot">{copy.safetyFoot}</p>
            </div>
          </div>
        </section>

        <section className="showcase-section showcase-sharing" aria-labelledby="sharing-title">
          <div className="showcase-container showcase-sharing__grid">
            <div>
              <p className="showcase-eyebrow">{copy.sharingEyebrow}</p>
              <h2 id="sharing-title">{copy.sharingTitle}</h2>
              <p>{copy.sharingBody}</p>
            </div>
            <ol className="showcase-sharing__steps">
              {copy.shareSteps.map((step, index) => <li key={step}><span>0{index + 1}</span><b>{step}</b></li>)}
            </ol>
          </div>
        </section>

        <section className="showcase-section showcase-resources" id="docs" aria-labelledby="start-title">
          <div className="showcase-container showcase-resources__layout">
            <div className="showcase-section-heading">
              <p className="showcase-eyebrow">{copy.startEyebrow}</p>
              <h2 id="start-title">{copy.startTitle}</h2>
              <p>{copy.startBody}</p>
            </div>
            <div className="showcase-resource-links">
              <a aria-label={copy.startReadme} href={docs.readme} target="_blank" rel="noreferrer"><span className="showcase-resource-links__icon"><BookOpen size={17} aria-hidden="true" /></span><span><b>{copy.startReadme}</b><small>README.md</small></span><ArrowUpRight size={15} aria-hidden="true" /></a>
              <a aria-label={copy.startDesign} href={docs.design} target="_blank" rel="noreferrer"><span className="showcase-resource-links__icon"><Workflow size={17} aria-hidden="true" /></span><span><b>{copy.startDesign}</b><small>PROJECT_DESIGN.md</small></span><ArrowUpRight size={15} aria-hidden="true" /></a>
              <a aria-label={copy.startPackaging} href={docs.packaging} target="_blank" rel="noreferrer"><span className="showcase-resource-links__icon"><FileText size={17} aria-hidden="true" /></span><span><b>{copy.startPackaging}</b><small>desktop_packaging.md</small></span><ArrowUpRight size={15} aria-hidden="true" /></a>
            </div>
          </div>
        </section>

        <section className="showcase-section showcase-download" id="download" aria-labelledby="download-title">
          <div className="showcase-container showcase-download__inner">
            <div><p className="showcase-eyebrow">{copy.downloadEyebrow}</p><h2 id="download-title">{copy.downloadTitle}</h2><p>{copy.downloadBody}</p></div>
            <a className="showcase-button showcase-button--primary" href={docs.packaging} target="_blank" rel="noreferrer">{copy.downloadButton}<ArrowUpRight size={16} aria-hidden="true" /></a>
          </div>
        </section>
      </main>

      <footer className="showcase-footer">
        <div className="showcase-container showcase-footer__inner">
          <a className="showcase-brand" href="#home"><span className="showcase-brand__mark" aria-hidden="true">V</span><span className="showcase-brand__copy"><strong>{copy.brand}</strong><small>{copy.subtitle}</small></span></a>
          <p>{copy.footerLine}</p>
          <div className="showcase-footer__links"><a href={docs.readme} target="_blank" rel="noreferrer"><BookOpen size={14} aria-hidden="true" />{copy.footerDocs}</a><a href={repository} target="_blank" rel="noreferrer"><Github size={14} aria-hidden="true" />{copy.footerRepo}</a></div>
          <small className="showcase-footer__access">{copy.footerAccess}</small>
        </div>
      </footer>
    </div>
  );
}

export function ShowcaseApp() {
  return <ThemeProvider><ShowcasePage /></ThemeProvider>;
}
