import { LogIn, UserRound } from "lucide-react";
import { createCommunityApi, useAuth } from "@veyra/connected-account";
import { useLocale } from "@veyra/ui";
import "./site-auth.css";

export const publicCommunityApi = createCommunityApi({ baseUrl: "/api/v1" });

export function SiteAccountControl() {
  const { account, status } = useAuth();
  const { locale } = useLocale();
  const zh = locale === "zh";
  const name = account?.display_name || account?.handle;
  const label = status === "booting" ? (zh ? "正在检查登录状态" : "Checking sign-in") : account ? (zh ? `我的 · ${name}，已登录` : `Mine · ${name}, signed in`) : (zh ? "登录社区" : "Sign in");
  return <a className={`showcase-account${account ? " is-connected" : ""}`} href={account ? "#/community/mine" : "#/login"} aria-label={label} title={label} aria-busy={status === "booting"}>
    {account?.avatar_url ? <img src={account.avatar_url} alt="" /> : account ? <UserRound size={18} aria-hidden="true" /> : <LogIn size={18} aria-hidden="true" />}
    <span>{account ? name : zh ? "登录" : "Sign in"}</span>{account ? <i aria-hidden="true" /> : null}
  </a>;
}
