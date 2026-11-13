/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public Community website base URL; never put credentials or tokens here. */
  readonly VITE_COMMUNITY_SITE_URL?: string;
}

interface Window {
  readonly veyraDesktop?: {
    openExternal(url: string): Promise<void>;
  };
}
