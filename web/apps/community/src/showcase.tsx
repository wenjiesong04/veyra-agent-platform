import { ArrowRight, ArrowUpRight, BookOpen, Check, ChevronRight, FileText, Maximize2, Menu, Moon, Play, RotateCcw, ShieldCheck, Sun, X } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ThemeProvider, useLocale, useTheme } from "@veyra/ui";
import { showcaseCopy } from "./showcase-copy";
import { ShowcaseDemo } from "./showcase-demo";
import { ShowcaseDocs } from "./showcase-docs";
import { ShowcaseBrief, ShowcaseOutput } from "./showcase-case";
import "./showcase.css";

const repository = "https://github.com/wenjiesong04/veyra-agent-platform";
const branch = `${repository}/blob/codex/agent-platform`;
const sources = ["gift-input.jpg", "gift-studio.png", "gift-runtime.png"] as const;
const linkTargets = ["#/docs/get-started", repository, `${branch}/docs/desktop_packaging.md`];
const sectionTargets = ["#demo", "#product", "#safety", "#/docs", "#/community"];

type ShowcasePageProps = { documentation?: boolean; documentSection?: string; community?: boolean; children?: ReactNode; headerAccount?: ReactNode };

function ShowcasePage({ documentation = false, documentSection, community = false, children, headerAccount }: ShowcasePageProps) {
  const { locale, setLanguage } = useLocale();
  const { effectiveDark, setTheme } = useTheme();
  const copy = showcaseCopy[locale];
  const [scene, setScene] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const [decision, setDecision] = useState<0 | 1 | 2>(0);
  const [expandedImage, setExpandedImage] = useState({ src: "", alt: "" });
  const dialogRef = useRef<HTMLDialogElement>(null);
  const menuRef = useRef<HTMLButtonElement>(null);
  const approveRef = useRef<HTMLButtonElement>(null);
  const resetRef = useRef<HTMLButtonElement>(null);
  const decisionChanged = useRef(false);
  const sceneButtons = useRef<(HTMLButtonElement | null)[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [activeSection, setActiveSection] = useState("");

  useEffect(() => {
    const root = scrollRef.current;
    if (!root) return;
    let frame = 0;
    function measure() {
      if (!root) return;
      if (community) { setActiveSection("#/community"); return; }
      if (documentation) { setActiveSection("#/docs"); return; }
      let active = "";
      for (const [index, id] of ["demo", "product", "safety", "docs"].entries()) {
        const section = document.getElementById(id);
        if (section && section.getBoundingClientRect().top <= root.getBoundingClientRect().top + 145) active = sectionTargets[index];
      }
      setActiveSection(active);
    }
    function schedule() { cancelAnimationFrame(frame); frame = requestAnimationFrame(measure); }
    root.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(schedule);
    observer?.observe(root.querySelector("main") ?? root);
    measure();
    return () => { root.removeEventListener("scroll", schedule); window.removeEventListener("resize", schedule); observer?.disconnect(); cancelAnimationFrame(frame); };
  }, [documentation, community]);

  useEffect(() => {
    setMenuOpen(false);
    const frame = requestAnimationFrame(() => {
      if (documentation && documentSection) return;
      const target = document.getElementById(window.location.hash.slice(1));
      if (target) target.scrollIntoView({ behavior: "instant", block: "start" });
      else scrollRef.current?.scrollTo({ top: 0, behavior: "instant" });
    });
    return () => cancelAnimationFrame(frame);
  }, [documentation, documentSection, community]);

  useEffect(() => {
    const originalTitle = document.title;
    const originalLanguage = document.documentElement.lang;
    return () => {
      document.title = originalTitle;
      document.documentElement.lang = originalLanguage;
    };
  }, []);

  useEffect(() => {
    const requested = new URLSearchParams(window.location.search).get("lang");
    if (requested === "zh" || requested === "en") setLanguage(requested);
  }, [setLanguage]);

  useEffect(() => {
    if (!menuOpen) return;
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      menuRef.current?.focus();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [menuOpen]);

  useEffect(() => {
    if (!decisionChanged.current) return;
    (decision === 0 ? approveRef : resetRef).current?.focus();
  }, [decision]);

  function decide(next: 0 | 1 | 2) {
    decisionChanged.current = true;
    setDecision(next);
  }

  function changeLanguage() {
    const next = locale === "zh" ? "en" : "zh";
    const url = new URL(window.location.href);
    url.searchParams.set("lang", next);
    window.history.replaceState(window.history.state, "", url);
    setLanguage(next);
  }

  useEffect(() => {
    document.title = community ? `${locale === "zh" ? "社区" : "Community"} · Veyra` : documentation ? `${locale === "zh" ? "项目文档" : "Documentation"} · Veyra` : copy.title;
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  }, [copy.title, locale, documentation, community]);

  function enlarge(src: string, alt: string) {
    setExpandedImage({ src, alt });
    dialogRef.current?.showModal();
  }

  function changeScene(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % 3;
    else if (event.key === "ArrowLeft") next = (index + 2) % 3;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = 2;
    else return;
    event.preventDefault();
    setScene(next);
    sceneButtons.current[next]?.focus();
  }

  return (
    <div ref={scrollRef} className="showcase" data-dark={effectiveDark} onClickCapture={(event) => {
      const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[href^="#/docs"]') : null;
      const href = anchor?.getAttribute("href");
      if (!href || href !== window.location.hash) return;
      event.preventDefault();
      const section = href.split("/")[2];
      const target = section ? document.getElementById(`showcase-docs-${section}`) : null;
      if (target) target.scrollIntoView({ block: "start" });
      else scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
      setMenuOpen(false);
    }}>
      <a className="showcase-skip" href="#main" onClick={(event) => { event.preventDefault(); document.getElementById("main")?.focus({ preventScroll: true }); scrollRef.current?.scrollTo({ top: 0, behavior: "instant" }); }}>{copy.skip}</a>
      <header className="showcase-header">
        <a className="showcase-brand" href="#home" aria-label="Veyra"><img src="/veyra-icon.png" alt="" width="32" height="32" /><span>Veyra</span></a>
        <nav id="showcase-navigation" className={menuOpen ? "showcase-nav is-open" : "showcase-nav"} aria-label={copy.navigation}>
          {copy.nav.map((label, index) => <a key={sectionTargets[index]} href={sectionTargets[index]} aria-current={activeSection === sectionTargets[index] ? "location" : undefined} onClick={() => setMenuOpen(false)}>{label}</a>)}
        </nav>
        <div className="showcase-header-actions">
          <button type="button" className="showcase-icon" aria-label={copy.language} title={copy.language} onClick={changeLanguage}>{locale === "zh" ? "EN" : "中文"}</button>
          <button type="button" className="showcase-icon" aria-label={effectiveDark ? copy.light : copy.dark} title={effectiveDark ? copy.light : copy.dark} onClick={() => setTheme(effectiveDark ? "light" : "dark")}>{effectiveDark ? <Sun size={19} /> : <Moon size={19} />}</button>
          <a className="showcase-header-start" href="#/docs/get-started">{copy.getStarted}<ArrowRight size={15} /></a>
          <button ref={menuRef} type="button" className="showcase-icon showcase-menu" aria-label={menuOpen ? copy.closeMenu : copy.menu} aria-expanded={menuOpen} aria-controls="showcase-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={20} /> : <Menu size={20} />}</button>
          {headerAccount}
        </div>
      </header>

      <main id="main" tabIndex={-1}>
        {community ? children : documentation ? <ShowcaseDocs locale={locale} section={documentSection} /> : <>
        <section id="home" className="showcase-hero" aria-labelledby="showcase-title">
          <div className="showcase-hero-grid">
          <div className="showcase-hero-copy">
            <p className="showcase-hero-line">{copy.heroLine}</p>
            <h1 id="showcase-title">{copy.heroTitle[0]}<br /><span>{copy.heroTitle[1]}</span></h1>
            <p className="showcase-hero-body">{copy.heroBody}</p>
            <div className="showcase-actions"><a className="showcase-primary" href="#/docs/get-started"><BookOpen size={16} />{copy.getStarted}<ArrowRight size={15} /></a><a className="showcase-text-link" href="#product"><Play size={15} />{copy.watchDemo}</a></div>
            <p className="showcase-preview">{copy.preview}</p>
          </div>
          <div id="demo" className="showcase-demo-anchor"><p className="showcase-case-label">{copy.heroCaption}</p><ShowcaseDemo locale={locale} /></div>
          </div>
        </section>

        <section id="product" className="showcase-experience" aria-labelledby="showcase-experience-title">
          <span id="experience" className="showcase-anchor" aria-hidden="true" />
          <div className="showcase-wrap">
            <p className="showcase-eyebrow">01 / {copy.productEyebrow}</p>
            <div className="showcase-section-intro"><h2 id="showcase-experience-title">{copy.experienceTitle[0]}<br />{copy.experienceTitle[1]}</h2><p>{copy.experienceBody}</p></div>
            <div className="showcase-tour-tabs" role="tablist" aria-label={copy.tour}>
              {copy.tabs.map((label, index) => <button key={label} ref={(element) => { sceneButtons.current[index] = element; }} type="button" id={`showcase-tab-${index}`} role="tab" aria-selected={scene === index} aria-controls={`showcase-scene-${index}`} tabIndex={scene === index ? 0 : -1} onClick={() => setScene(index)} onKeyDown={(event) => changeScene(event, index)}>{label}<ChevronRight size={16} /></button>)}
            </div>
            {copy.scenes.map((item, index) => <div key={sources[index]} id={`showcase-scene-${index}`} role="tabpanel" aria-labelledby={`showcase-tab-${index}`} hidden={scene !== index} tabIndex={0}>
              {index === 0 ? <ShowcaseBrief locale={locale} onEnlarge={enlarge} /> : index === 2 ? <ShowcaseOutput locale={locale} onEnlarge={enlarge} /> : <><figure className="showcase-tour-image"><img src={`/showcase/${sources[index]}`} alt={item.alt} width="1470" height="835" loading="lazy" /><button className="showcase-image-zoom" type="button" aria-label={copy.enlarge} title={copy.enlarge} onClick={() => enlarge(sources[index], item.alt)}><Maximize2 size={20} /></button></figure><div className="showcase-tour-caption"><div><h3>{item.title}</h3><p>{item.body}</p></div><span>{item.caption}</span></div></>}
            </div>)}
            <p className="showcase-recording">{copy.recording}</p>
          </div>
        </section>

        <section id="how-it-works" className="showcase-method" aria-labelledby="showcase-method-title">
          <div className="showcase-wrap showcase-method-grid">
            <div className="showcase-method-copy"><p className="showcase-eyebrow">02 / {copy.methodEyebrow}</p><h2 id="showcase-method-title">{copy.editTitle[0]}<br />{copy.editTitle[1]}</h2><p>{copy.editBody}</p><a className="showcase-text-link" href="#/docs/concepts">{copy.editLink}<ArrowRight size={17} /></a></div>
            <figure><button className="showcase-media-button" type="button" aria-label={copy.enlarge} onClick={() => enlarge("gift-capabilities.png", copy.editAlt)}><img src="/showcase/gift-capabilities.png" alt={copy.editAlt} width="1470" height="835" loading="lazy" /></button><figcaption>{copy.editCaption}</figcaption></figure>
          </div>
        </section>

        <section className="showcase-evidence" aria-labelledby="showcase-evidence-title">
          <div className="showcase-wrap">
            <p className="showcase-eyebrow">03 / {copy.evidenceEyebrow}</p>
            <div className="showcase-section-intro"><h2 id="showcase-evidence-title">{copy.evidenceTitle}</h2><div><p>{copy.evidenceBody}</p><p className="showcase-note">{copy.evidenceNote}</p></div></div>
            <div className="showcase-gift-comparison"><figure><button className="showcase-media-button" type="button" aria-label={copy.enlarge} onClick={() => enlarge("gift-input.jpg", copy.scenes[0].alt)}><img src="/showcase/gift-input.jpg" alt={copy.scenes[0].alt} width="746" height="746" loading="lazy" /></button><figcaption>{copy.inputCaption}</figcaption></figure><figure><button className="showcase-media-button" type="button" aria-label={copy.enlarge} onClick={() => enlarge("gift-output.jpg", copy.evidenceCaption)}><img src="/showcase/gift-output.jpg" alt={copy.evidenceCaption} width="1600" height="1600" loading="lazy" /></button><figcaption>{copy.outputCaption}</figcaption></figure></div>
          </div>
        </section>

        <section id="safety" className="showcase-control" aria-labelledby="showcase-control-title">
          <span id="control" className="showcase-anchor" aria-hidden="true" />
          <div className="showcase-wrap showcase-control-grid">
            <div><p className="showcase-eyebrow">04 / {copy.controlEyebrow}</p><h2 id="showcase-control-title">{copy.controlTitle[0]}<br />{copy.controlTitle[1]}</h2><p>{copy.controlBody}</p><p className="showcase-control-local">{copy.controlLocal}</p></div>
            <div className="showcase-approval">
              <div className="showcase-approval-label"><ShieldCheck size={20} /><span>{copy.approvalLabel}</span></div>
              <h3>{copy.approvalTitle}</h3><p>{copy.approvalBody}</p>
              <dl><div><dt>{copy.target}</dt><dd><FileText size={17} />{copy.approvalFile}</dd></div><div><dt>{copy.impact}</dt><dd>{copy.impactValue}</dd></div></dl>
              <p className="showcase-decision" role="status" aria-live="polite">{decision === 1 ? <Check size={18} /> : decision === 2 ? <X size={18} /> : <span className="showcase-wait-dot" />}{copy.status[decision]}</p>
              <div className="showcase-approval-actions">{decision === 0 ? <><button ref={approveRef} className="showcase-primary" type="button" onClick={() => decide(1)}><Check size={16} />{copy.approve}</button><button className="showcase-reject" type="button" onClick={() => decide(2)}><X size={16} />{copy.reject}</button></> : <button ref={resetRef} className="showcase-reset" type="button" onClick={() => decide(0)}><RotateCcw size={16} />{copy.reset}</button>}</div>
              <p className="showcase-note">{decision === 0 ? copy.approvalNote : decision === 1 ? copy.approvedNote : copy.rejectedNote}</p>
            </div>
          </div>
        </section>

        <section id="docs" className="showcase-start" aria-labelledby="showcase-start-title"><span id="start" className="showcase-anchor" aria-hidden="true" /><div className="showcase-wrap"><p className="showcase-eyebrow">05 / {copy.startEyebrow}</p><div className="showcase-section-intro"><h2 id="showcase-start-title">{copy.startTitle[0]}<br />{copy.startTitle[1]}</h2><p>{copy.startBody}</p></div><div className="showcase-start-links">{copy.links.map((item, index) => <a key={item.title} href={linkTargets[index]} target={index === 0 ? undefined : "_blank"} rel={index === 0 ? undefined : "noreferrer"}><div><h3>{item.title}</h3><p>{item.body}</p></div>{index === 0 ? <ArrowRight size={24} /> : <ArrowUpRight size={24} />}</a>)}</div><p id="download" className="showcase-release">{copy.release}</p></div></section>
        </>}
      </main>

      <dialog ref={dialogRef} className="showcase-image-dialog" aria-label={copy.enlarge} onClick={(event) => { if (event.target === event.currentTarget) dialogRef.current?.close(); }}><div className="showcase-image-actions"><a className="showcase-icon" href={`/showcase/${expandedImage.src}`} target="_blank" rel="noreferrer" aria-label={copy.originalImage} title={copy.originalImage}><ArrowUpRight size={21} /></a><button autoFocus className="showcase-icon" type="button" aria-label={copy.closeImage} title={copy.closeImage} onClick={() => dialogRef.current?.close()}><X size={24} /></button></div><div className="showcase-image-stage">{expandedImage.src ? <img src={`/showcase/${expandedImage.src}`} alt={expandedImage.alt} width="1440" height="900" /> : null}</div></dialog>
    </div>
  );
}

export function ShowcaseApp(props: ShowcasePageProps) {
  return <ThemeProvider><ShowcasePage {...props} /></ThemeProvider>;
}
