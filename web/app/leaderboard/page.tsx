import type { Metadata } from "next";

import { Leaderboard } from "@/components/Leaderboard";

export const metadata: Metadata = { title: "排行榜" };

export default function LeaderboardPage() {
  return (
    <div className="narrow-shell leaderboard-page">
      <div className="leader-title"><span className="eyebrow">Community ranking</span><h1 className="page-title">解题排行榜</h1><p className="muted">按通过的不同题目数量排名；同分时，更早开始有效练习的学习者在前。</p></div>
      <Leaderboard />
    </div>
  );
}

