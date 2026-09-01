import type { Metadata } from "next";

import { ProblemList } from "@/components/ProblemList";

export const metadata: Metadata = { title: "公开题库" };

export default function ProblemsPage() {
  return (
    <div className="page-shell">
      <div className="page-title-row">
        <div>
          <span className="eyebrow">Problem set</span>
          <h1 className="page-title">公开题库</h1>
          <p className="muted">从算法原理到边界条件，用真正的代码检验理解。</p>
        </div>
        <div className="title-note mono">RUN SAMPLES → SUBMIT HIDDEN TESTS</div>
      </div>
      <ProblemList />
    </div>
  );
}

