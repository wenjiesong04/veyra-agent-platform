import { ArrowUpRight, Captions, Download, Maximize2, Pause, Play, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { demoCopy } from "./showcase-demo-copy";
import "./showcase-demo.css";

const videoSource = "/showcase/veyra-gift-tour.mp4";
const chapterStarts = [0, 8, 16, 24, 32];
type VideoWithIOSFullscreen = HTMLVideoElement & { webkitEnterFullscreen?: () => void };
const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || document.documentElement.dataset.motion === "reduced";

export function ShowcaseDemo({ locale }: { locale: "zh" | "en" }) {
  const copy = demoCopy[locale];
  const videoRef = useRef<HTMLVideoElement>(null);
  const figureRef = useRef<HTMLElement>(null);
  const pendingSeek = useRef<number | null>(null);
  const [chapter, setChapter] = useState(0);
  const [failed, setFailed] = useState(false);
  const [reduced, setReduced] = useState(reducedMotion);
  const [userPaused, setUserPaused] = useState(false);
  const [manualPlay, setManualPlay] = useState(false);
  const [visible, setVisible] = useState(true);
  const [foreground, setForeground] = useState(() => !document.hidden);
  const [playing, setPlaying] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const [captions, setCaptions] = useState(false);
  const [fullscreenUnavailable, setFullscreenUnavailable] = useState(false);
  const wantsPlayback = !userPaused && (!reduced || manualPlay);

  function playVideo() {
    const promise = videoRef.current?.play();
    promise?.then(() => setBlocked(false)).catch(() => setBlocked(true));
  }

  useEffect(() => {
    const query = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    const updateMotion = () => { const next = reducedMotion(); setReduced(next); if (next) setManualPlay(false); };
    const updateVisibility = () => setForeground(!document.hidden);
    const observer = new MutationObserver(updateMotion);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-motion"] });
    query?.addEventListener("change", updateMotion);
    document.addEventListener("visibilitychange", updateVisibility);
    const intersection = typeof IntersectionObserver === "undefined" ? null : new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.12 });
    if (figureRef.current) intersection?.observe(figureRef.current);
    return () => { observer.disconnect(); intersection?.disconnect(); query?.removeEventListener("change", updateMotion); document.removeEventListener("visibilitychange", updateVisibility); };
  }, []);

  useEffect(() => {
    if (wantsPlayback && visible && foreground && !failed) playVideo();
    else videoRef.current?.pause();
  }, [wantsPlayback, visible, foreground, failed]);

  function syncCaptions() {
    const tracks = videoRef.current?.textTracks;
    if (!tracks) return;
    for (let index = 0; index < tracks.length; index += 1) tracks[index].mode = captions && tracks[index].language === locale ? "showing" : "disabled";
  }
  useEffect(() => { syncCaptions(); }, [locale, captions]);

  function updateChapter() {
    const time = videoRef.current?.currentTime ?? 0;
    setChapter(chapterStarts.reduce((current, start, index) => time >= start ? index : current, 0));
  }

  function applyPendingSeek() {
    const video = videoRef.current;
    if (!video) return;
    if (pendingSeek.current !== null) {
      video.currentTime = Math.min(pendingSeek.current, Number.isFinite(video.duration) ? Math.max(0, video.duration - 0.1) : pendingSeek.current);
      pendingSeek.current = null;
    }
    updateChapter();
  }

  function selectChapter(index: number) {
    if (failed) return;
    pendingSeek.current = chapterStarts[index];
    if ((videoRef.current?.readyState ?? 0) >= HTMLMediaElement.HAVE_METADATA) applyPendingSeek();
  }

  function togglePlayback() {
    if (playing) { setUserPaused(true); videoRef.current?.pause(); }
    else { setManualPlay(true); setUserPaused(false); playVideo(); }
  }

  async function enterFullscreen() {
    const video = videoRef.current as VideoWithIOSFullscreen | null;
    if (!video) return;
    setFullscreenUnavailable(false);
    try {
      if (video.requestFullscreen) await video.requestFullscreen();
      else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen();
      else setFullscreenUnavailable(true);
    } catch { setFullscreenUnavailable(true); }
  }

  function retry() { pendingSeek.current = null; setFailed(false); setChapter(0); videoRef.current?.load(); }

  return (
    <figure ref={figureRef} className="showcase-demo" aria-label={copy.title}>
      <div className="showcase-video-frame">
        <video ref={videoRef} autoPlay={!reduced && !userPaused && visible && foreground} muted loop playsInline preload="auto" poster="/showcase/gift-poster.jpg" aria-label={copy.video} aria-describedby="showcase-video-note" onPlay={() => { setPlaying(true); setBlocked(false); }} onPause={() => setPlaying(false)} onTimeUpdate={updateChapter} onSeeked={updateChapter} onLoadedMetadata={() => { applyPendingSeek(); syncCaptions(); }} onError={() => setFailed(true)}>
          <source src={videoSource} type="video/mp4" />
          <track kind="captions" src="/showcase/gift.zh.vtt" srcLang="zh" label="中文" />
          <track kind="captions" src="/showcase/gift.en.vtt" srcLang="en" label="English" />
          {copy.unsupported}
        </video>
        <div className="showcase-video-controls">
          <button type="button" onClick={togglePlayback} aria-label={playing ? copy.pause : copy.play} title={playing ? copy.pause : copy.play}>{playing ? <Pause size={17} /> : <Play size={17} />}</button>
          <button type="button" onClick={() => setCaptions(!captions)} aria-label={copy.captions} aria-pressed={captions} title={copy.captions}><Captions size={18} /></button>
          <button type="button" onClick={enterFullscreen} aria-label={copy.fullscreen} title={copy.fullscreen}><Maximize2 size={17} /></button>
        </div>
        {blocked && !failed && <button className="showcase-video-start" type="button" onClick={togglePlayback}><Play size={19} />{copy.play}</button>}
        {failed && <div className="showcase-video-error" role="alert"><p>{copy.error}</p><div><button type="button" onClick={retry}><RotateCcw size={16} />{copy.retry}</button><a href="/showcase/gift-output.jpg" target="_blank" rel="noreferrer">{copy.original}<ArrowUpRight size={15} /></a></div></div>}
      </div>
      <div className="showcase-video-below"><ol className="showcase-video-chapters" aria-label={copy.chaptersLabel}>{copy.chapters.map((label, index) => <li key={label}><button type="button" aria-current={chapter === index ? "step" : undefined} disabled={failed} onClick={() => selectChapter(index)}><small>{String(index + 1).padStart(2, "0")}</small>{label}</button></li>)}</ol><a className="showcase-video-download" href={videoSource} download="veyra-gift-tour.mp4" aria-label={copy.download} title={copy.download}><Download size={16} /></a></div>
      <figcaption><p id="showcase-video-note">{copy.note}</p><details className="showcase-video-evidence"><summary>{copy.evidenceLabel}</summary><p>{copy.evidenceBody}</p><a href="/showcase/gift-runtime.png" target="_blank" rel="noreferrer">{copy.record}<ArrowUpRight size={13} /></a></details>{fullscreenUnavailable && <p role="status">{copy.fullscreenUnavailable}</p>}</figcaption>
    </figure>
  );
}
