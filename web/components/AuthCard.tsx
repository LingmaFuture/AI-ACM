import { Logo } from "./Logo";

export function AuthCard({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="auth-page">
      <div className="auth-aside">
        <div>
          <span className="eyebrow">LEARN · CODE · VERIFY</span>
          <h2>每一次通过，都是对算法真正理解的证明。</h2>
        </div>
        <pre className="mono">distance → neighbors → vote{"\n"}samples → centers → clusters</pre>
      </div>
      <section className="auth-card">
        <Logo />
        <div><span className="eyebrow">{eyebrow}</span><h1>{title}</h1></div>
        {children}
      </section>
    </div>
  );
}

