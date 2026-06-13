"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Zap, Github } from "lucide-react";
import { SITE } from "@/lib/site";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/#projects", label: "Projects" },
  { href: "/#about", label: "About" },
];

export function SiteNav() {
  const pathname = usePathname();
  const onHome = pathname === "/";
  // Point the nav's demo CTA at whichever project the visitor is currently reading.
  const demoHref = pathname.startsWith("/auditagent")
    ? "/auditagent/demo"
    : "/retrofitgpt/demo";

  return (
    <header className="sticky top-0 z-40 border-b border-surface-border bg-surface/80 backdrop-blur">
      <nav className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-3.5">
        <Link href="/" className="flex items-center gap-2 text-white">
          <Zap className="h-5 w-5 text-accent" />
          <span className="font-semibold tracking-tight">{SITE.name}</span>
        </Link>

        <div className="ml-auto flex items-center gap-1 text-sm">
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="rounded-lg px-3 py-1.5 text-zinc-400 transition-colors hover:bg-surface-raised hover:text-white"
            >
              {l.label}
            </Link>
          ))}
          {!onHome && (
            <Link
              href={demoHref}
              className="ml-1 rounded-lg bg-accent px-3 py-1.5 font-medium text-black transition-opacity hover:opacity-90"
            >
              Live demo
            </Link>
          )}
          <a
            href={SITE.github}
            target="_blank"
            rel="noreferrer"
            aria-label="GitHub"
            className="ml-1 rounded-lg p-2 text-zinc-400 transition-colors hover:bg-surface-raised hover:text-white"
          >
            <Github className="h-4 w-4" />
          </a>
        </div>
      </nav>
    </header>
  );
}
