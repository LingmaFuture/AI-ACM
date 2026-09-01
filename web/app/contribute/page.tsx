import type { Metadata } from "next";

import { ContributionStudio } from "@/components/ContributionStudio";

export const metadata: Metadata = { title: "AI 投稿工作台" };

export default function ContributePage() {
  return <div className="page-shell"><ContributionStudio /></div>;
}

