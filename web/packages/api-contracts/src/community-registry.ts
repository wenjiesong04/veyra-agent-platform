/** Public and authenticated Community Agent registry wire contracts. */

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
};

export type CommunityRegistryListResponse = {
  schema_version: "community.registry.v1";
  entries: CommunityRegistryEntry[];
};
