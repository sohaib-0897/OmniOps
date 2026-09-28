"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, ArrowUpRight, Eye, EyeOff, FileSpreadsheet, FileText, ShieldCheck } from "lucide-react";
import { BrandLockup, ThemeToggle } from "@/components/casefile/Brand";
import { apiClient } from "@/lib/api-client";
import type { AuthSession, User } from "@/types/api";
import "./auth.css";

type Mode = "login" | "register" | "forgot" | "reset";

function PasswordField({ id, value, onChange, label, autoComplete }: { id: string; value: string; onChange: (value: string) => void; label: string; autoComplete: string }) {
  const [shown, setShown] = useState(false);
  return <div className="rev-auth-field"><label htmlFor={id}>{label}</label><div className="rev-password-wrap"><input id={id} type={shown ? "text" : "password"} value={value} onChange={event => onChange(event.target.value)} autoComplete={autoComplete} required minLength={autoComplete === "current-password" ? 1 : 12} maxLength={72}/><button type="button" aria-label={shown ? "Hide password" : "Show password"} aria-pressed={shown} onClick={() => setShown(v => !v)}>{shown ? <EyeOff size={18}/> : <Eye size={18}/>}</button></div></div>;
}

function AuthVisual() {
  const [selected, setSelected] = useState(0);
  return <div className="rev-auth-visual"><div className="rev-auth-visual-top"><span>FROM SOURCE TO ANSWER</span><span>◌</span></div><div className="rev-auth-visual-center"><div className="rev-auth-source-pair"><button type="button" onClick={() => setSelected(0)} aria-pressed={selected === 0}><FileText size={22}/><span>Source</span><strong>Operating review</strong><small>Page 12</small></button><button type="button" onClick={() => setSelected(1)} aria-pressed={selected === 1}><FileSpreadsheet size={22}/><span>Table</span><strong>Quarterly figures</strong><small>Row 24</small></button></div><div className="rev-auth-thread" aria-hidden="true"><span/><span/><span/></div><div className="rev-auth-answer"><span><ShieldCheck size={18}/> EVIDENCE TRAIL</span><strong>{selected === 0 ? "A finding with a passage behind it." : "A calculation with its inputs in view."}</strong><small>{selected === 0 ? "Operating review · p. 12" : "Quarterly figures · row 24"}</small></div></div><p>Choose a source to trace the line.</p></div>;
}

export function AuthExperience({ mode, token, expired = false, onAuthenticated }: { mode: Mode; token?: string | null; expired?: boolean; onAuthenticated?: (user: User) => void }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [done, setDone] = useState(false);
  const [query, setQuery] = useState<URLSearchParams | null>(null);
  useEffect(() => setQuery(new URLSearchParams(window.location.search)), []);
  const next = query?.get("next");
  const safeNext = next?.startsWith("/workspaces/") && !next.startsWith("//") ? next : null;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if ((mode === "register" || mode === "reset") && password !== confirm) { setError("Passwords do not match."); return; }
    if (mode === "reset" && !token) { setError("This reset link is missing its token. Request a new link."); return; }
    setBusy(true); setError("");
    try {
      if (mode === "forgot") {
        await apiClient.post("/auth/password-reset/request", { email });
        setSent(true);
      } else if (mode === "reset") {
        await apiClient.post("/auth/password-reset/confirm", { token, password });
        apiClient.clearToken(); setDone(true);
      } else {
        const result = await apiClient.post<AuthSession>(mode === "login" ? "/auth/login" : "/auth/register", mode === "login" ? { email, password } : { email, password, full_name: name });
        apiClient.setToken(result.token.access_token);
        setPassword(""); setConfirm("");
        if (onAuthenticated) onAuthenticated(result.user);
        else router.replace(safeNext || "/app");
      }
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Something went wrong. Try again."); }
    finally { setBusy(false); }
  };
  const title = { login: "Welcome back.", register: "Make room for a better question.", forgot: "Reset your password.", reset: "Choose a new password." }[mode];
  const intro = { login: "Your sources and investigations are ready when you are.", register: "Create an account, then bring the sources you want to investigate.", forgot: "Enter your email and we'll send a reset link if there's an account for it.", reset: "Use a password of at least 12 characters. All current sessions will be signed out." }[mode];
  return <div className="rev-auth"><div className="rev-auth-form-side"><header><Link href="/" aria-label="OmniOps home"><BrandLockup size={28}/></Link><ThemeToggle/></header><main id="main-content"><span className="rev-auth-small">{mode === "register" ? "START HERE" : mode === "login" ? "GOOD TO SEE YOU" : "ACCOUNT ACCESS"}</span><h1>{title}</h1><p className="rev-auth-intro">{intro}</p>
      {expired && <p className="rev-auth-alert" role="status">Your session ended. Sign in to continue.</p>}
      {mode === "login" && query?.get("reset") === "success" && <p className="rev-auth-alert" role="status">Password updated. Sign in with your new password.</p>}
      {sent || done ? <div className="rev-auth-result" role="status"><ShieldCheck size={26}/><h2>{sent ? "Check your email" : "Password updated"}</h2><p>{sent ? "If that account exists, a password reset link is on its way. Check your inbox and spam folder." : "All previous sessions were signed out. You can now sign in with your new password."}</p><Link href={done ? "/login?reset=success" : "/login"}>Back to sign in <ArrowRight size={17}/></Link></div> : <form onSubmit={submit} aria-busy={busy}>
        {mode === "register" && <div className="rev-auth-field"><label htmlFor="auth-name">Full name</label><input id="auth-name" autoComplete="name" required minLength={2} value={name} onChange={event => setName(event.target.value)}/></div>}
        {mode !== "reset" && <div className="rev-auth-field"><label htmlFor="auth-email">Email address</label><input id="auth-email" type="email" autoComplete="email" required value={email} onChange={event => setEmail(event.target.value)}/></div>}
        {(mode === "login" || mode === "register" || mode === "reset") && <PasswordField id="auth-password" label={mode === "reset" ? "New password" : "Password"} value={password} onChange={setPassword} autoComplete={mode === "login" ? "current-password" : "new-password"}/>}
        {(mode === "register" || mode === "reset") && <PasswordField id="auth-confirm" label="Confirm password" value={confirm} onChange={setConfirm} autoComplete="new-password"/>}
        {mode === "login" && <Link href="/forgot-password" className="rev-forgot">Forgot password?</Link>}
        {error && <p className="rev-auth-error" role="alert">{error}</p>}
        <button type="submit" className="rev-auth-submit" disabled={busy || (mode === "reset" && !token)}>{busy ? "Please wait…" : { login: "Sign in", register: "Create account", forgot: "Send reset link", reset: "Reset password" }[mode]} <ArrowRight size={18}/></button>
      </form>}
      <div className="rev-auth-alternate">{mode === "login" ? <>New to OmniOps? <Link href="/register">Create an account <ArrowUpRight size={15}/></Link></> : mode === "register" ? <>Already have an account? <Link href="/login">Sign in <ArrowUpRight size={15}/></Link></> : <Link href="/login">Back to sign in <ArrowUpRight size={15}/></Link>}</div>
    </main><footer><span>Follow the evidence, all the way back.</span><Link href="/">Explore OmniOps <ArrowUpRight size={14}/></Link></footer></div><AuthVisual/></div>;
}
