import { ArrowUpRight, Check, ChevronRight, FileText } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import "./showcase-docs.css";

const sourceRoot = "https://github.com/wenjiesong04/veyra-agent-platform/blob/HEAD";
const sections = ["get-started", "concepts", "first-agent", "acceptance"] as const;
type Section = typeof sections[number];

const text = {
  zh: {
    nav: "文档目录", items: ["快速开始", "认识 Agent 与 Workflow", "完成第一个任务", "检查结果与验收"],
    preview: "开发预览", previewBody: "当前面向本地开发与验证。公开安装包尚未通过发布验收，暂不提供下载。",
    startTitle: "先准备本地工作室。", startBody: "目前从源代码启动 Veyra。需要专用 Conda 环境、Node.js / npm 和仓库依赖；完整环境要求以仓库文档为准。以下命令在仓库根目录执行，前后端分别保持一个终端运行。",
    terminal: "终端", backend: "Local API", frontend: "桌面界面", backendNote: "先激活专用环境，再安装依赖并启动本地 API。首次建立环境时，按仓库的 environment.yml 创建。", frontendNote: "另开一个终端，启动浏览器中的桌面工作台。打开 http://127.0.0.1:5173。",
    portsTitle: "四个地址，各有职责。", portRows: [
      ["5173", "桌面工作台", "创建项目、构建、编辑和运行 Agent / Workflow。"],
      ["8771", "Local API", "本机的文件、模型调用、执行与运行记录。"],
      ["5174", "公开展示", "你正在浏览的官网、文档和社区目录。"],
      ["8772", "Community API", "账号与版本注册服务，不执行 Agent。"],
    ],
    optional: "账号和社区功能需要另行配置并启动 Community API；在激活环境的仓库根目录运行：", website: "只浏览官网时，在 web 目录运行 npm run dev:community 即可；官网主体不依赖 Local API。",
    setupTitle: "运行前，配置你要用的模型。", setupBody: "在桌面设置中添加 Provider 和凭据，再检查项目或 Agent 的模型绑定与工具是否就绪。Builder 的生成模型与 Agent 的运行模型是两项配置。密钥由设备凭据设施保存，项目定义只保存引用。外部模型是否收到资料，取决于你选择的输入、工具和配置。",
    source: "查看仓库说明", conceptsTitle: "选一个合适的工作方式。", conceptsBody: "Project 是工作空间。Agent 和 Workflow 是其中两种平级对象，用来解决不同的任务，不需要为了每一次模型判断都画流程图。",
    agentTitle: "Agent", agentTag: "一个自主工作的能力单元", agentBody: "你给出任务、方法、可用模型和工具。Agent 根据任务选择工具、读取结果，并继续处理，直到给出结果或触及运行限制。", agentExample: "例如：礼盒包装助手。根据品牌资料和需求提出方案，按你的反馈修改。", agentMap: "画布表示模型、说明、工具等能力的关系。连线不代表固定的执行顺序。",
    workflowTitle: "Workflow", workflowTag: "一条明确编排的工作流程", workflowBody: "当任务有固定阶段、条件分支或业务审批时，用 Workflow 明确安排每一步，并在阶段之间传递输入和输出。", workflowExample: "例如：整理需求 → 调用包装设计 Agent → 人工确认 → 整理交付。", workflowMap: "画布表示执行图。调用 Agent 时绑定明确的已保存版本。",
    versionTitle: "草稿用于编辑，版本用于明确执行。", versionBody: "在 Studio 中调整草稿，可以修改说明、能力与输入输出。检查完成后保存固定版本，再从应用运行。后续编辑草稿，不应悄悄改变你正在使用的那个版本。",
    taskTitle: "从一个小而完整的任务开始。", taskBody: "先写出输入、希望得到的结果和不能做的事。下面沿用首页的礼物包装任务，说明完整路径。",
    prompt: "帮我创建一个礼品包装设计助手。根据上传的商品照片和送礼场合提出设计方向，说明结构、配色与材料；缺少尺寸等信息时先问我，不要自行猜测。确认方向后再生成效果图，保留设计说明，修改或保存文件前让我确认。",
    promptLabel: "可以这样描述需求", steps: [
      ["描述目标", "在项目的 Veyra Chat 中说明需求，选择要提供的文件或资料。文件出现在项目里，不等于已经授权把全部内容发给模型。"],
      ["检查创建方案", "查看拟创建的 Agent 或 Workflow、输入输出、工具、权限和缺少的资源。确认方案后再应用；拒绝方案不会把它变成正式对象。"],
      ["打开 Studio", "检查说明、模型、工具和输入输出。继续用对话调整，或在画布、能力与源码视图中编辑同一份草稿。"],
      ["保存明确版本", "完成校验并提交版本。确认运行使用的版本与模型绑定、依赖和输入都符合本次任务。结构检查通过仍不等于业务结果正确。"],
      ["运行并处理等待", "从应用提交本次材料。观察执行进度；需要补充信息或批准操作时，先检查当前请求和影响范围，再回复、批准或拒绝。"],
      ["拿结果回到原始资料核对", "对照原始商品和你的要求检查设计：结构、配色、材料和效果图是否一致，尺寸和预算是否有依据。需要文件交付时，还要确认实际文件与操作回执。"],
    ],
    giftNote: "首页使用已有礼物包装案例的真实界面与图像候选。图像子任务已产出候选，但历史总流程有失败记录；完整业务交付、实际制作和设计质量仍需验收。",
    acceptanceTitle: "完成执行之后，还要检查交付。", acceptanceBody: "Veyra 会保留运行、工具操作、审批和产物等记录。用这些信息核对这次任务，而不是只凭“完成”两个字判断结果。",
    checks: [
      ["任务是否被完整执行", "检查原始要求、输入、固定版本和实际步骤，确认没有遗漏关键材料或约束。"],
      ["交付是否真的存在", "打开结果和产物，检查文件内容、引用、格式与工具回执。工具调用成功不自动证明最终内容合格。"],
      ["结果是否符合要求", "模型审查属于模型判断。需要独立事实、精确计算或人工判断的内容，仍要用适合的方法复核。"],
      ["失败后能否继续", "区分等待补充、等待审批、预算限制和失败。先读取错误与已有操作记录，再决定如何继续，避免重复外部操作。"],
    ],
    releaseTitle: "当前发布边界", releaseBody: "部分本地路径具备测试与运行记录，但整体验收仍需要固定同一份代码，分别检查真实 Provider、普通用户操作、跨任务重复交付、失败恢复，以及安装包启动、干净安装和升级。官网演示与单次成功记录不能替代这些证据。",
    packaging: "桌面构建与证据说明", design: "完整产品设计", status: "开发进展与已有证据", faq: "常见问题", faqs: [
      ["工作空间在本机，就代表完全离线吗？", "不是。项目和运行在本机管理，配置的模型或外部工具仍可能联网。请根据任务选择要发送的资料与允许的工具。"],
      ["Agent 运行完成，结果就已经验证了吗？", "不是。执行状态、工具回执和结果验证是不同的证据。模型审查也不是独立业务认证，仍要检查本次交付所需的事实和标准。"],
      ["可以直接下载桌面安装包吗？", "当前没有经过发布验收的公开安装包。开发者可以参考构建指南在自己的环境验证；本地构建成功不代表签名、公证和安装升级已经通过。"],
      ["社区会替我执行下载的 Agent 吗？", "不会。Community 提供账号和版本目录。导入前检查来源、依赖和权限，实际配置与执行留在本地工作台。"],
    ],
  },
  en: {
    nav: "Documentation contents", items: ["Get started", "Agents and Workflows", "Your first task", "Results and acceptance"],
    preview: "Development preview", previewBody: "For local development and validation. Public installers have not passed release acceptance, so no download is offered yet.",
    startTitle: "Prepare your local studio.", startBody: "Veyra currently runs from source. You need its dedicated Conda environment, Node.js / npm, and repository dependencies. Follow the repository for the complete requirements. Run these commands from the repository root, keeping a separate terminal for each process.",
    terminal: "Terminal", backend: "Local API", frontend: "Desktop interface", backendNote: "Activate the dedicated environment, install the dependencies, and start the local API. Create the environment from environment.yml first if needed.", frontendNote: "In another terminal, start the desktop workspace in your browser. Open http://127.0.0.1:5173.",
    portsTitle: "Four addresses, distinct roles.", portRows: [
      ["5173", "Desktop workspace", "Create projects, build, edit, and run Agents / Workflows."],
      ["8771", "Local API", "Local files, model calls, execution, and run records."],
      ["5174", "Public website", "This showcase, documentation, and community catalog."],
      ["8772", "Community API", "Accounts and version registry. It does not run Agents."],
    ],
    optional: "Account and community features require a separately configured Community API. Start it from the repository root with the environment active:", website: "To view the website alone, run npm run dev:community in web. The main showcase does not depend on the Local API.",
    setupTitle: "Configure a model before running.", setupBody: "Add a Provider and credential in Desktop settings, then check the project or Agent model binding and tool readiness. The Builder generation model and Agent runtime model are separate configurations. Device credential services keep secrets; project definitions keep references. Which materials reach external models depends on your selected inputs, tools, and settings.",
    source: "Repository setup", conceptsTitle: "Choose how the work should run.", conceptsBody: "A Project is your workspace. Agents and Workflows are peer objects within it, suited to different tasks. You do not need to draw every model decision as a flowchart.",
    agentTitle: "Agent", agentTag: "An autonomous capability unit", agentBody: "Give it a task, instructions, a model, and permitted tools. The Agent chooses tools, reads their results, and continues until it returns an output or reaches a runtime limit.", agentExample: "For example: a gift packaging assistant that proposes designs from your brand brief and revises them from your feedback.", agentMap: "Its canvas maps capabilities such as a model, instructions, and tools. Connections are not a fixed execution order.",
    workflowTitle: "Workflow", workflowTag: "An explicitly arranged process", workflowBody: "Use a Workflow when the task has defined stages, conditions, or business approvals. Set out the steps and pass typed inputs and outputs between them.", workflowExample: "For example: collect requirements → call the packaging Agent → human approval → prepare delivery.", workflowMap: "Its canvas is an execution graph. Agent calls bind an explicit saved version.",
    versionTitle: "Edit a draft. Run a defined version.", versionBody: "Use Studio to edit instructions, capabilities, and inputs / outputs. Check the draft, save a fixed version, then run it from the application. Later draft edits should not silently change the version you are using.",
    taskTitle: "Start with one small, complete task.", taskBody: "Specify the inputs, the result you need, and the boundaries. Follow the gift-packaging task from the homepage through its full path.",
    prompt: "Create a gift-packaging assistant from an uploaded product photo and the occasion. Propose directions with structure, palette, and materials. Ask about missing dimensions rather than guessing. After I confirm a direction, create a visual and retain design notes. Ask before changing or saving files.",
    promptLabel: "A request to start from", steps: [
      ["Describe the goal", "Use Veyra Chat in your Project and choose the files or materials to provide. A file being in the Project does not authorize sending all of it to a model."],
      ["Review the proposal", "Inspect the proposed Agent or Workflow, inputs, outputs, tools, permissions, and missing resources. Apply after reviewing it. Rejecting a proposal does not create the proposed object."],
      ["Open Studio", "Check the instructions, model, tools, and inputs / outputs. Continue the conversation or edit the same draft in canvas, capability, and source views."],
      ["Save a defined version", "Validate and commit a version. Check its model binding, dependencies, and inputs for this task. Passing structural validation does not establish business correctness."],
      ["Run and handle requests", "Submit this task's materials from the application. Watch progress and inspect any request for information or approval, including its scope, before replying, approving, or rejecting."],
      ["Check the result against the source", "Compare the design with the original product and brief: structure, colors, materials, and visuals should agree. Check the basis for dimensions and budget. For file delivery, also inspect the actual artifact and receipt."],
    ],
    giftNote: "The homepage uses real screens and an image candidate from an existing gift-packaging case. Its image task produced a candidate, while the parent workflow failed. Complete delivery, production suitability, and design quality still require acceptance.",
    acceptanceTitle: "Execution ends. Delivery still needs a check.", acceptanceBody: "Veyra keeps run, tool operation, approval, and artifact records. Use them to assess the task rather than relying on a completion message alone.",
    checks: [
      ["Was the complete task executed?", "Check the original request, inputs, fixed version, and actual steps for missing materials or constraints."],
      ["Does the delivery exist?", "Open the outputs and artifacts. Check content, references, format, and tool receipts. A successful tool call does not establish final quality."],
      ["Does the result meet the requirements?", "Model review is a model assessment. Independently check facts, exact calculations, or human judgments with an appropriate method."],
      ["Can a failed task continue safely?", "Distinguish requests for information, approval waits, budget limits, and failures. Read errors and existing operation records before continuing so external actions are not repeated blindly."],
    ],
    releaseTitle: "Current release boundary", releaseBody: "Some local paths have tests and run records. Overall acceptance still requires one fixed code revision and separate evidence for real Providers, ordinary user interactions, repeat delivery across tasks, failure recovery, package startup, clean installation, and upgrades. Website demonstrations and a single success do not replace these checks.",
    packaging: "Desktop builds and evidence", design: "Full product design", status: "Development status and evidence", faq: "Common questions", faqs: [
      ["Does local-first mean fully offline?", "No. Projects and runs are managed locally, but configured models and external tools may use the network. Choose the materials and tools appropriate to your task."],
      ["Is a completed Agent run a verified result?", "No. Execution state, tool receipts, and result verification are different evidence. Model review is not independent business certification. Check the facts and criteria required for the delivery."],
      ["Can I download a desktop installer?", "There is no public installer that has passed release acceptance yet. Developers can follow the build guide for local validation. A successful build does not prove signing, notarization, clean installation, or upgrades."],
      ["Will Community run a downloaded Agent for me?", "No. Community provides accounts and a version catalog. Inspect sources, dependencies, and permissions before importing; configuration and execution stay in your local workspace."],
    ],
  },
};

export function ShowcaseDocs({ locale, section }: { locale: "zh" | "en"; section?: string }) {
  const copy = text[locale];
  const [active, setActive] = useState<Section>(() => sections.includes(section as Section) ? section as Section : "get-started");
  const docsRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLElement>(null);
  const scheduleMeasurement = useRef<() => void>(() => {});

  useEffect(() => {
    const docs = docsRef.current;
    const scroller = docs?.closest<HTMLElement>(".showcase");
    if (!docs || !scroller) return;
    const header = scroller.querySelector<HTMLElement>(".showcase-header");
    const sidebar = docs.querySelector<HTMLElement>(".showcase-docs-sidebar");
    let frame = 0;

    function measure() {
      if (!docs || !scroller || scroller.clientHeight <= 0) return;
      const headerHeight = header?.getBoundingClientRect().height ?? 0;
      const inlineNavigation = getComputedStyle(docs).getPropertyValue("--showcase-docs-inline-nav").trim() === "1";
      const navigationHeight = inlineNavigation ? sidebar?.getBoundingClientRect().height ?? 0 : 0;
      const offset = headerHeight + navigationHeight + 24;
      docs.style.setProperty("--showcase-docs-header-offset", `${headerHeight}px`);
      docs.style.setProperty("--showcase-docs-scroll-offset", `${offset}px`);

      let next: Section = "get-started";
      const threshold = scroller.getBoundingClientRect().top + offset + 1;
      for (const id of sections) {
        const target = docs.querySelector<HTMLElement>(`#showcase-docs-${id}`);
        if (target && target.getBoundingClientRect().top <= threshold) next = id;
      }
      const maxScroll = scroller.scrollHeight - scroller.clientHeight;
      if (maxScroll > 0 && scroller.scrollTop >= maxScroll - 2) next = "acceptance";
      setActive(next);
    }

    function schedule() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    }

    scheduleMeasurement.current = schedule;
    scroller.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(schedule);
    observer?.observe(docs);
    if (header) observer?.observe(header);
    if (sidebar) observer?.observe(sidebar);
    schedule();
    return () => {
      scroller.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      observer?.disconnect();
      cancelAnimationFrame(frame);
      scheduleMeasurement.current = () => {};
    };
  }, []);

  useEffect(() => {
    if (!section || !sections.includes(section as Section)) return;
    setActive(section as Section);
    const frame = window.requestAnimationFrame(() => {
      document.getElementById(`showcase-docs-${section}`)?.scrollIntoView?.({ block: "start" });
      scheduleMeasurement.current();
    });
    return () => window.cancelAnimationFrame(frame);
  }, [section, locale]);

  useEffect(() => {
    const nav = navRef.current;
    const link = nav?.querySelector<HTMLElement>('[aria-current="location"]');
    if (!nav || !link || nav.scrollWidth <= nav.clientWidth) return;
    const navBounds = nav.getBoundingClientRect();
    const linkBounds = link.getBoundingClientRect();
    const delta = linkBounds.left < navBounds.left ? linkBounds.left - navBounds.left : linkBounds.right > navBounds.right ? linkBounds.right - navBounds.right : 0;
    if (delta) nav.scrollTo({ left: nav.scrollLeft + delta, behavior: "instant" });
  }, [active, locale]);

  return (
    <div ref={docsRef} className="showcase-docs showcase-wrap">
      <div className="showcase-docs-layout">
        <aside className="showcase-docs-sidebar">
          <nav ref={navRef} aria-label={copy.nav}>
            {sections.map((id, index) => <a href={`#/docs/${id}`} key={id} aria-current={active === id ? "location" : undefined}><span>0{index + 1}</span>{copy.items[index]}<ChevronRight size={14} /></a>)}
          </nav>
          <p className="showcase-docs-preview"><span>{copy.preview}</span>{copy.previewBody}</p>
        </aside>
        <div className="showcase-docs-content">
          <section id="showcase-docs-get-started" aria-labelledby="showcase-docs-start-title">
            <p className="showcase-docs-kicker">01 · {copy.items[0]}</p>
            <h1 id="showcase-docs-start-title">{copy.startTitle}</h1>
            <p>{copy.startBody}</p>
            <div className="showcase-docs-terminal"><div><span>{copy.terminal} 1</span>{copy.backend}</div><pre><code>{"conda activate veyra-agent-platform\nmake install\npython -m uvicorn veyra_agent_platform.local.app:app --host 127.0.0.1 --port 8771"}</code></pre></div>
            <p className="showcase-docs-caption">{copy.backendNote}</p>
            <div className="showcase-docs-terminal"><div><span>{copy.terminal} 2</span>{copy.frontend}</div><pre><code>{"cd web\nnpm ci\nnpm run dev:desktop"}</code></pre></div>
            <p className="showcase-docs-caption">{copy.frontendNote}</p>
            <h3>{copy.portsTitle}</h3>
            <dl className="showcase-docs-ports">{copy.portRows.map(([port, name, body]) => <div key={port}><dt><code>{port}</code><strong>{name}</strong></dt><dd>{body}</dd></div>)}</dl>
            <p>{copy.optional}</p>
            <pre className="showcase-docs-command"><code>python -m uvicorn veyra_agent_platform.community.app:app --host 127.0.0.1 --port 8772</code></pre>
            <p className="showcase-docs-caption">{copy.website}</p>
            <h3>{copy.setupTitle}</h3><p>{copy.setupBody}</p>
            <a className="showcase-docs-source" href={`${sourceRoot}/README.md`} target="_blank" rel="noreferrer">{copy.source}<ArrowUpRight size={15} /></a>
          </section>
          <section id="showcase-docs-concepts" aria-labelledby="showcase-docs-concepts-title">
            <p className="showcase-docs-kicker">02 · {copy.items[1]}</p><h2 id="showcase-docs-concepts-title">{copy.conceptsTitle}</h2><p>{copy.conceptsBody}</p>
            <div className="showcase-docs-concepts">
              <div><h3>{copy.agentTitle}</h3><span>{copy.agentTag}</span><p>{copy.agentBody}</p><p>{copy.agentExample}</p><p className="showcase-docs-caption">{copy.agentMap}</p></div>
              <div><h3>{copy.workflowTitle}</h3><span>{copy.workflowTag}</span><p>{copy.workflowBody}</p><p>{copy.workflowExample}</p><p className="showcase-docs-caption">{copy.workflowMap}</p></div>
            </div>
            <h3>{copy.versionTitle}</h3><p>{copy.versionBody}</p>
          </section>
          <section id="showcase-docs-first-agent" aria-labelledby="showcase-docs-task-title">
            <p className="showcase-docs-kicker">03 · {copy.items[2]}</p><h2 id="showcase-docs-task-title">{copy.taskTitle}</h2><p>{copy.taskBody}</p>
            <blockquote><span>{copy.promptLabel}</span><p>{copy.prompt}</p></blockquote>
            <ol className="showcase-docs-steps">{copy.steps.map(([title, body], index) => <li key={title}><span className="showcase-docs-step-number">{index + 1}</span><div><h3>{title}</h3><p>{body}</p></div></li>)}</ol>
            <p className="showcase-docs-callout"><FileText size={18} />{copy.giftNote}</p>
          </section>
          <section id="showcase-docs-acceptance" aria-labelledby="showcase-docs-acceptance-title">
            <p className="showcase-docs-kicker">04 · {copy.items[3]}</p><h2 id="showcase-docs-acceptance-title">{copy.acceptanceTitle}</h2><p>{copy.acceptanceBody}</p>
            <ul className="showcase-docs-checks">{copy.checks.map(([title, body]) => <li key={title}><Check size={17} /><div><h3>{title}</h3><p>{body}</p></div></li>)}</ul>
            <h3>{copy.releaseTitle}</h3><p>{copy.releaseBody}</p>
            <div className="showcase-docs-sources">{[["desktop_packaging.md", copy.packaging], ["PROJECT_DESIGN.md", copy.design], ["DEVELOPMENT.md", copy.status]].map(([file, label]) => <a className="showcase-docs-source" key={file} href={`${sourceRoot}/docs/${file}`} target="_blank" rel="noreferrer">{label}<ArrowUpRight size={15} /></a>)}</div>
            <h3 className="showcase-docs-faq-title">{copy.faq}</h3>
            <div className="showcase-docs-faq">{copy.faqs.map(([question, answer]) => <details key={question}><summary>{question}<ChevronRight size={17} /></summary><p>{answer}</p></details>)}</div>
          </section>
        </div>
      </div>
    </div>
  );
}
