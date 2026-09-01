"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";
import type { Draft } from "@/lib/types";

type Stage = "idle" | "uploading" | "extracting" | "generating" | "complete";

const STAGE_COPY: Record<Stage, string> = {
  idle: "等待上传",
  uploading: "正在安全上传…",
  extracting: "正在抽取文字与识别结构…",
  generating: "AI 正在生成题目与测试…",
  complete: "草稿生成完成",
};

export function ContributionStudio() {
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [error, setError] = useState("");
  const [drafts, setDrafts] = useState<Draft[]>([]);

  async function loadDrafts() {
    try {
      const data = await api<{ items: Draft[] }>("/drafts");
      setDrafts(data.items);
    } catch {
      setDrafts([]);
    }
  }

  useEffect(() => { void loadDrafts(); }, []);

  async function pollJob(jobId: string) {
    for (let attempt = 0; attempt < 180; attempt += 1) {
      const job = await api<{ status: string; draft_id: string | null; error: string | null }>(`/jobs/${jobId}`);
      if (job.status === "completed" && job.draft_id) {
        setStage("complete");
        window.location.href = `/drafts/${job.draft_id}`;
        return;
      }
      if (job.status === "failed") throw new Error(job.error || "题目生成失败");
      setStage(attempt < 3 ? "extracting" : "generating");
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
    throw new Error("生成时间过长，请稍后在草稿列表查看结果");
  }

  async function begin() {
    if (!file) return;
    setError(""); setStage("uploading");
    const form = new FormData(); form.append("file", file);
    try {
      const upload = await api<{ id: string }>("/uploads", { method: "POST", body: form });
      setStage("extracting");
      const job = await api<{ job_id: string }>(`/uploads/${upload.id}/generate`, { method: "POST" });
      await pollJob(job.job_id);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) setError("请先登录并验证邮箱，再上传资料。 ");
      else setError(caught instanceof Error ? caught.message : "上传失败");
      setStage("idle");
    }
  }

  const busy = stage !== "idle" && stage !== "complete";

  return (
    <div className="contribution-layout">
      <section>
        <span className="eyebrow">AI problem studio</span>
        <h1 className="page-title">把资料变成一道好题</h1>
        <p className="lead muted">上传算法讲义、认证题或个人笔记。系统会生成结构化草稿，但只有你确认并通过自动质量门禁后才会公开。</p>

        <div className={`upload-zone card ${file ? "has-file" : ""}`}>
          <input
            type="file"
            id="source-file"
            accept=".pdf,.docx,.md,.txt,.png,.jpg,.jpeg"
            disabled={busy}
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <label htmlFor="source-file">
            <span className="upload-icon">↥</span>
            <strong>{file ? file.name : "选择或拖入算法资料"}</strong>
            <small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : "PDF · DOCX · Markdown · TXT · PNG/JPG，最大 20 MB"}</small>
          </label>
        </div>

        <div className="generation-steps">
          {["安全上传", "文字抽取", "题目生成", "人工校对"].map((value, index) => {
            const activeIndex = { idle: -1, uploading: 0, extracting: 1, generating: 2, complete: 3 }[stage];
            return <div className={index <= activeIndex ? "active" : ""} key={value}><span>{index < activeIndex ? "✓" : index + 1}</span><small>{value}</small></div>;
          })}
        </div>
        {busy && <div className="notice"><span className="inline-loader" />{STAGE_COPY[stage]}</div>}
        {error && <div className="notice notice-error">{error}{error.includes("登录") && <Link href="/login">去登录 →</Link>}</div>}
        <div className="button-row upload-actions">
          <button className="button button-accent" disabled={!file || busy} onClick={begin}>{busy ? "生成中…" : "上传并生成题目"}</button>
          <span className="muted">原始资料默认私有，不提供公开下载。</span>
        </div>
        <div className="notice notice-warn privacy-note">资料文本会发送给部署者配置的 AI 服务商。请勿上传公司机密、个人敏感信息或无权使用的内容。</div>
      </section>

      <aside className="studio-aside">
        <div className="card panel studio-guide">
          <span className="eyebrow">生成后你可以</span>
          <ol>
            <li><span>01</span><div><strong>校对题意</strong><small>修改标题、描述、接口和难度</small></div></li>
            <li><span>02</span><div><strong>检查测试</strong><small>查看参考解、公开与隐藏用例</small></div></li>
            <li><span>03</span><div><strong>运行质量门禁</strong><small>确保正确解通过、典型错解失败</small></div></li>
            <li><span>04</span><div><strong>自行发布</strong><small>确认授权后进入公共题库</small></div></li>
          </ol>
        </div>
        <div className="draft-stack">
          <div className="aside-heading"><h3>我的最近草稿</h3><button onClick={loadDrafts}>刷新</button></div>
          {drafts.length === 0 && <p className="muted">登录后可在这里继续未完成的投稿。</p>}
          {drafts.slice(0, 5).map((draft) => (
            <Link href={`/drafts/${draft.id}`} className="draft-link" key={draft.id}>
              <span className={`draft-status ${draft.status}`} />
              <div><strong>{draft.payload.title}</strong><small>{draft.status} · {new Date(draft.updated_at).toLocaleDateString("zh-CN")}</small></div>
              <b>→</b>
            </Link>
          ))}
        </div>
      </aside>
    </div>
  );
}

