import type {
  CommunityRegistryEntry,
  CommunityRegistryReview,
} from "@veyra/api-contracts";
import type { CommunityApi } from "@veyra/connected-account";
import { Button, ErrorState, Panel, SectionHeading, Tag, useLocale } from "@veyra/ui";
import { useCallback, useEffect, useState } from "react";

type CommunityFeedbackPanelProps = {
  entry: CommunityRegistryEntry;
  communityApi: CommunityApi;
};

export function CommunityFeedbackPanel({
  entry,
  communityApi,
}: CommunityFeedbackPanelProps) {
  const { locale } = useLocale();
  const zh = locale === "zh";
  const [starred, setStarred] = useState(false);
  const [starCount, setStarCount] = useState(entry.star_count);
  const [reviewCount, setReviewCount] = useState(entry.review_count);
  const [averageRating, setAverageRating] = useState(entry.average_rating);
  const [reviews, setReviews] = useState<CommunityRegistryReview[]>([]);
  const [rating, setRating] = useState("5");
  const [reviewBody, setReviewBody] = useState("");
  const [reportReason, setReportReason] = useState("quality");
  const [reportDetails, setReportDetails] = useState("");
  const [busy, setBusy] = useState<"star" | "review" | "report" | null>(null);
  const [error, setError] = useState("");

  const applyFeedback = (next: { star_count: number; review_count: number; average_rating: number }) => {
    setStarCount(next.star_count);
    setReviewCount(next.review_count);
    setAverageRating(next.average_rating);
  };

  const loadReviews = useCallback(async () => {
    try {
      setReviews((await communityApi.listRegistryReviews(entry.owner_handle, entry.slug, entry.version)).reviews);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "无法读取评价。" : "Could not load reviews."));
    }
  }, [communityApi, entry.owner_handle, entry.slug, entry.version, zh]);

  const loadStarStatus = useCallback(async () => {
    try {
      const result = await communityApi.getRegistryStarStatus(entry.owner_handle, entry.slug, entry.version);
      setStarred(result.starred);
      applyFeedback(result);
    } catch {
      // An expired session should not prevent public reviews from rendering.
    }
  }, [communityApi, entry.owner_handle, entry.slug, entry.version]);

  useEffect(() => { void loadReviews(); }, [loadReviews]);
  useEffect(() => { void loadStarStatus(); }, [loadStarStatus]);

  const toggleStar = async () => {
    setBusy("star");
    setError("");
    try {
      const result = starred
        ? await communityApi.unstarRegistryAgent(entry.owner_handle, entry.slug, entry.version)
        : await communityApi.starRegistryAgent(entry.owner_handle, entry.slug, entry.version);
      setStarred(result.starred);
      applyFeedback(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "更新收藏失败。" : "Could not update star."));
    } finally {
      setBusy(null);
    }
  };

  const submitReview = async () => {
    if (!reviewBody.trim()) return;
    setBusy("review");
    setError("");
    try {
      const result = await communityApi.reviewRegistryAgent(
        entry.owner_handle,
        entry.slug,
        entry.version,
        { rating: Number(rating), body: reviewBody.trim() },
      );
      setReviewBody("");
      applyFeedback(result);
      await loadReviews();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "提交评价失败。" : "Could not submit review."));
    } finally {
      setBusy(null);
    }
  };

  const submitReport = async () => {
    setBusy("report");
    setError("");
    try {
      await communityApi.reportRegistryAgent(
        entry.owner_handle,
        entry.slug,
        entry.version,
        { reason: reportReason, details: reportDetails.trim() },
      );
      setReportDetails("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : (zh ? "提交举报失败。" : "Could not submit report."));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Panel className="community-feedback-panel">
      <SectionHeading
        eyebrow={zh ? "社区反馈" : "Community feedback"}
        title={zh ? "版本反馈" : "Version feedback"}
        detail={zh ? "Star 和 Review 绑定到这个不可变版本；它们不代表安全或效果保证。" : "Stars and reviews bind to this immutable version; neither is a safety or quality guarantee."}
      />
      <div className="community-feedback-summary">
        <Button variant={starred ? "secondary" : "ghost"} onClick={() => void toggleStar()} disabled={busy !== null}>
          {starred ? (zh ? "已 Star" : "Starred") : "Star"}
        </Button>
        <Tag>{starCount} {zh ? "个 Star" : "stars"}</Tag>
        <Tag>{averageRating ? `${averageRating.toFixed(1)} / 5` : (zh ? "暂无评分" : "No rating")}</Tag>
        <Tag>{reviewCount} {zh ? "条评价" : "reviews"}</Tag>
      </div>
      <div className="community-feedback-form">
        <label>
          <span>{zh ? "评分" : "Rating"}</span>
          <select value={rating} onChange={(event) => setRating(event.target.value)} disabled={busy !== null}>
            {[5, 4, 3, 2, 1].map((value) => <option key={value} value={value}>{value} / 5</option>)}
          </select>
        </label>
        <label>
          <span>{zh ? "评价" : "Review"}</span>
          <textarea value={reviewBody} onChange={(event) => setReviewBody(event.target.value)} rows={3} maxLength={4_000} placeholder={zh ? "这次版本实际帮你完成了什么？" : "What did this version help you do?"} disabled={busy !== null} />
        </label>
        <Button variant="primary" disabled={busy !== null || !reviewBody.trim()} onClick={() => void submitReview()}>{busy === "review" ? "…" : (zh ? "提交评价" : "Submit review")}</Button>
      </div>
      {reviews.length ? <div className="community-review-list">{reviews.map((review) => <article key={review.id}><div><strong>{review.author_display_name || review.author_handle}</strong><Tag>{review.rating} / 5</Tag></div><p>{review.body}</p></article>)}</div> : <p className="resource-detail-muted">{zh ? "还没有评价。" : "No reviews yet."}</p>}
      <details className="community-report-form">
        <summary>{zh ? "报告这个版本" : "Report this version"}</summary>
        <label><span>{zh ? "原因" : "Reason"}</span><select value={reportReason} onChange={(event) => setReportReason(event.target.value)} disabled={busy !== null}><option value="quality">{zh ? "质量问题" : "Quality"}</option><option value="security">{zh ? "安全问题" : "Security"}</option><option value="copyright">{zh ? "版权问题" : "Copyright"}</option><option value="spam">Spam</option></select></label>
        <label><span>{zh ? "补充说明" : "Details"}</span><textarea value={reportDetails} onChange={(event) => setReportDetails(event.target.value)} rows={3} maxLength={4_000} disabled={busy !== null} /></label>
        <Button variant="danger" disabled={busy !== null} onClick={() => void submitReport()}>{busy === "report" ? "…" : (zh ? "提交举报" : "Submit report")}</Button>
      </details>
      {error ? <ErrorState message={error} onRetry={() => void loadReviews()} /> : null}
    </Panel>
  );
}
