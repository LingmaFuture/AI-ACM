"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

interface Leader {
  rank: number;
  user_id: string;
  display_name: string;
  solved: number;
}

export function Leaderboard() {
  const [items, setItems] = useState<Leader[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { api<{ items: Leader[] }>("/leaderboard").then((data) => setItems(data.items)).catch((caught) => setError(caught.message)); }, []);
  if (!items && !error) return <div className="loading"><div className="loader" /></div>;
  return (
    <div className="leader-table card">
      <div className="leader-row leader-head"><span>排名</span><span>学习者</span><span>通过题目</span></div>
      {error && <div className="empty-state notice-error">{error}</div>}
      {items?.length === 0 && <div className="empty-state">排行榜还在等待第一位解题者。</div>}
      {items?.map((item) => (
        <div className={`leader-row rank-${item.rank}`} key={item.user_id}>
          <span className="rank-mark">{item.rank <= 3 ? ["Ⅰ", "Ⅱ", "Ⅲ"][item.rank - 1] : item.rank}</span>
          <span className="leader-name"><i>{item.display_name.slice(0, 1)}</i><strong>{item.display_name}</strong></span>
          <span><b className="mono">{item.solved}</b> 道</span>
        </div>
      ))}
    </div>
  );
}

