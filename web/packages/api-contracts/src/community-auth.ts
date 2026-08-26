export const communityAuthRoutePaths = {
  login: "#/login",
  register: "#/register",
  forgotPassword: "#/forgot-password",
  account: "#/account",
} as const;

export const communityAccountApiPaths = {
  me: "/account/me",
  profile: "/account/profile",
  sessions: "/account/sessions",
  avatar: "/account/avatar",
} as const;

export type CommunityAccount = {
  id: string;
  email: string;
  handle: string;
  display_name: string | null;
  avatar_url: string | null;
};

export type CommunityAuthenticatedResponse = {
  schema_version: "community.auth.v1";
  authenticated: true;
  account: CommunityAccount;
};

export type CommunityAcceptedResponse = {
  schema_version: "community.auth.v1";
  accepted: true;
};

export type CommunityPasswordResetResponse = {
  schema_version: "community.auth.v1";
  reset: true;
};

export type CommunityMeResponse = {
  schema_version: "community.account.v1";
  account: CommunityAccount;
};

export type CommunityDeviceSession = {
  id: string;
  device_name: string | null;
  user_agent: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
};

export type CommunitySessionListResponse = {
  schema_version: "community.account.v1";
  sessions: CommunityDeviceSession[];
};

export type CommunityEmailRequest = {
  email: string;
  device_name?: string;
};

export type CommunityRegistrationRequest = CommunityEmailRequest & {
  handle?: string;
  password: string;
  verification_code: string;
  display_name?: string;
};

export type CommunityVerificationCodeRequest = CommunityEmailRequest & {
  purpose: "registration" | "password_reset";
};

export type CommunityLoginRequest = CommunityEmailRequest & {
  password: string;
};

export type CommunityPasswordResetRequest = CommunityEmailRequest & {
  verification_code: string;
  new_password: string;
};

export type CommunityProfileUpdate = {
  display_name?: string;
  handle?: string;
};
