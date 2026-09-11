/** Public and authenticated Community Agent registry wire contracts. */

export type CommunityForkOrigin = {
  owner_handle: string;
  slug: string;
  version: string;
  source_hash: string;
};

export type CommunityRegistryEntry = {
  schema_version: "community.registry.v1";
  owner_handle: string;
  owner_display_name: string | null;
  slug: string;
  name: string;
  description: string;
  version: string;
  source_hash: string;
  behavior_hash: string;
  lock_hash: string;
  status: "published";
  created_at: string;
  published_at: string | null;
  fork_of: CommunityForkOrigin | null;
  star_count: number;
  review_count: number;
  average_rating: number;
};

export type CommunityRegistryReview = {
  id: string;
  author_handle: string;
  author_display_name: string | null;
  rating: number;
  body: string;
  created_at: string;
  updated_at: string;
};

export type CommunityRegistryReviewsResponse = {
  schema_version: "community.feedback.v1";
  reviews: CommunityRegistryReview[];
};

export type CommunityRegistryFeedbackResponse = {
  schema_version: "community.feedback.v1";
  starred: boolean;
  star_count: number;
  review_count: number;
  average_rating: number;
};

export type CommunityRegistryReviewRequest = {
  rating: number;
  body: string;
};

export type CommunityRegistryReportRequest = {
  reason: string;
  details?: string;
};

export type CommunityRegistryReportResponse = {
  schema_version: "community.feedback.v1";
  report_id: string;
  status: string;
};

export type CommunityRegistryListResponse = {
  schema_version: "community.registry.v1";
  entries: CommunityRegistryEntry[];
};
