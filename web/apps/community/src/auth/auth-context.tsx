import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PropsWithChildren } from "react";
import type {
  CommunityAccount,
  CommunityDeviceSession,
  CommunityPasswordResetRequest,
  CommunityProfileUpdate,
  CommunityRegistrationRequest,
} from "@veyra/api-contracts";
import { CommunityApiError, communityApi } from "./community-api";

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
};

const AuthContext = createContext<AuthContextValue | null>(null);

async function bootstrapAccount(): Promise<CommunityAccount | null> {
  try {
    return await communityApi.me();
  } catch (error) {
    if (!(error instanceof CommunityApiError) || error.status !== 401) throw error;
    if (!communityApi.hasRefreshEvidence()) return null;
    try {
      return await communityApi.refresh();
    } catch (refreshError) {
      if (refreshError instanceof CommunityApiError && [401, 403].includes(refreshError.status)) return null;
      throw refreshError;
    }
  }
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [status, setStatus] = useState<AuthStatus>("booting");
  const [account, setAccount] = useState<CommunityAccount | null>(null);
  const [bootstrapError, setBootstrapError] = useState<CommunityApiError | null>(null);
  const bootstrapRef = useRef<Promise<CommunityAccount | null> | null>(null);

  useEffect(() => {
    let cancelled = false;
    bootstrapRef.current ??= bootstrapAccount();
    void bootstrapRef.current.then((nextAccount) => {
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
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const nextAccount = await communityApi.login({ email, password });
    setAccount(nextAccount);
    setStatus("authenticated");
    setBootstrapError(null);
    return nextAccount;
  }, []);

  const register = useCallback(async (payload: Omit<CommunityRegistrationRequest, "device_name">) => {
    const nextAccount = await communityApi.register(payload);
    setAccount(nextAccount);
    setStatus("authenticated");
    setBootstrapError(null);
    return nextAccount;
  }, []);

  const requestCode = useCallback(async (email: string, purpose: VerificationPurpose) => {
    await communityApi.requestVerificationCode(email, purpose);
  }, []);

  const resetPassword = useCallback(async (payload: Omit<CommunityPasswordResetRequest, "device_name">) => {
    await communityApi.resetPassword(payload);
  }, []);

  const logout = useCallback(async () => {
    await communityApi.logout();
    setAccount(null);
    setStatus("anonymous");
  }, []);

  const updateProfile = useCallback(async (payload: CommunityProfileUpdate) => {
    const nextAccount = await communityApi.updateProfile(payload);
    setAccount(nextAccount);
    return nextAccount;
  }, []);

  const listSessions = useCallback(() => communityApi.listSessions(), []);

  const revokeSession = useCallback(async (sessionId: string) => {
    await communityApi.revokeSession(sessionId);
    try {
      const currentAccount = await communityApi.me();
      setAccount((previous) => previous
        && previous.id === currentAccount.id
        && previous.email === currentAccount.email
        && previous.handle === currentAccount.handle
        && previous.display_name === currentAccount.display_name
        ? previous
        : currentAccount);
    } catch (error) {
      if (!(error instanceof CommunityApiError) || error.status !== 401) throw error;
      setAccount(null);
      setStatus("anonymous");
    }
  }, []);

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
  }), [account, bootstrapError, listSessions, login, logout, register, requestCode, resetPassword, revokeSession, status, updateProfile]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider");
  return context;
}
