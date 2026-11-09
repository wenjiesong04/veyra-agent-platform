import { ArrowUpRight, Maximize2 } from "lucide-react";
import "./showcase-case.css";

const caseCopy = {
  zh: {
    briefLabel: "原始创建需求 · 节选",
    brief: [
      "帮我做一个礼品包装设计 Agent。",
      "用户可以上传需要包装的商品图片，再告诉它送给谁、什么场合、预算和喜欢的风格。",
      "用户确认以后，再生成最终包装方案和包装效果图，最后检查是否满足预算、尺寸、保护和设计要求。",
    ],
    fields: [["输入", "商品照片、送礼场合、风格和预算"], ["本次场景", "圣诞礼赠"], ["目标", "设计方向、结构与材料说明、包装效果图"], ["边界", "看不清尺寸时先问；允许继续修改当前设计"]],
    input: "本次商品照片", inputAlt: "案例输入：粉色圆形分格糖果盒，带蝴蝶结盖钮。",
    resultLabel: "已有图像产物", title: "「圣诞恋歌」圆形糖果礼盒",
    summary: "从原有的圆盒、分格和蝴蝶结出发，提出圣诞礼赠方向。",
    notes: [["结构方向", "圆形分格盒，保留蝴蝶结元素"], ["配色方案", "圣诞红、奶油白与金色"], ["材料建议", "纸浆盒身、丝绒丝带、分格内托"], ["制作前确认", "尺寸、文字、材料可行性与预算"]],
    resultAlt: "该案例实际生成的圣诞糖果礼盒候选图：红色圆盒、奶油白盒盖、蝴蝶结、糖果和贺卡。",
    enlarge: "放大产品画面", candidate: "设计候选 · 待复核",
    evidence: "这份结果验证到了哪一步？",
    evidenceBody: "“未验证”表示运行留下了产物，但尚无独立验收结论。这个历史案例的图像子任务产出了候选图，父工作流存在失败记录，因此不能将它视为完整任务已经通过。图中的文字、尺寸、材料和成本仍需人工核对。",
    original: "查看原始运行画面", originalAlt: "原始 Renderer 运行详情，保留未验证状态和图像产物。",
  },
  en: {
    briefLabel: "Original brief · Translated excerpts",
    brief: [
      "Build a gift-packaging design Agent.",
      "Let users upload a product photo and provide the recipient, occasion, budget, and preferred style.",
      "After confirmation, generate the packaging plan and visual, then check the budget, dimensions, protection, and design requirements.",
    ],
    fields: [["Inputs", "Product photo, occasion, style, and budget"], ["This case", "Christmas gifting"], ["Deliverables", "Design directions, structure, materials, and a packaging visual"], ["Boundaries", "Ask about unknown dimensions; retain the current design for revision"]],
    input: "Product photo for this task", inputAlt: "Case input: a pink round divided candy box with a bow on the lid.",
    resultLabel: "Existing image artifact", title: "A Christmas candy gift box",
    summary: "A festive direction based on the original round box, compartments, and bow.",
    notes: [["Structure", "Round divided box with a bow"], ["Palette", "Christmas red, ivory, and gold"], ["Suggested materials", "Pulp box, velvet ribbon, and divided insert"], ["Before production", "Check dimensions, text, material feasibility, and budget"]],
    resultAlt: "The actual generated Christmas gift-box candidate: red round box, ivory lid, bow, candy, and a card.",
    enlarge: "Enlarge product image", candidate: "Design candidate · Needs review",
    evidence: "What has been verified?",
    evidenceBody: "Unverified means an artifact exists without an independent acceptance conclusion. This historical image task produced a candidate, while the parent Workflow failed. It does not establish complete task acceptance. Text, dimensions, materials, and costs still need human review.",
    original: "View the original run screen", originalAlt: "Original Renderer run details retaining the unverified status and image artifact.",
  },
};

type Props = { locale: "zh" | "en"; onEnlarge: (file: string, alt: string) => void };

export function ShowcaseBrief({ locale, onEnlarge }: Props) {
  const copy = caseCopy[locale];
  return <div className="showcase-case-brief">
    <div className="showcase-brief-content">
      <p className="showcase-case-kicker">{copy.briefLabel}</p>
      <blockquote>{copy.brief.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}</blockquote>
      <dl>{copy.fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
    </div>
    <figure className="showcase-brief-photo">
      <button type="button" aria-label={copy.enlarge} onClick={() => onEnlarge("gift-input.jpg", copy.inputAlt)}><img src="/showcase/gift-input.jpg" alt={copy.inputAlt} width="746" height="746" loading="lazy" /><Maximize2 size={18} /></button>
      <figcaption>{copy.input}</figcaption>
    </figure>
  </div>;
}

export function ShowcaseOutput({ locale, onEnlarge }: Props) {
  const copy = caseCopy[locale];
  return <div className="showcase-case-output">
    <figure className="showcase-output-art">
      <button type="button" aria-label={copy.enlarge} onClick={() => onEnlarge("gift-output.jpg", copy.resultAlt)}><img src="/showcase/gift-output.jpg" alt={copy.resultAlt} width="1600" height="1600" loading="lazy" /><Maximize2 size={18} /></button>
      <figcaption>{copy.candidate}</figcaption>
    </figure>
    <div className="showcase-output-notes">
      <p className="showcase-case-kicker">{copy.resultLabel}</p><h3>{copy.title}</h3><p>{copy.summary}</p>
      <dl>{copy.notes.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      <details className="showcase-case-evidence"><summary>{copy.evidence}</summary><p>{copy.evidenceBody}</p><button type="button" onClick={() => onEnlarge("gift-runtime.png", copy.originalAlt)}>{copy.original}<ArrowUpRight size={14} /></button></details>
    </div>
  </div>;
}
