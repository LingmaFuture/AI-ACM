"use client";

import Editor from "@monaco-editor/react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { formatJson } from "@/lib/formatJson";
import type { Draft, ProblemDraftPayload } from "@/lib/types";

export function DraftEditor() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [jsonText, setJsonText] = useState("");
  const [rights, setRights] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function load() {
    try {
      const data = await api<Draft>(`/drafts/${params.id}`);
      setDraft(data); setJsonText(formatJson(data.payload)); setRights(data.rights_attested);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "草稿加载失败"); }
  }
  useEffect(() => { void load(); }, [params.id]);

  function parsedPayload(): ProblemDraftPayload {
    try { return JSON.parse(jsonText) as ProblemDraftPayload; }
    catch { throw new Error("JSON 格式无效，请检查逗号、引号和括号"); }
  }

  async function save() {
    setError(""); setBusy("saving"); setSaved(false);
    try {
      const updated = await api<Draft>(`/drafts/${params.id}`, { method: "PATCH", body: JSON.stringify({ payload: parsedPayload(), rights_attested: rights }) });
      setDraft(updated); setSaved(true);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "保存失败"); }
    finally { setBusy(""); }
  }

  async function pollValidation(jobId: string) {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      const job = await api<{ status: string; error: string | null }>(`/jobs/${jobId}`);
      if (job.status === "completed") { await load(); return; }
      if (job.status === "failed") throw new Error(job.error || "校验失败");
      await new Promise((resolve) => window.setTimeout(resolve, 800));
    }
    throw new Error("校验超时，请稍后刷新页面");
  }

  async function validate() {
    setError(""); setBusy("validating");
    try {
      await api(`/drafts/${params.id}`, { method: "PATCH", body: JSON.stringify({ payload: parsedPayload(), rights_attested: rights }) });
      const job = await api<{ job_id: string }>(`/drafts/${params.id}/validate`, { method: "POST" });
      await pollValidation(job.job_id);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "校验失败"); }
    finally { setBusy(""); }
  }

  async function publish() {
    setError(""); setBusy("publishing");
    try {
      const result = await api<{ slug: string }>(`/drafts/${params.id}/publish`, { method: "POST" });
      router.push(`/problems/${result.slug}`);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "发布失败"); setBusy(""); }
  }

  if (!draft && !error) return <div className="loading"><div className="loader" /></div>;
  if (!draft) return <div className="narrow-shell"><div className="notice notice-error">{error}</div></div>;
  const report = draft.validation_report;

  return (
    <div className="draft-editor-shell">
      <div className="draft-editor-heading">
        <div><Link href="/contribute" className="text-link">← 返回投稿台</Link><h1>{draft.payload.title}</h1><p className="muted">高级草稿编辑器 · 私有字段仅你和管理员可见</p></div>
        <span className={`draft-badge ${draft.status}`}>{draft.status}</span>
      </div>
      <div className="draft-grid">
        <section className="json-editor card">
          <div className="json-topbar"><strong>ProblemDraftV1.json</strong><span>题干 + 判题包</span></div>
          <Editor
            height="680px"
            language="json"
            theme="vs-dark"
            value={jsonText}
            onChange={(value) => { setJsonText(value ?? ""); setSaved(false); }}
            options={{ minimap: { enabled: false }, fontSize: 12, lineHeight: 20, automaticLayout: true, tabSize: 2, wordWrap: "on" }}
          />
        </section>
        <aside className="validation-panel">
          <div className="card panel">
            <span className="eyebrow">Quality gate</span><h3>自动质量门禁</h3>
            {!report && <p className="muted">保存后运行校验。系统会真正执行参考答案、空实现和每份典型错解。</p>}
            {report?.checks.map((check) => (
              <div className="check-row" key={check.name}><span className={check.passed ? "pass" : "fail"}>{check.passed ? "✓" : "×"}</span><div><strong>{check.name}</strong><small>{check.message}</small></div></div>
            ))}
            {report?.similar && report.similar.length > 0 && <div className="similar-box"><strong>可能相似的题目</strong>{report.similar.map((item) => <Link href={`/problems/${item.slug}`} key={item.slug}>{item.title} · {Math.round(item.score * 100)}%</Link>)}</div>}
          </div>
          <label className="checkbox-row rights-box card panel"><input type="checkbox" checked={rights} onChange={(event) => { setRights(event.target.checked); setSaved(false); }} /><span>我确认拥有使用和发布本资料衍生内容的权利，并同意对题目正确性负责。</span></label>
          {error && <div className="notice notice-error">{error}</div>}
          {saved && <div className="notice">草稿已保存</div>}
          <div className="draft-actions">
            <button className="button button-secondary" disabled={!!busy || draft.status === "published"} onClick={save}>{busy === "saving" ? "保存中…" : "保存草稿"}</button>
            <button className="button" disabled={!!busy || draft.status === "published"} onClick={validate}>{busy === "validating" ? "校验中…" : "运行质量门禁"}</button>
            <button className="button button-accent" disabled={!!busy || !rights || !report?.passed || draft.status === "published"} onClick={publish}>{busy === "publishing" ? "发布中…" : "发布到公开题库"}</button>
          </div>
        </aside>
      </div>
    </div>
  );
}
