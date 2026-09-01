import type { Metadata } from "next";

import { Header } from "@/components/Header";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "AI-ACM · AI 算法训练场", template: "%s · AI-ACM" },
  description: "上传算法资料，自动生成题目，像刷 ACM 一样练习 AI 算法。",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <Header />
        <main>{children}</main>
        <footer className="site-footer">
          <div>
            <strong>AI-ACM</strong>
            <span>把散落的算法资料，变成每个人都能练习的题。</span>
          </div>
          <span>Python + NumPy · 社区共建</span>
        </footer>
      </body>
    </html>
  );
}
