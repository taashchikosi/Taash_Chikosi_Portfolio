import type { Metadata } from "next";
import Link from "next/link";
import { Zap, LayoutDashboard, MessageSquareText } from "lucide-react";
import "./globals.css";

export const metadata: Metadata = {
  title: "RetrofitGPT — Building Decarbonisation Advisor",
  description:
    "Autonomous multi-agent retrofit analysis: physics-verified savings, payback and carbon — built on Australian data.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">
        <div className="flex min-h-screen">
          {/* Left nav */}
          <aside className="w-56 shrink-0 border-r border-surface-border bg-surface-raised/50 p-4 flex flex-col gap-1">
            <div className="flex items-center gap-2 px-2 py-3 mb-4">
              <Zap className="h-5 w-5 text-accent" />
              <span className="font-semibold tracking-tight text-white">
                RetrofitGPT
              </span>
            </div>
            <NavLink href="/" icon={<MessageSquareText className="h-4 w-4" />}>
              Analysis
            </NavLink>
            <NavLink href="/dashboard" icon={<LayoutDashboard className="h-4 w-4" />}>
              Dashboard
            </NavLink>
            <div className="mt-auto px-2 py-3 text-xs text-zinc-500">
              🇦🇺 NABERS · NCC · CDR · NGA
            </div>
          </aside>
          <main className="flex-1 overflow-y-auto">{children}</main>
        </div>
      </body>
    </html>
  );
}

function NavLink({
  href,
  icon,
  children,
}: {
  href: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-2 rounded-lg px-2 py-2 text-sm text-zinc-400 hover:bg-surface-border/50 hover:text-white transition-colors"
    >
      {icon}
      {children}
    </Link>
  );
}
