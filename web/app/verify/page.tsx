"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { api } from "@/lib/api";

function VerifyContent() {
  const params = useSearchParams();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("正在验证邮箱…");
  useEffect(() => {
    const token = params.get("token");
    if (!token) { setStatus("error"); setMessage("验证链接缺少 token"); return; }
    api<{ message: string }>(`/auth/verify?token=${encodeURIComponent(token)}`)
      .then((data) => { setStatus("success"); setMessage(data.message); })
      .catch((error) => { setStatus("error"); setMessage(error.message); });
  }, [params]);
  return (
    <div className="narrow-shell verify-card card panel">
      <div className={`success-symbol ${status === "error" ? "error" : ""}`}>{status === "loading" ? "…" : status === "success" ? "✓" : "×"}</div>
      <h1 className="page-title">{message}</h1>
      <p className="muted">{status === "success" ? "你的账号已经可以提交代码和贡献题目。" : "如果链接已过期，请重新注册或联系管理员。"}</p>
      <Link className="button" href={status === "success" ? "/login" : "/"}>{status === "success" ? "去登录" : "返回首页"}</Link>
    </div>
  );
}

export default function VerifyPage() { return <Suspense><VerifyContent /></Suspense>; }

