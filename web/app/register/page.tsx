"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";

import { AuthCard } from "@/components/AuthCard";
import { api } from "@/lib/api";

export default function RegisterPage() {
  const [form, setForm] = useState({ display_name: "", email: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [verificationToken, setVerificationToken] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      const data = await api<{ verification_token?: string }>("/auth/register", { method: "POST", body: JSON.stringify(form) });
      setVerificationToken(data.verification_token || "sent");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "注册失败"); }
    finally { setLoading(false); }
  }

  return (
    <AuthCard eyebrow="Join the commons" title="创建你的训练档案">
      {verificationToken ? (
        <div className="form-stack">
          <div className="success-symbol">✓</div>
          <div><h3>验证邮件已经发出</h3><p className="muted">打开邮件中的链接后即可登录、提交代码和上传资料。</p></div>
          {verificationToken !== "sent" && <Link className="button" href={`/verify?token=${verificationToken}`}>开发环境：立即验证</Link>}
          <Link className="text-link" href="/login">返回登录</Link>
        </div>
      ) : (
        <form className="form-stack" onSubmit={submit}>
          <div className="field"><label>显示名称</label><input className="input" required minLength={2} value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} placeholder="你的社区昵称" /></div>
          <div className="field"><label>邮箱</label><input className="input" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@example.com" /></div>
          <div className="field"><label>密码</label><input className="input" type="password" required minLength={8} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="至少 8 位" /></div>
          {error && <div className="notice notice-error">{error}</div>}
          <button className="button" disabled={loading}>{loading ? "创建中…" : "创建账号"}</button>
          <small className="muted">注册即表示你同意只上传有权使用和发布的内容。</small>
        </form>
      )}
      {!verificationToken && <p className="auth-switch">已有账号？<Link href="/login">直接登录 →</Link></p>}
    </AuthCard>
  );
}

