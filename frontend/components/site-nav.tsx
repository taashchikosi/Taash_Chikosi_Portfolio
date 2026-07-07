"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { SITE } from "@/lib/site";

const Caret = () => (
  <svg className="caret" viewBox="0 0 24 24">
    <path d="M6 9l6 6 6-6" />
  </svg>
);

export function SiteNav() {
  const pathname = usePathname();
  const [open, setOpen] = useState<string | null>(null);
  const onHome = pathname === "/";
  const onProjects = pathname === "/projects" || isCaseRoute(pathname);

  // Close dropdowns on outside click / Escape (mirrors the mockup).
  useEffect(() => {
    const close = () => setOpen(null);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    document.addEventListener("click", close);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", close);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const toggle = (id: string, e: React.MouseEvent) => {
    // Stop the NATIVE event too — the outside-click "close" handler is a native
    // document listener, which React's synthetic stopPropagation won't reach,
    // so without this the menu opens and instantly closes on the same click.
    e.stopPropagation();
    e.nativeEvent.stopImmediatePropagation();
    setOpen((cur) => (cur === id ? null : id));
  };

  return (
    <nav>
      <div className="nav-in">
        <Link href="/" className="brand">
          <span className="mk">T</span>
          <span>{SITE.name}</span>
        </Link>
        <div className="links">
          <Link href="/" className={onHome ? "active" : ""}>
            Home
          </Link>

          <div className={`dd${open === "proj" ? " open" : ""}`}>
            <button
              onClick={(e) => toggle("proj", e)}
              className={onProjects ? "active" : ""}
            >
              Projects
              <Caret />
            </button>
            <div className="menu" role="menu">
              <Link href="/projects?lane=agentic">
                <span className="dot" style={{ background: "var(--acc)" }} />
                <span>
                  Agentic AI<span className="sub">2 projects</span>
                </span>
              </Link>
              <Link href="/projects?lane=automation">
                <span className="dot" style={{ background: "var(--cyan)" }} />
                <span>
                  Agents<span className="sub">2 projects</span>
                </span>
              </Link>
            </div>
          </div>

          <div className={`dd${open === "res" ? " open" : ""}`}>
            <button onClick={(e) => toggle("res", e)}>
              Résumé
              <Caret />
            </button>
            <div className="menu" role="menu">
              <a href={SITE.resume} target="_blank" rel="noopener noreferrer">
                <svg className="icn" viewBox="0 0 24 24">
                  <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
                <span>
                  View<span className="sub">opens in a new tab</span>
                </span>
              </a>
              <a href={SITE.resume} download>
                <svg className="icn" viewBox="0 0 24 24">
                  <path d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14" />
                </svg>
                <span>
                  Download<span className="sub">PDF</span>
                </span>
              </a>
              <Link href="/certifications">
                <svg className="icn" viewBox="0 0 24 24">
                  <circle cx="12" cy="9" r="5" />
                  <path d="M8.5 13.2L7 22l5-3 5 3-1.5-8.8" />
                </svg>
                <span>
                  Certifications<span className="sub">credentials &amp; badges</span>
                </span>
              </Link>
            </div>
          </div>

          <a className="nav-social" href={SITE.linkedin} target="_blank" rel="noopener noreferrer" aria-label="LinkedIn">
            <svg className="icn nav-social-icn" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M16 8a6 6 0 016 6v6h-4v-6a2 2 0 00-4 0v6h-4v-10h4v2" />
              <circle cx="4" cy="4" r="2" />
              <path d="M2 9h4v11H2z" />
            </svg>
            <span className="nav-social-txt">LinkedIn</span>
          </a>
          <a className="nav-social" href={SITE.github} target="_blank" rel="noopener noreferrer" aria-label="GitHub">
            <svg
              className="icn nav-social-icn"
              viewBox="0 0 24 24"
              aria-hidden="true"
              style={{ fill: "currentColor", stroke: "none" }}
            >
              <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.5a3 3 0 00-.8-2.3c2.7-.3 5.5-1.3 5.5-6a4.6 4.6 0 00-1.3-3.2 4.3 4.3 0 00-.1-3.2s-1-.3-3.5 1.3a12 12 0 00-6.3 0C6 1.6 5 1.9 5 1.9a4.3 4.3 0 00-.1 3.2A4.6 4.6 0 003.5 8.3c0 4.6 2.8 5.7 5.5 6a3 3 0 00-.8 2.2V21" />
            </svg>
            <span className="nav-social-txt">GitHub</span>
          </a>
        </div>
      </div>
    </nav>
  );
}

function isCaseRoute(path: string) {
  const slugs = [
    "energy-modeller",
    "auditagent",
    "vera",
    "margo",
  ];
  return slugs.some((s) => path === `/${s}`);
}
