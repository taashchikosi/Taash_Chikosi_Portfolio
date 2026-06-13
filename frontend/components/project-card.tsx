import Link from "next/link";
import { ArrowRight, Github } from "lucide-react";
import type { Project } from "@/lib/projects";

const STATUS_STYLES: Record<Project["status"], { label: string; cls: string }> = {
  live: {
    label: "Live",
    cls: "border-accent/40 bg-accent-soft text-accent",
  },
  "in-progress": {
    label: "In progress",
    cls: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  },
  planned: {
    label: "Planned",
    cls: "border-surface-border bg-surface text-zinc-500",
  },
};

export function ProjectCard({ project }: { project: Project }) {
  const status = STATUS_STYLES[project.status];
  const isPlanned = project.status === "planned";

  const inner = (
    <div
      className={`group relative flex h-full flex-col rounded-2xl border border-surface-border bg-surface-raised p-6 transition-colors ${
        isPlanned ? "opacity-60" : "hover:border-accent/50"
      }`}
    >
      <div className="flex items-center gap-2">
        <h3 className="text-lg font-semibold text-white">{project.title}</h3>
        <span
          className={`ml-auto inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${status.cls}`}
        >
          {project.status === "live" && (
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent" />
            </span>
          )}
          {status.label}
        </span>
      </div>

      <p className="mt-1 text-sm text-accent">{project.tagline}</p>
      <p className="mt-3 text-sm leading-relaxed text-zinc-400">{project.blurb}</p>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {project.tags.map((t) => (
          <span
            key={t}
            className="rounded-md border border-surface-border bg-surface px-2 py-0.5 text-[11px] text-zinc-400"
          >
            {t}
          </span>
        ))}
      </div>

      {!isPlanned && (
        <div className="mt-5 flex items-center gap-4 pt-1 text-sm">
          <span className="inline-flex items-center gap-1.5 font-medium text-accent">
            View case study
            <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
          </span>
          {project.repo && (
            <span className="inline-flex items-center gap-1.5 text-zinc-500">
              <Github className="h-3.5 w-3.5" /> Source
            </span>
          )}
        </div>
      )}
    </div>
  );

  if (isPlanned || !project.href) return inner;
  return (
    <Link href={project.href} className="block h-full">
      {inner}
    </Link>
  );
}
