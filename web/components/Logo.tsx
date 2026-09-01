import Link from "next/link";

export function Logo() {
  return (
    <Link href="/" className="logo" aria-label="AI-ACM 首页">
      <span className="logo-mark">A²</span>
      <span>
        <strong>AI-ACM</strong>
        <small>算法训练场</small>
      </span>
    </Link>
  );
}

