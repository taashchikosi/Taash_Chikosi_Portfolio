"use client";

/**
 * /retrofitgpt — recruiter-facing case study: hero + live status → problem →
 * architecture → eval metrics → technical decisions (ADR) → links. Includes the
 * mandatory "About the model" panel + "Demo calibration" badge so the green verdict
 * is never mistaken for a real-building calibration (docs/ARCHETYPE_AND_CALIBRATION.md §6).
 *
 * Live status dot hits NEXT_PUBLIC_API_BASE/health (the VPS container behind Caddy TLS).
 */

import { useEffect, useState } from "react";
import {
  Activity, ArrowRight, BadgeCheck, Boxes, CircleAlert, Cpu, Database,
  FlaskConical, Gauge, GitBranch, Github, Info, Leaf, ShieldCheck, Building2,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080";
const REPO = "https://github.com/taashchikosi/Taash_Chikosi_Portfolio";

type Health = {
  status: string;
  live_simulation_available?: boolean;
  token_budget?: { exhausted?: boolean };
};

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
  const ok = !failed && health?.status === "ok";
  const label = failed
    ? "offline"
    : health
    ? health.status === "ok"
      ? "live"
      : "degraded"
    : "checking…";
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
      <p className="text-xs font-medium uppercase tracking-wider text-accent">
        {eyebrow}
      </p>
      <h2 className="mt-1 text-2xl font-semibold tracking-tight text-white">
        {title}
      </h2>
      <div className="mt-5 text-sm leading-relaxed text-zinc-400">{children}</div>
    </section>
  );
}

const AGENTS = [
  { icon: Database, name: "Retriever", note: "inspect IDF + classify", model: "Claude" },
  { icon: Boxes, name: "Modeler", note: "pick measures + NCC J7D3", model: "DeepSeek" },
  { icon: Cpu, name: "Sim Runner", note: "real EnergyPlus", model: "—" },
  { icon: Gauge, name: "Analyzer", note: "$ / payback / NPV / tCO₂e", model: "deterministic" },
  { icon: ShieldCheck, name: "Reviewer", note: "GL14 + LLM06 + citations", model: "Claude" },
];

const METRICS = [
  { k: "125", v: "tests green", sub: "unit + eval, CI-gated" },
  { k: "5 / 71", v: "golden cases / checks", sub: "Tier A regression gate" },
  { k: "GL14", v: "calibration", sub: "monthly 5% / 15%" },
  { k: "NCC J7D3", v: "real compliance", sub: "lighting + aggregate" },
];

export default function RetrofitGPTCaseStudy() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-14">
      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <StatusDot />
        <span className="text-xs text-zinc-600">RetrofitGPT · live agent</span>
      </div>
      <h1 className="mt-5 text-4xl font-semibold leading-tight tracking-tight text-white">
        An autonomous multi-agent system that turns a building energy model into an
        audit-ready{" "}
        <span className="text-accent">decarbonisation business case</span>.
      </h1>
      <p className="mt-4 max-w-2xl text-base leading-relaxed text-zinc-400">
        Upload a <span className="text-zinc-200">.idf</span> model + 12 months of
        bills → five agents run <span className="text-zinc-200">real EnergyPlus</span>{" "}
        retrofit simulations and return savings %, payback, NPV and tCO₂e — verified
        against ASHRAE Guideline 14, an OWASP-LLM06 guardrail, and real NCC 2022
        Section J code compliance.
      </p>
      <div className="mt-7 flex flex-wrap gap-3">
        <a
          href="/retrofitgpt/demo"
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

      {/* ── About the model (HONESTY PANEL) ──────────────────────────── */}
      <div
        id="about-model"
        className="mt-10 rounded-xl border border-amber-500/30 bg-amber-500/5 p-5 scroll-mt-20"
      >
        <div className="flex items-center gap-2">
          <Info className="h-4 w-4 text-amber-400" />
          <h3 className="text-sm font-semibold text-amber-200">About the model</h3>
          <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-medium text-amber-200">
            <BadgeCheck className="h-3 w-3" /> Demo calibration
          </span>
        </div>
        <p className="mt-3 text-sm leading-relaxed text-zinc-300">
          <span className="text-zinc-100">What you&apos;re seeing:</span> a live run on
          the <span className="text-zinc-100">DOE Small Office reference building</span>{" "}
          (Sydney climate) — a representative archetype, not a specific building. The
          energy figures come from a <span className="text-zinc-100">real EnergyPlus
          simulation</span>. The green calibration badge in this demo uses{" "}
          <span className="text-zinc-100">synthetic bills derived from the baseline</span>{" "}
          to exercise the approval path; calibrating to a <em>real</em> building requires
          tuning the model to its actual bills (NMBE ≤ 5%, CV-RMSE ≤ 15%, ASHRAE
          Guideline 14). That tuning loop is the next milestone.
        </p>
        <p className="mt-2 text-xs text-zinc-500">
          Baseline EUI 133.1 kWh/m²·yr · units are kWh/m²·yr (not MJ).
        </p>
      </div>

      {/* ── Problem ──────────────────────────────────────────────────── */}
      <Section eyebrow="The problem" title="Energy audits are slow, manual, and hard to trust">
        <p>
          A commercial retrofit business case takes an engineer days of EnergyPlus
          modelling, spreadsheet finance, and manual code-compliance checks — and the
          output is only as trustworthy as the assumptions buried inside it. The hard
          part isn&apos;t running one simulation; it&apos;s producing a number a client
          can act on, with the calibration, governance, and code citations that make it
          defensible.
        </p>
      </Section>

      {/* ── Architecture ─────────────────────────────────────────────── */}
      <Section eyebrow="Architecture" title="Five agents, one MCP physics layer">
        <p className="mb-5">
          The agents never touch EnergyPlus directly — physics and reference data live
          behind an <span className="text-zinc-200">MCP server</span> (20 tools). That
          boundary is the architecture: swapping seed data for RAG over the live NCC
          changes a tool, not an agent. The LLM only makes judgement calls; every number
          is deterministic arithmetic or a simulated value.
        </p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
          {AGENTS.map((a, i) => (
            <div
              key={a.name}
              className="relative rounded-lg border border-surface-border bg-surface-raised p-3"
            >
              <a.icon className="h-5 w-5 text-accent" />
              <p className="mt-2 text-sm font-medium text-zinc-200">{a.name}</p>
              <p className="mt-0.5 text-xs text-zinc-500">{a.note}</p>
              <p className="mt-2 text-[10px] uppercase tracking-wide text-zinc-600">
                {a.model}
              </p>
              {i < AGENTS.length - 1 && (
                <ArrowRight className="absolute -right-2.5 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-surface-border sm:block" />
              )}
            </div>
          ))}
        </div>
        <p className="mt-4 flex items-center gap-2 text-xs text-zinc-500">
          <GitBranch className="h-3.5 w-3.5" /> The Reviewer routes failures back —
          calibration fail → Modeler, claim/citation fail → Analyzer (max 3 cycles),
          with a human gate before any simulation runs.
        </p>
      </Section>

      {/* ── Eval metrics ─────────────────────────────────────────────── */}
      <Section eyebrow="Evidence" title="Evals, not vibes">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {METRICS.map((m) => (
            <div
              key={m.v}
              className="rounded-lg border border-surface-border bg-surface-raised p-4"
            >
              <p className="text-2xl font-semibold text-white">{m.k}</p>
              <p className="text-sm text-zinc-300">{m.v}</p>
              <p className="mt-1 text-xs text-zinc-600">{m.sub}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 flex items-start gap-2">
          <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
          <span>
            A two-tier eval gate backs the model-routing decision. Tier A pins five
            golden buildings (office, medium office, retail, school) to expected
            savings/payback bands + compliance verdicts. Tier B runs the real
            LLM-judgement nodes against each provider — checking classification, measure
            selection, valid-JSON, stability across samples, and a citation judge that
            must flag fabricated rebates.
          </span>
        </p>
      </Section>

      {/* ── Technical decisions / ADR ────────────────────────────────── */}
      <Section eyebrow="Technical decisions" title="What I chose, and why">
        <div className="space-y-3">
          {[
            {
              icon: Cpu,
              t: "The eval picks the model per node",
              d: "A live Tier-B swap caught DeepSeek stably mis-sizing a 511 m² small office as 'medium'. A prompt fix corrected offices but destabilised retail/school — so classification routes to Claude, while measure-selection and the citation gate use the cheaper DeepSeek. The gate made the call, not a preference.",
            },
            {
              icon: Building2,
              t: "Real NCC Section J, not a hardcoded pass",
              d: "Compliance encodes what the code actually regulates: lighting power density is a numeric J7D3 check (incl. the aggregate area-weighted method); plug loads are not regulated; glazing needs the J4 façade calc. Primary-verified against the live ABCB NCC 2022 text.",
            },
            {
              icon: CircleAlert,
              t: "A green check is not a correct value",
              d: "Seven 'green-but-wrong' bugs passed automated checks but were wrong numbers — caught only by domain knowledge (a meter double-count put EUI at 1498 vs 133; hourly GL14 limits applied to monthly bills). The reflex: validate against the live source, never hardcode.",
            },
          ].map((d) => (
            <div
              key={d.t}
              className="rounded-lg border border-surface-border bg-surface-raised p-4"
            >
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
        <a href="/retrofitgpt/demo" className="inline-flex items-center gap-1.5 text-accent hover:underline">
          <Activity className="h-4 w-4" /> Live demo
        </a>
        <a
          href={REPO}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1.5 text-zinc-300 hover:text-white"
        >
          <Github className="h-4 w-4" /> GitHub
        </a>
        <a href="#about-model" className="inline-flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200">
          <Leaf className="h-4 w-4" /> About the model
        </a>
        <span className="ml-auto text-xs text-zinc-600">
          ASHRAE GL14 · OWASP LLM06 · NCC 2022 Section J
        </span>
      </div>
    </div>
  );
}
