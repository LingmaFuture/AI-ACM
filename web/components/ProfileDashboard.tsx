"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { User } from "@/lib/types";

interface ProfileData {
  user: User;
  stats: { solved: number; submissions: number; streak: number; tags: Record<string, number> };
}

export function ProfileDashboard() {
  const [data, setData] = useState<ProfileData | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<ProfileData>("/profile")
      .then(setData)
      .catch((caught) => setError(caught instanceof ApiError && caught.status === 401 ? "请先登录查看训练档案" : caught.message));
  }, []);
  if (!data && !error) return <div className="loading"><div className="loader" /></div>;
  if (!data) return <div className="narrow-shell"><div className="notice notice-error">{error}</div><Link className="button" href="/login">去登录</Link></div>;
  const tags = Object.entries(data.stats.tags).sort((a, b) => b[1] - a[1]);
  const maxTag = Math.max(1, ...tags.map(([, value]) => value));
  return (
    <div className="page-shell profile-page">
      <section className="profile-identity">
        <div className="profile-avatar">{data.user.display_name.slice(0, 1)}</div>
        <div><span className="eyebrow">Training profile</span><h1>{data.user.display_name}</h1><p>{data.user.email} · {data.user.email_verified ? "邮箱已验证" : "待验证"}</p></div>
        <Link className="button button-secondary" href="/problems">继续刷题 →</Link>
      </section>
      <div className="stats-grid">
        <article className="card panel"><span>已通过题目</span><strong>{data.stats.solved}</strong><small>不同题目</small></article>
        <article className="card panel"><span>累计提交</span><strong>{data.stats.submissions}</strong><small>运行与正式提交</small></article>
        <article className="card panel"><span>连续练习</span><strong>{data.stats.streak}</strong><small>天</small></article>
      </div>
      <section className="mastery card panel">
        <div><span className="eyebrow">Tag mastery</span><h2>算法掌握度</h2><p className="muted">按已通过题目所属标签统计。</p></div>
        <div className="mastery-bars">
          {tags.length === 0 && <div className="empty-state">通过第一道题后，这里会形成你的算法能力图谱。</div>}
          {tags.map(([tag, value]) => <div key={tag}><span>{tag}</span><div><i style={{ width: `${(value / maxTag) * 100}%` }} /></div><b className="mono">{value}</b></div>)}
        </div>
      </section>
    </div>
  );
}

