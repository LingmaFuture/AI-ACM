import Link from "next/link";

import { Logo } from "./Logo";
import { SessionNav } from "./SessionNav";

export function Header() {
  return (
    <header className="site-header">
      <div className="header-inner">
        <Logo />
        <nav className="main-nav" aria-label="主导航">
          <Link href="/problems">题库</Link>
          <Link href="/leaderboard">排行榜</Link>
          <Link href="/contribute">AI 投稿</Link>
        </nav>
        <SessionNav />
      </div>
    </header>
  );
}

