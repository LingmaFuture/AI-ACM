"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { User } from "@/lib/types";

export function SessionNav() {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    api<{ user: User | null }>("/auth/me")
      .then((data) => setUser(data.user))
      .catch(() => setUser(null));
  }, []);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    window.location.href = "/";
  }

  if (user === undefined) return <span className="nav-placeholder" />;
  if (!user) {
    return (
      <div className="nav-actions">
        <Link href="/login" className="text-link">
          登录
        </Link>
        <Link href="/register" className="button button-small">
          加入社区
        </Link>
      </div>
    );
  }
  return (
    <div className="nav-actions">
      <Link href="/profile" className="user-chip">
        <span>{user.display_name.slice(0, 1)}</span>
        {user.display_name}
      </Link>
      <button className="text-button" onClick={logout}>
        退出
      </button>
    </div>
  );
}

