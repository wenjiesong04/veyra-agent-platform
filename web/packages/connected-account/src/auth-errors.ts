import { CommunityApiError } from "./api";

export type AuthErrorSurface = "login" | "register" | "reset" | "account";
export type AuthErrorField = "email" | "password" | "code";

export type AuthErrorExplanation = {
  message: string;
  field?: AuthErrorField;
};

export type ErrorCopy = {
  invalidCredentials: string;
  registrationUnavailable: string;
  invalidCode: string;
  passwordPolicy: string;
  profileUnavailable: string;
  profileInvalid: string;
  csrf: string;
  origin: string;
  sessionExpired: string;
  rateLimited: string;
  network: string;
  notFound: string;
  server: string;
  forbidden: string;
  avatarInvalid: string;
  avatarTooLarge: string;
  generic: string;
  genericWithStatus: string;
};

const NETWORK_CODES = new Set([
  "network_unavailable",
  "community_unavailable",
  "http_0",
  "http_502",
  "http_503",
  "http_504",
]);

type NormalizedApiError = {
  status: number;
  code: string;
  validationMessages: string[];
};

function normalizeApiError(error: unknown): NormalizedApiError | null {
  if (error instanceof CommunityApiError) {
    return { status: error.status, code: error.code, validationMessages: error.validationMessages };
  }
  if (typeof error !== "object" || error === null) return null;
  const candidate = error as { name?: unknown; code?: unknown; status?: unknown; validationMessages?: unknown };
  if (candidate.name !== "CommunityApiError" || typeof candidate.code !== "string") return null;
  return {
    status: typeof candidate.status === "number" ? candidate.status : 0,
    code: candidate.code,
    validationMessages: Array.isArray(candidate.validationMessages)
      ? candidate.validationMessages.filter((item): item is string => typeof item === "string")
      : [],
  };
}

function isNetworkFailure(error: unknown): boolean {
  if (error instanceof TypeError) return true;
  if (!(error instanceof Error)) return false;
  return /failed to fetch|networkerror|load failed|network request failed/i.test(error.message);
}

export function explainAuthError(
  error: unknown,
  copy: ErrorCopy,
  surface: AuthErrorSurface = "account",
): AuthErrorExplanation {
  const apiError = normalizeApiError(error);
  if (apiError === null) {
    return { message: isNetworkFailure(error) ? copy.network : copy.generic };
  }

  if (apiError.status === 429 || apiError.code === "rate_limited") return { message: copy.rateLimited };

  if (apiError.code === "invalid_credentials" || (surface === "login" && apiError.status === 401)) {
    return { message: copy.invalidCredentials, field: "password" };
  }

  const byCode: Record<string, AuthErrorExplanation> = {
    registration_unavailable: { message: copy.registrationUnavailable },
    invalid_verification_code: { message: copy.invalidCode, field: "code" },
    password_policy_failed: { message: copy.passwordPolicy, field: "password" },
    profile_update_unavailable: { message: copy.profileUnavailable },
    profile_update_invalid: { message: copy.profileInvalid },
    csrf_failed: { message: copy.csrf },
    origin_not_allowed: { message: copy.origin },
    authentication_required: { message: copy.sessionExpired },
    avatar_invalid: { message: copy.avatarInvalid },
    avatar_too_large: { message: copy.avatarTooLarge },
  };
  if (byCode[apiError.code]) return byCode[apiError.code];

  if (
    NETWORK_CODES.has(apiError.code)
    || apiError.status === 0
    || apiError.status === 502
    || apiError.status === 503
    || apiError.status === 504
  ) {
    return { message: copy.network };
  }

  if (apiError.status === 404 || apiError.code === "http_404") return { message: copy.notFound };
  if (apiError.status === 500 || apiError.code === "http_500") return { message: copy.server };
  if (apiError.status === 403 || apiError.code === "http_403") return { message: copy.forbidden };
  if (apiError.validationMessages[0]) return { message: apiError.validationMessages[0] };
  if (apiError.status > 0) return { message: copy.genericWithStatus.replace("{status}", String(apiError.status)) };
  return { message: copy.generic };
}

export function authErrorMessage(
  error: unknown,
  copy: ErrorCopy,
  surface: AuthErrorSurface = "account",
): string {
  return explainAuthError(error, copy, surface).message;
}

export const errorCopy = {
  zh: {
    invalidCredentials: "邮箱或密码不正确。请检查后重试，或使用「忘记密码」重置。",
    registrationUnavailable: "该邮箱已注册，或自动生成的公开标识不可用。请尝试登录。",
    invalidCode: "验证码不正确或已经过期。",
    passwordPolicy: "密码需包含 8–64 个字符。",
    profileUnavailable: "这个公开标识已被使用，请换一个。",
    profileInvalid: "请检查姓名或公开标识的格式。",
    csrf: "安全凭据已过期，请刷新页面后重试。",
    origin: "登录被安全策略拦截。请重启 Community 服务，然后刷新本页再试。",
    sessionExpired: "登录状态已失效，请重新登录。",
    rateLimited: "操作过于频繁，请稍后再试。",
    network: "无法连接社区账号服务。请确认 Community 已启动后再登录。",
    notFound: "找不到社区登录接口。请确认 Community 已启动，且地址配置正确。",
    server: "社区服务暂时出错，请稍后重试。",
    forbidden: "请求被拒绝。请刷新页面后重试。",
    avatarInvalid: "头像必须是有效的图片文件。",
    avatarTooLarge: "头像文件不能超过 2 MiB。",
    generic: "请求未完成，请稍后重试。",
    genericWithStatus: "请求未完成（HTTP {status}），请稍后重试。",
  },
  en: {
    invalidCredentials: "The email or password is incorrect. Check both, or use Forgot password to reset.",
    registrationUnavailable: "This email is already registered or the generated public handle is unavailable. Try signing in.",
    invalidCode: "The verification code is incorrect or has expired.",
    passwordPolicy: "Use a password of 8–64 characters.",
    profileUnavailable: "That public handle is already in use. Try another one.",
    profileInvalid: "Check the format of your name or public handle.",
    csrf: "Your security session expired. Refresh the page and try again.",
    origin: "Sign-in was blocked by an origin check. Restart the Community service, then refresh this page.",
    sessionExpired: "Your session expired. Please sign in again.",
    rateLimited: "Too many attempts. Please wait and try again.",
    network: "The Community account service is unavailable. Start Community, then try signing in again.",
    notFound: "The Community sign-in endpoint was not found. Confirm Community is running and the proxy target is correct.",
    server: "The Community service had an internal error. Please try again shortly.",
    forbidden: "The request was rejected. Refresh the page and try again.",
    avatarInvalid: "Choose a valid image file.",
    avatarTooLarge: "Avatar files must be 2 MiB or smaller.",
    generic: "The request could not be completed. Please try again.",
    genericWithStatus: "The request could not be completed (HTTP {status}). Please try again.",
  },
} as const satisfies Record<"zh" | "en", ErrorCopy>;
