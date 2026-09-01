"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { api, difficultyLabel } from "@/lib/api";
import type { ProblemSummary } from "@/lib/types";

const TAGS = ["全部", "KNN", "K-Means", "分类", "聚类", "回归", "降维"];

export function ProblemList({ compact = false }: { compact?: boolean }) {
  const [items, setItems] = useState<ProblemSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [tag, setTag] = useState("全部");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (difficulty) params.set("difficulty", difficulty);
    if (tag !== "全部") params.set("tag", tag);
    if (compact) params.set("limit", "6");
    try {
      const data = await api<{ items: ProblemSummary[] }>(`/problems?${params}`);
      setItems(data.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "题库加载失败");
    } finally {
      setLoading(false);
    }
  }, [compact, difficulty, query, tag]);

  useEffect(() => {
    const timer = window.setTimeout(load, 180);
    return () => window.clearTimeout(timer);
  }, [load]);

  return (
    <section className="problem-browser">
      {!compact && (
        <div className="problem-filters">
          <div className="search-box">
            <span>⌕</span>
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索算法或题目…"
              aria-label="搜索题目"
            />
          </div>
          <select
            className="select filter-select"
            value={difficulty}
            onChange={(event) => setDifficulty(event.target.value)}
            aria-label="筛选难度"
          >
            <option value="">所有难度</option>
            <option value="easy">入门</option>
            <option value="medium">进阶</option>
            <option value="hard">挑战</option>
          </select>
        </div>
      )}

      {!compact && (
        <div className="tag-filter" aria-label="算法标签">
          {TAGS.map((value) => (
            <button key={value} className={tag === value ? "active" : ""} onClick={() => setTag(value)}>
              {value}
            </button>
          ))}
        </div>
      )}

      <div className="problem-table card">
        <div className="problem-row problem-head">
          <span>状态</span>
          <span>题目</span>
          <span>难度</span>
          <span>标签</span>
        </div>
        {loading && (
          <div className="loading list-loading">
            <div className="loader" />
          </div>
        )}
        {!loading && error && <div className="empty-state notice-error">{error}</div>}
        {!loading && !error && items.length === 0 && <div className="empty-state">没有找到匹配的题目。</div>}
        {!loading &&
          !error &&
          items.map((problem, index) => (
            <Link className="problem-row" href={`/problems/${problem.slug}`} key={problem.id}>
              <span className={`status-dot ${problem.solved ? "solved" : ""}`} aria-label={problem.solved ? "已完成" : "未完成"} />
              <span className="problem-title">
                <b className="mono">{String(index + 1).padStart(2, "0")}</b>
                <span>
                  <strong>{problem.title}</strong>
                  <small>by {problem.author}</small>
                </span>
              </span>
              <span className={`difficulty ${problem.difficulty}`}>{difficultyLabel(problem.difficulty)}</span>
              <span className="row-tags">
                {problem.tags.slice(0, 3).map((value) => (
                  <span className="tag" key={value}>
                    {value}
                  </span>
                ))}
              </span>
            </Link>
          ))}
      </div>
    </section>
  );
}

