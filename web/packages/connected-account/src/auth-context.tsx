import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren } from "react";
import type {
  CommunityAccount,
  CommunityDeviceSession,
  CommunityPasswordResetRequest,
  CommunityProfileUpdate,
  CommunityRegistrationRequest,
} from "@veyra/api-contracts";
import { CommunityApiError, createCommunityApi, type CommunityApi } from "./api";

export type AuthStatus = "booting" | "anonymous" | "authenticated";
export type VerificationPurpose = "registration" | "password_reset";

type AuthContextValue = {
  status: AuthStatus;
  account: CommunityAccount | null;
  bootstrapError: CommunityApiError | null;
  login: (email: string, password: string) => Promise<CommunityAccount>;
  register: (payload: Omit<CommunityRegistrationRequest, "device_name">) => Promise<CommunityAccount>;
  requestCode: (email: string, purpose: VerificationPurpose) => Promise<void>;
  resetPassword: (payload: Omit<CommunityPasswordResetRequest, "device_name">) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (payload: CommunityProfileUpdate) => Promise<CommunityAccount>;
  listSessions: () => Promise<CommunityDeviceSession[]>;
  revokeSession: (sessionId: string) => Promise<void>;
  uploadAvatar: (file: File) => Promise<string | null>;
  replaceAvatar: (file: File) => Promise<string | null>;
  deleteAvatar: () => Promise<string | null>;
};

const defaultApi = createCommunityApi({ baseUrl: "/api/v1" });
const AuthContext = createContext<AuthContextValue | null>(null);

async function bootstrapAccount(api: CommunityApi): Promise<CommunityAccount | null> {
  try {
    return await api.me();
  } catch (error) {
    if (!(error instanceof CommunityApiError) || error.status !== 401) throw error;
    if (!api.hasRefreshEvidence()) return null;
    try {
      return await api.refresh();
    } catch (refreshError) {
      if (refreshError instanceof CommunityApiError && [401, 403].includes(refreshError.status)) return null;
      throw refreshError;
    }
  }
}

export function AuthProvider({ children, api = defaultApi }: PropsWithChildren<{ api?: CommunityApi }>) {
  const [status, setStatus] = useState<AuthStatus>("booting");
  const [account, setAccount] = useState<CommunityAccount | null>(null);
  const [bootstrapError, setBootstrapError] = useState<CommunityApiError | null>(null);
  const bootstrapRef = useRef<{ api: CommunityApi; promise: Promise<CommunityAccount | null> } | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!bootstrapRef.current || bootstrapRef.current.api !== api) bootstrapRef.current = { api, promise: bootstrapAccount(api) };
    void bootstrapRef.current.promise.then((nextAccount) => {
      if (cancelled) return;
      setAccount(nextAccount);
      setStatus(nextAccount ? "authenticated" : "anonymous");
      setBootstrapError(null);
    }).catch((error: unknown) => {
      if (cancelled) return;
      setAccount(null);
      setStatus("anonymous");
      setBootstrapError(error instanceof CommunityApiError ? error : new CommunityApiError("request_failed"));
    });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const login = useCallback(async (email: string, password: string) => {
    const nextAccount = await api.login({ email, password });
    setAccount(nextAccount);
    setStatus("authenticated");
    setBootstrapError(null);
    return nextAccount;
  }, [api]);

  const register = useCallback(async (payload: Omit<CommunityRegistrationRequest, "device_name">) => {
    const nextAccount = await api.register(payload);
    setAccount(nextAccount);
    setStatus("authenticated");
    setBootstrapError(null);
    return nextAccount;
  }, [api]);

  const requestCode = useCallback(async (email: string, purpose: VerificationPurpose) => {
    await api.requestVerificationCode(email, purpose);
  }, [api]);

  const resetPassword = useCallback(async (payload: Omit<CommunityPasswordResetRequest, "device_name">) => {
    await api.resetPassword(payload);
    setAccount(null);
    setStatus("anonymous");
    setBootstrapError(null);
  }, [api]);

  const logout = useCallback(async () => {
    await api.logout();
    setAccount(null);
    setStatus("anonymous");
  }, [api]);

  const updateProfile = useCallback(async (payload: CommunityProfileUpdate) => {
    const nextAccount = await api.updateProfile(payload);
    setAccount(nextAccount);
    return nextAccount;
  }, [api]);

  const listSessions = useCallback(() => api.listSessions(), [api]);

  const revokeSession = useCallback(async (sessionId: string) => {
    await api.revokeSession(sessionId);
    try {
      const currentAccount = await api.me();
      setAccount((previous) => previous
        && previous.id === currentAccount.id
        && previous.email === currentAccount.email
        && previous.handle === currentAccount.handle
        && previous.display_name === currentAccount.display_name
        && previous.avatar_url === currentAccount.avatar_url
        ? previous
        : currentAccount);
    } catch (error) {
      if (!(error instanceof CommunityApiError) || error.status !== 401) throw error;
      setAccount(null);
      setStatus("anonymous");
    }
  }, [api]);

  const uploadAvatar = useCallback(async (file: File) => {
    const nextAccount = await api.uploadAvatar(file);
    setAccount(nextAccount);
    return nextAccount.avatar_url;
  }, [api]);

  const replaceAvatar = useCallback(async (file: File) => {
    const nextAccount = await api.replaceAvatar(file);
    setAccount(nextAccount);
    return nextAccount.avatar_url;
  }, [api]);

  const deleteAvatar = useCallback(async () => {
    await api.deleteAvatar();
    setAccount((previous) => previous ? { ...previous, avatar_url: null } : previous);
    return null;
  }, [api]);

  const value = useMemo<AuthContextValue>(() => ({
    status,
    account,
    bootstrapError,
    login,
    register,
    requestCode,
    resetPassword,
    logout,
    updateProfile,
    listSessions,
    revokeSession,
    uploadAvatar,
    replaceAvatar,
    deleteAvatar,
  }), [account, bootstrapError, deleteAvatar, listSessions, login, logout, register, requestCode, replaceAvatar, resetPassword, revokeSession, status, updateProfile, uploadAvatar]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
