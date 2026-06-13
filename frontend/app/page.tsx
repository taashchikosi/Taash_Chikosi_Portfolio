import Link from "next/link";
import { ArrowRight, Github, Cpu, Building2, ShieldCheck } from "lucide-react";
import { PROJECTS } from "@/lib/projects";
import { SITE } from "@/lib/site";
import { ProjectCard } from "@/components/project-card";
import { Reveal } from "@/components/reveal";

const HIGHLIGHTS = [
  {
    icon: Building2,
    title: "Building-energy domain",
    body: "IESVE / EnergyPlus modelling background — I build AI that understands the physics, not just the prompt.",
  },
  {
    icon: Cpu,
    title: "Agentic systems",
    body: "Multi-agent pipelines with a clean tool boundary (MCP), eval-gated model routing, and cost discipline.",
  },
  {
    icon: ShieldCheck,
    title: "Governed & verified",
    body: "Calibration gates, guardrails, and real code-compliance checks — green ticks backed by evidence, not vibes.",
  },
];

export default function HomePage() {
  return (
    <div className="mx-auto max-w-5xl px-6">
      {/* ── Hero ─────────────────────────────────────────────── */}
      <section className="pt-24 pb-16">
        <p className="animate-rise text-sm font-medium text-accent">{SITE.role}</p>
        <h1
          className="animate-rise mt-3 max-w-3xl text-4xl font-semibold leading-[1.1] tracking-tight text-white sm:text-5xl"
          style={{ animationDelay: "80ms" }}
        >
          I build <span className="text-accent">autonomous AI systems</span> for the
          built environment — and ship them live.
        </h1>
        <p
          className="animate-rise mt-5 max-w-2xl text-base leading-relaxed text-zinc-400"
          style={{ animationDelay: "160ms" }}
        >
          {SITE.name.split(" ")[0]} here. I pair a building-energy engineering
          background with agentic-AI engineering: physics-in-the-loop pipelines,
          verified against real standards, deployed end to end. Everything below is a
          working demo, not a slide.
        </p>
        <div
          className="animate-rise mt-8 flex flex-wrap gap-3"
          style={{ animationDelay: "240ms" }}
        >
          <Link
            href="/retrofitgpt"
            className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-black transition-opacity hover:opacity-90"
          >
            See RetrofitGPT <ArrowRight className="h-4 w-4" />
          </Link>
          <a
            href={SITE.github}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-surface-border bg-surface-raised px-5 py-2.5 text-sm font-medium text-zinc-200 transition-colors hover:border-accent/50"
          >
            <Github className="h-4 w-4" /> GitHub
          </a>
        </div>
      </section>

      {/* ── Projects ─────────────────────────────────────────── */}
      <section id="projects" className="scroll-mt-20 border-t border-surface-border pt-14">
        <Reveal>
          <p className="text-xs font-medium uppercase tracking-wider text-accent">
            Projects
          </p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-white">
            Things I&apos;ve built
          </h2>
        </Reveal>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {PROJECTS.map((p, i) => (
            <Reveal key={p.slug} delay={i * 90}>
              <ProjectCard project={p} />
            </Reveal>
          ))}
        </div>
      </section>

      {/* ── About ────────────────────────────────────────────── */}
      <section id="about" className="scroll-mt-20 pt-20">
        <Reveal>
          <p className="text-xs font-medium uppercase tracking-wider text-accent">
            About
          </p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-white">
            Engineering the physics, not just the prompt
          </h2>
          <p className="mt-5 max-w-2xl text-sm leading-relaxed text-zinc-400">
            {/* TODO: personalise this paragraph. */}
            I&apos;m a building-energy engineer moving into agentic-AI engineering and
            solution architecture, focused on the Australian market — NABERS, NCC
            Section J, and decarbonisation. My work sits where domain rigour meets
            modern AI: systems that run real simulations, cite real codes, and are
            honest about what they can and can&apos;t yet prove.
          </p>
        </Reveal>

        <div className="mt-8 grid gap-4 sm:grid-cols-3">
          {HIGHLIGHTS.map((h, i) => (
            <Reveal key={h.title} delay={i * 90}>
              <div className="h-full rounded-xl border border-surface-border bg-surface-raised p-5">
                <h.icon className="h-5 w-5 text-accent" />
                <p className="mt-3 text-sm font-medium text-zinc-100">{h.title}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-zinc-400">{h.body}</p>
              </div>
            </Reveal>
          ))}
        </div>

        <Reveal>
          <div className="mt-8 flex flex-wrap gap-3 text-sm">
            <a
              href={`mailto:${SITE.email}`}
              className="inline-flex items-center gap-2 rounded-lg border border-surface-border bg-surface-raised px-4 py-2 text-zinc-200 transition-colors hover:border-accent/50"
            >
              Get in touch
            </a>
          </div>
        </Reveal>
      </section>
    </div>
  );
}
