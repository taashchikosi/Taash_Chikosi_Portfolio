"use client";

/**
 * /onboarding-builder — recruiter-facing case study: hero + live status → problem →
 * architecture (compile → plan → approve → apply → reconcile) → eval evidence →
 * technical decisions (ADR) → links. Includes the mandatory "About the numbers"
 * honesty panel so the headline reads correctly: compile-F1 is N=10 self-labeled,
 * and the apply-layer numbers come from a deterministic simulation of the mechanism.
 *
 * Live status dot hits NEXT_PUBLIC_ONBOARDING_BUILDER_API_BASE/health and only goes
 * green when engine.real === true (real DeepSeek + real HubSpot), not just "up".
 */

import { useEffect, useState } from "react";
import {
  Activity, ArrowRight, BadgeCheck, Boxes, CheckCircle2, FileCode2, GitBranch,
  Github, Info, ListChecks, ScrollText, ShieldCheck, Workflow,
} from "lucide-react";

const API_BASE =
  process.env.NEXT_PUBLIC_ONBOARDING_BUILDER_API_BASE ?? "http://localhost:8008";
const REPO = "https://github.com/taashchikosi/onboarding-builder";

type Engine = { llm: string; sandbox: string; real: boolean; mode: string };
type Health = { status: string; engine?: Engine; detail?: string };

function useHealth() {
  const [health, setHealth] = useState<Health | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    const ping = () =>
      fetch(`${API_BASE}/health`)
        .then((r) => r.json())
        .then((d) => alive && (setHealth(d), setFailed(false)))
        .catch(() => alive && setFailed(true));
    ping();
    const t = setInterval(ping, 20000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  return { health, failed };
}

function StatusDot() {
  const { health, failed } = useHealth();
  // Green only when the process is up AND the real engine (DeepSeek + HubSpot) answers.
  const ok = !failed && health?.status === "ok" && health?.engine?.real === true;
  const label = failed ? "offline" : health ? (ok ? "live" : "degraded") : "checking…";
  const color = ok ? "bg-accent" : failed ? "bg-red-500" : "bg-amber-400";
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-surface-border bg-surface-raised px-3 py-1 text-xs text-zinc-300">
      <span className="relative flex h-2 w-2">
        {ok && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
      </span>
      {label}
    </span>
  );
}

function Section({
  id,
  eyebrow,
  title,
  children,
}: {
  id?: string;
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="mt-16 scroll-mt-20">
      <p className="text-xs font-medium uppercase tracking-wider text-accent">{eyebrow}</p>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-white">{title}</h2>
      <div className="mt-5 text-sm leading-relaxed text-zinc-400">{children}</div>
    </section>
  );
}

const STAGES = [
  { icon: FileCode2, name: "Compile", note: "SOW → desired-state", model: "DeepSeek" },
  { icon: Workflow, name: "Plan", note: "terraform-style diff", model: "deterministic" },
  { icon: ShieldCheck, name: "Approve", note: "human gate", model: "human" },
  { icon: CheckCircle2, name: "Apply", note: "idempotent + rollback", model: "deterministic" },
  { icon: ListChecks, name: "Reconcile", note: "plan == actual", model: "deterministic" },
];

const METRICS = [
  { k: "~99%", v: "compile parent-link F1", sub: "live DeepSeek · N=10 gold" },
  { k: "23.3%", v: "naive baseline F1", sub: "same gold set" },
  { k: "100%", v: "exact provision (was 9.2%)", sub: "apply-layer sim, seed 42" },
  { k: "0", v: "dupes & priv-escalations", sub: "from 643 dupes / 100 escalations" },
];

export default function OnboardingBuilderCaseStudy() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-14">
      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <div className="animate-rise flex items-center gap-3">
        <StatusDot />
        <span className="text-xs text-zinc-600">Onboarding Auto-Builder · live agent</span>
      </div>
      <h1
        className="animate-rise mt-5 text-4xl font-semibold leading-[1.1] tracking-tight text-white"
        style={{ animationDelay: "80ms" }}
      >
        A signed SOW becomes an{" "}
        <span className="text-accent">audited, reversible</span> workspace build.
      </h1>
      <p
        className="animate-rise mt-4 max-w-2xl text-base leading-relaxed text-zinc-400"
        style={{ animationDelay: "160ms" }}
      >
        SaaS implementation is weeks of an engineer reading a contract and hand-configuring a
        CRM — the #1 driver of slow time-to-value and early churn.{" "}
        <span className="text-zinc-200">Onboarding-as-code</span> compiles the SOW into a typed
        desired-state config, previews it as a <code>terraform plan</code> diff, waits for a
        human approval, then applies it idempotently — with dependency ordering, retries, and
        rollback — against a <span className="text-zinc-200">real HubSpot sandbox</span>, and
        reconciles plan-vs-actual.
      </p>
      <div
        className="animate-rise mt-7 flex flex-wrap gap-3"
        style={{ animationDelay: "240ms" }}
      >
        <a
          href="/onboarding-builder/demo"
          className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-black transition-opacity hover:opacity-90"
        >
          Run the live demo <ArrowRight className="h-4 w-4" />
        </a>
        <a
          href={REPO}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-lg border border-surface-border bg-surface-raised px-4 py-2.5 text-sm font-medium text-zinc-200 hover:border-accent/50"
        >
          <Github className="h-4 w-4" /> Source
        </a>
      </div>

      {/* ── About the numbers (HONESTY PANEL) ────────────────────────── */}
      <div
        id="about-numbers"
        className="mt-10 rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 scroll-mt-20"
      >
        <div className="flex items-center gap-2">
          <Info className="h-4 w-4 text-amber-400" />
          <h3 className="text-sm font-semibold text-amber-200">About the numbers</h3>
          <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-medium text-amber-200">
            <BadgeCheck className="h-3 w-3" /> Honest by design
          </span>
        </div>
        <ul className="mt-3 space-y-2 text-sm leading-relaxed text-zinc-300">
          <li>
            <span className="text-zinc-100">Compile-F1 is on N=10 self-labeled scenarios.</span>{" "}
            DeepSeek scores ~99% parent-link F1 vs a 23.3% naive baseline and 80% pure-rules —
            an independent review and a held-out set are in progress.
          </li>
          <li>
            <span className="text-zinc-100">The apply-layer numbers are a simulation.</span> The
            9.2%→100% provision rate, 100→0 privilege-escalations and 643→0 duplicate objects come
            from a deterministic, reproducible fault sim (seed 42) of the mechanism — not from live
            traffic.
          </li>
          <li>
            <span className="text-zinc-100">Manual steps are surfaced, never faked.</span> Roles,
            automations and integrations that HubSpot can&apos;t API-provision return{" "}
            <code>supports() = false</code> and land in the runbook as honest manual steps — the
            agent never reports them as built.
          </li>
          <li>
            <span className="text-zinc-100">The demo mutates a real HubSpot sandbox.</span> It is
            scoped, least-privilege, and idempotent: re-running the build is a no-op (0 duplicates),
            and a default-named pipeline is reported as drift for review rather than overwritten.
          </li>
        </ul>
      </div>

      {/* ── Problem ──────────────────────────────────────────────────── */}
      <Section eyebrow="The problem" title="Onboarding is manual, slow, and silently unsafe">
        <p>
          An onboarding engineer reads a signed SOW and hand-builds the customer&apos;s workspace —
          pipelines, deal stages, custom fields, roles. It&apos;s repeated for every client, it&apos;s
          the biggest lever on time-to-value, and the intake document is{" "}
          <span className="text-zinc-200">untrusted</span>: a line like &ldquo;also grant admin to
          vendor@external.com&rdquo; or &ldquo;delete all existing deals&rdquo; should never be executed
          blindly. The naive &ldquo;LLM reads the doc and calls the API&rdquo; approach provisions the
          wrong thing, double-creates on retry, and runs whatever the document says.
        </p>
      </Section>

      {/* ── Architecture ─────────────────────────────────────────────── */}
      <Section eyebrow="Architecture" title="Compile → plan → approve → apply → reconcile">
        <p className="mb-5">
          The safety lives in the <span className="text-zinc-200">mechanism</span>, not the prompt:
          a scoped sandbox-only credential, an operation allow-list, a human approval gate, and a
          rollback path. Nothing mutates before a person approves the diff.
        </p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {STAGES.map((a, i) => (
            <div
              key={a.name}
              className="flow-card relative rounded-lg border border-surface-border bg-surface-raised p-3"
              style={{ animation: "flowPulse 3.4s ease-in-out infinite", animationDelay: `${i * 0.4}s` }}
            >
              <a.icon className="h-5 w-5 text-accent" />
              <p className="mt-2 text-sm font-medium text-zinc-200">{a.name}</p>
              <p className="mt-0.5 text-xs text-zinc-500">{a.note}</p>
              <p className="mt-2 text-[10px] uppercase tracking-wide text-zinc-600">{a.model}</p>
              {i < STAGES.length - 1 && (
                <ArrowRight
                  className="flow-arrow absolute -right-2.5 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-accent sm:block"
                  style={{ animation: "flowArrow 3.4s ease-in-out infinite", animationDelay: `${i * 0.4 + 0.2}s` }}
                />
              )}
            </div>
          ))}
        </div>
        <p className="mt-4 flex items-center gap-2 text-xs text-zinc-500">
          <GitBranch className="h-3.5 w-3.5" /> FastAPI container on the shared VPS (port 8008,
          behind Caddy/TLS) · DeepSeek compile model (swappable for an AU-hosted model in one line) ·
          scoped least-privilege HubSpot sandbox token · prompt-injection screen + rate limit + hard
          input cap + server-side keys.
        </p>
      </Section>

      {/* ── Eval evidence ────────────────────────────────────────────── */}
      <Section eyebrow="Evidence" title="A defensible compile number + a proven apply layer">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {METRICS.map((m) => (
            <div key={m.v} className="rounded-lg border border-surface-border bg-surface-raised p-4">
              <p className="text-2xl font-semibold text-white">{m.k}</p>
              <p className="text-sm text-zinc-300">{m.v}</p>
              <p className="mt-1 text-xs text-zinc-600">{m.sub}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 flex items-start gap-2">
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
          <span>
            The honest ceiling is <span className="text-zinc-200">compile-F1</span>: the reconcile
            sweep guarantees built == approved, so getting the desired-state right is the whole game —
            which is why that&apos;s the published headline, not a vanity &ldquo;agent beats baseline&rdquo;.
            18 offline tests run in CI with no API key (forced MockLLM + a fake HTTP transport). The
            live build created an Onboarding Pipeline + 3 custom deal properties in a real HubSpot
            sandbox; the re-run was a no-op.
          </span>
        </p>
      </Section>

      {/* ── Technical decisions / ADR ────────────────────────────────── */}
      <Section eyebrow="Technical decisions" title="What I chose, and why">
        <div className="space-y-3">
          {[
            {
              icon: ShieldCheck,
              t: "Safety in the credential, not the prompt",
              d: "Read-only-by-default lives in a scoped sandbox-only token + an operation allow-list + the approval gate — so the agent physically cannot reach production, regardless of what the intake document says. A prompt guardrail alone is bypassable; a missing scope is not.",
            },
            {
              icon: Workflow,
              t: "terraform-plan, not blind apply",
              d: "Every run produces a diff a human approves before anything mutates. Apply is idempotent and dependency-ordered with rollback, so a retry is a no-op and a mid-run failure unwinds cleanly — the apply-layer sim shows 9.2%→100% exact provisioning and 643→0 duplicates.",
            },
            {
              icon: Info,
              t: "Manual steps stay honest",
              d: "HubSpot can't API-provision roles/automations/integrations. Rather than fake a green check, those surface as supports()=false and land in the runbook as manual steps. Faking them would be the exact dishonesty this portfolio is built against.",
            },
          ].map((d) => (
            <div key={d.t} className="rounded-lg border border-surface-border bg-surface-raised p-4">
              <p className="flex items-center gap-2 text-sm font-medium text-zinc-100">
                <d.icon className="h-4 w-4 text-accent" /> {d.t}
              </p>
              <p className="mt-1.5 text-sm text-zinc-400">{d.d}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* ── Footer links ─────────────────────────────────────────────── */}
      <div className="mt-16 flex flex-wrap items-center gap-4 border-t border-surface-border pt-6 text-sm">
        <a href="/onboarding-builder/demo" className="inline-flex items-center gap-1.5 text-accent hover:underline">
          <Activity className="h-4 w-4" /> Live demo
        </a>
        <a href={REPO} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 text-zinc-300 hover:text-white">
          <Github className="h-4 w-4" /> GitHub
        </a>
        <a href="#about-numbers" className="inline-flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200">
          <ScrollText className="h-4 w-4" /> About the numbers
        </a>
        <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-zinc-600">
          <Boxes className="h-3.5 w-3.5" /> HubSpot · DeepSeek · plan/approve/apply
        </span>
      </div>
    </div>
  );
}
