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
};

export type CommunityRegistryListResponse = {
  schema_version: "community.registry.v1";
  entries: CommunityRegistryEntry[];
};
