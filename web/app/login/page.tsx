"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";

import { AuthCard } from "@/components/AuthCard";
import { api } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const search = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setLoading(true); setError("");
    try {
      await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      router.push(search.get("next") || "/problems");
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "登录失败");
    } finally { setLoading(false); }
  }

  return (
    <AuthCard eyebrow="Welcome back" title="继续你的算法进度">
      <form className="form-stack" onSubmit={submit}>
        <div className="field"><label htmlFor="email">邮箱</label><input id="email" className="input" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" /></div>
        <div className="field"><label htmlFor="password">密码</label><input id="password" className="input" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="至少 8 位" /></div>
        {error && <div className="notice notice-error">{error}</div>}
        <button className="button" disabled={loading}>{loading ? "登录中…" : "登录"}</button>
      </form>
      <p className="auth-switch">还没有账号？<Link href="/register">创建账号 →</Link></p>
    </AuthCard>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}

