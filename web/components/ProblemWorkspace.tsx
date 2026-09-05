"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError, difficultyLabel, statusLabel } from "@/lib/api";
import { formatJson } from "@/lib/formatJson";
import type { Problem, Submission } from "@/lib/types";

import { CodeEditor } from "./CodeEditor";

function Description({ text }: { text: string }) {
  return (
    <div className="problem-copy">
      {text.split("\n").map((line, index) =>
        line ? <p key={index}>{line}</p> : <div className="copy-space" key={index} />,
      )}
    </div>
  );
}

export function ProblemWorkspace() {
  const params = useParams<{ slug: string }>();
  const [problem, setProblem] = useState<Problem | null>(null);
  const [code, setCode] = useState("");
  const [submission, setSubmission] = useState<Submission | null>(null);
  const [history, setHistory] = useState<Submission[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<"description" | "submissions">("description");

  const loadHistory = useCallback(async (problemId: string) => {
    try {
      const data = await api<{ items: Submission[] }>(`/problems/${problemId}/submissions`);
      setHistory(data.items);
    } catch {
      setHistory([]);
    }
  }, []);

  useEffect(() => {
    api<Problem>(`/problems/${params.slug}`)
      .then((data) => {
        setProblem(data);
        const saved = window.localStorage.getItem(`solution:${data.id}:v${data.version}`);
        setCode(saved ?? data.starter_code);
        void loadHistory(data.id);
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : "题目加载失败"))
      .finally(() => setLoading(false));
  }, [loadHistory, params.slug]);

  useEffect(() => {
    if (problem && code) window.localStorage.setItem(`solution:${problem.id}:v${problem.version}`, code);
  }, [code, problem]);

  function listen(submissionId: string) {
    const source = new EventSource(`/api/v1/submissions/${submissionId}/events`);
    source.addEventListener("status", (event) => {
      const next = JSON.parse((event as MessageEvent).data) as Submission;
      setSubmission(next);
      if (next.finished_at) {
        source.close();
        setRunning(false);
        if (problem) void loadHistory(problem.id);
      }
    });
    source.addEventListener("error", () => {
      source.close();
      setRunning(false);
    });
  }

  async function execute(kind: "run" | "submit") {
    if (!problem || running) return;
    setError("");
    setRunning(true);
    setSubmission(null);
    try {
      const data = await api<{ id: string }>(`/problems/${problem.id}/${kind}`, {
        method: "POST",
        body: JSON.stringify({ code }),
      });
      listen(data.id);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        setError("提交代码前请先登录。你的代码已经保存在浏览器中。 ");
      } else {
        setError(caught instanceof Error ? caught.message : "提交失败");
      }
      setRunning(false);
    }
  }

  async function report() {
    if (!problem) return;
    const details = window.prompt("请简要说明题目中的问题：");
    if (!details) return;
    try {
      await api(`/problems/${problem.id}/reports`, {
        method: "POST",
        body: JSON.stringify({ reason: "incorrect", details }),
      });
      window.alert("已收到举报，谢谢你帮助维护题库质量。 ");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "举报失败");
    }
  }

  async function revise() {
    if (!problem) return;
    setError("");
    try {
      const draft = await api<{ id: string }>(`/problems/${problem.id}/revisions`, {
        method: "POST",
      });
      window.location.href = `/drafts/${draft.id}`;
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建修订草稿失败");
    }
  }

  if (loading) return <div className="loading"><div className="loader" /></div>;
  if (!problem) return <div className="narrow-shell"><div className="notice notice-error">{error || "题目不存在"}</div></div>;

  return (
    <div className="workspace">
      <section className="problem-pane">
        <div className="pane-tabs">
          <button className={tab === "description" ? "active" : ""} onClick={() => setTab("description")}>题目描述</button>
          <button className={tab === "submissions" ? "active" : ""} onClick={() => setTab("submissions")}>我的提交 <span>{history.length}</span></button>
        </div>
        {tab === "description" ? (
          <div className="problem-scroll">
            <div className="problem-heading">
              <div className="problem-kicker"><span className={`difficulty ${problem.difficulty}`}>{difficultyLabel(problem.difficulty)}</span><span>版本 {problem.version}</span></div>
              <h1>{problem.title}</h1>
              <div className="row-tags">{problem.tags.map((tag) => <span className="tag" key={tag}>{tag}</span>)}</div>
            </div>
            <Description text={problem.description} />
            <section className="statement-section">
              <h3>函数接口</h3>
              <div className="signature mono">
                {problem.function_spec.class_name}.{problem.function_spec.method_name}(
                {problem.function_spec.args.map((arg) => `${arg.name}: ${arg.type}`).join(", ")}) → {problem.function_spec.return_type}
              </div>
            </section>
            <section className="statement-section">
              <h3>公开样例</h3>
              {problem.public_cases.map((test) => (
                <div className="example-box" key={test.name}>
                  <strong>{test.name}</strong>
                  <pre><span>输入</span>{formatJson(test.args)}{"\n"}<span>输出</span>{formatJson(test.expected)}</pre>
                </div>
              ))}
            </section>
            <section className="statement-section">
              <h3>约束</h3>
              <ul className="constraint-list">{problem.constraints.map((value) => <li key={value}>{value}</li>)}</ul>
            </section>
            <div className="problem-meta">
              由 {problem.author} 发布 · <button onClick={report}>报告问题</button>
              {problem.can_edit && <> · <button onClick={revise}>创建新版本</button></>}
            </div>
          </div>
        ) : (
          <div className="problem-scroll submission-list">
            {history.length === 0 && <div className="empty-state">登录并提交后，结果会出现在这里。</div>}
            {history.map((item) => (
              <article key={item.id}>
                <span className={`submission-status ${item.status}`}>{statusLabel(item.status)}</span>
                <div><strong>{item.kind === "run" ? "运行样例" : "正式提交"}</strong><small>{new Date(item.created_at).toLocaleString("zh-CN")}</small></div>
                <span className="mono">{item.passed_cases}/{item.total_cases}</span>
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="editor-pane">
        <div className="editor-topbar">
          <div><span className="language-dot" /> Python 3 + NumPy</div>
          <button onClick={() => setCode(problem.starter_code)}>重置代码</button>
        </div>
        <div className="editor-body"><CodeEditor value={code} onChange={setCode} /></div>
        <div className="result-pane">
          <div className="result-title">
            <strong>判题结果</strong>
            {submission && <span className={`submission-status ${submission.status}`}>{statusLabel(submission.status)}</span>}
          </div>
          {error && <div className="notice notice-error">{error}{error.includes("登录") && <Link href="/login">去登录 →</Link>}</div>}
          {!submission && !error && <p className="muted result-placeholder">先运行公开样例，确认后再提交隐藏测试。</p>}
          {submission && (
            <div className="case-results">
              {submission.result?.message && <div className="notice notice-error">{submission.result.message}</div>}
              {submission.result?.cases?.map((test, index) => (
                <div className={test.passed ? "passed" : "failed"} key={`${test.name}-${index}`}>
                  <span>{test.passed ? "✓" : "×"}</span>
                  <div><strong>{test.name}</strong><small>{test.message}{test.actual !== undefined ? ` · 输出 ${JSON.stringify(test.actual)}` : ""}</small></div>
                  <code>{test.runtime_ms} ms</code>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="editor-actions">
          <span className="mono">⌘ / Ctrl + S 自动保存在本地</span>
          <button className="button button-secondary button-small" disabled={running} onClick={() => execute("run")}>运行样例</button>
          <button className="button button-accent button-small" disabled={running} onClick={() => execute("submit")}>{running ? "判题中…" : "提交答案"}</button>
        </div>
      </section>
    </div>
  );
}
