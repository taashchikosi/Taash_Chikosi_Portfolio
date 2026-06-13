import { Github, Linkedin, Mail } from "lucide-react";
import { SITE } from "@/lib/site";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-surface-border">
      <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 px-6 py-8 text-sm text-zinc-500">
        <span>
          © {SITE.name} · built with Next.js, deployed on Vercel
        </span>
        <div className="ml-auto flex items-center gap-4">
          <a
            href={`mailto:${SITE.email}`}
            className="inline-flex items-center gap-1.5 hover:text-zinc-200"
          >
            <Mail className="h-4 w-4" /> Email
          </a>
          <a
            href={SITE.github}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 hover:text-zinc-200"
          >
            <Github className="h-4 w-4" /> GitHub
          </a>
          <a
            href={SITE.linkedin}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 hover:text-zinc-200"
          >
            <Linkedin className="h-4 w-4" /> LinkedIn
          </a>
        </div>
      </div>
    </footer>
  );
}
