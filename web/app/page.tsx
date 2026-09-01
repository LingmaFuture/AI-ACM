import Link from "next/link";

import { ProblemList } from "@/components/ProblemList";

export default function HomePage() {
  return (
    <>
      <section className="hero page-shell">
        <div className="hero-copy">
          <span className="eyebrow">AI Algorithm Commons</span>
          <h1>
            不只会调用，
            <br />
            <em>真正写懂</em>算法。
          </h1>
          <p>
            面向 AI 学习者的开放训练场。上传你的课程与认证资料，让 AI
            把知识变成可判题、可练习、可分享的算法挑战。
          </p>
          <div className="button-row">
            <Link className="button" href="/problems">
              开始刷题 <span>→</span>
            </Link>
            <Link className="button button-secondary" href="/contribute">
              上传资料生成题目
            </Link>
          </div>
          <div className="hero-proof">
            <span><b>Python</b> 单一语言</span>
            <span><b>NumPy</b> 真实计算</span>
            <span><b>AI</b> 自动出题</span>
          </div>
        </div>
        <div className="hero-visual" aria-label="算法判题流程示意">
          <div className="code-window">
            <div className="window-top"><i /><i /><i /><span>solution.py</span></div>
            <pre><code><span className="code-pink">class</span> <span className="code-yellow">Solution</span>:{"\n"}  <span className="code-pink">def</span> <span className="code-teal">predict</span>(self, X, k):{"\n"}    distances = np.<span className="code-teal">sqrt</span>(...){"\n"}    neighbors = np.<span className="code-teal">argsort</span>(distances){"\n"}    <span className="code-pink">return</span> vote(neighbors[:k])</code></pre>
            <div className="code-result"><span>✓</span><div><strong>Accepted</strong><small>8 / 8 测试通过 · 41ms</small></div></div>
          </div>
          <div className="orbit orbit-one">KNN</div>
          <div className="orbit orbit-two">K-Means</div>
          <div className="orbit orbit-three">PCA</div>
        </div>
      </section>

      <section className="how-section">
        <div className="page-shell how-inner">
          <div>
            <span className="eyebrow">From notes to practice</span>
            <h2>一份资料，走完出题全流程</h2>
          </div>
          <div className="step-grid">
            {[
              ["01", "上传", "PDF、Word、图片或 Markdown，原文件默认私有。"],
              ["02", "生成", "AI 提取知识点，给出题干、答案、样例和隐藏测试。"],
              ["03", "校验", "参考实现与典型错解自动过一遍真正的判题环境。"],
              ["04", "共练", "发布到公共题库，让每个人都能提交和积累进度。"],
            ].map(([number, title, copy]) => (
              <article className="step" key={number}>
                <span>{number}</span><h3>{title}</h3><p>{copy}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="page-shell featured-section">
        <div className="section-heading">
          <div><span className="eyebrow">Practice now</span><h2>从一道算法开始</h2></div>
          <Link href="/problems" className="text-link">查看完整题库 →</Link>
        </div>
        <ProblemList compact />
      </section>
    </>
  );
}

