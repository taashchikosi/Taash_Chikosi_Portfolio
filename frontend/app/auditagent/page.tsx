"use client";

/**
 * /auditagent — recruiter-facing case study: hero + live status → problem →
 * architecture → eval evidence → technical decisions (ADR) → links. Includes the
 * mandatory "About the numbers" honesty panel so the headline is read correctly:
 * the citation gate is a precision/integrity mechanism (+0.29 faithfulness), NOT
 * "agent beats single-shot", and detection (L1, CUAD-scored) ≠ severity (L2, rules).
 *
 * Live status dot hits NEXT_PUBLIC_AUDITAGENT_API_BASE/health and only goes green
 * when citation_anchoring === "ok" (the M1 invariant self-check), not just "up".
 */

import { useEffect, useState } from "react";
import {
  Activity, ArrowRight, BadgeCheck, Boxes, CircleAlert, Cpu, Database,
  FileSearch, FlaskConical, GitBranch, Github, Info, Quote, ScrollText,
  ShieldCheck, Tags,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_AUDITAGENT_API_BASE ?? "http://localhost:8002";
const REPO = "https://github.com/taashchikosi/auditagent";

type Health = {
  status: string;
  citation_anchoring?: string;
  milestone?: string;
  n_spans?: number;
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
  // Green only when the process is up AND the citation-anchoring self-check passes.
  const ok = !failed && health?.status === "ok" && health?.citation_anchoring === "ok";
  const label = failed
    ? "offline"
    : health
    ? ok
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
  { icon: FileSearch, name: "Extractor", note: "offset-exact spans", model: "deterministic" },
  { icon: Tags, name: "Classifier", note: "locate 5 clause types", model: "DeepSeek" },
  { icon: Database, name: "Risk Analyzer", note: "severity (L2 rules)", model: "deterministic" },
  { icon: ShieldCheck, name: "Reviewer", note: "citation gate", model: "Claude" },
];

const METRICS = [
  { k: "0.912", v: "high-risk recall", sub: "B2 agent, CUAD n=102" },
  { k: "+0.29", v: "citation faithfulness", sub: "0.555 → 0.849 (anchorer)" },
  { k: "0.649", v: "macro-F1", sub: "vs RoBERTa P@80R 0.482" },
  { k: "73", v: "tests green", sub: "ruff clean · CI-gated" },
];

// Per-clause F1 (B2, DeepSeek n=102) — straight from eval_deepseek_full.md.
const PER_CLAUSE = [
  { c: "Termination for convenience", f1: "0.78", cite: "1.00" },
  { c: "Non-compete", f1: "0.77", cite: "0.91" },
  { c: "Auto-renewal notice", f1: "0.60", cite: "0.87" },
  { c: "Change of control", f1: "0.58", cite: "0.67" },
  { c: "Uncapped liability", f1: "0.51", cite: "0.80" },
];

export default function AuditAgentCaseStudy() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-14">
      {/* ── Hero ─────────────────────────────────────────────────────── */}
      <div className="animate-rise flex items-center gap-3">
        <StatusDot />
        <span className="text-xs text-zinc-600">AuditAgent · live agent</span>
      </div>
      <h1
        className="animate-rise mt-5 text-4xl font-semibold leading-[1.1] tracking-tight text-white"
        style={{ animationDelay: "80ms" }}
      >
        A contract-review agent that flags risky clauses and{" "}
        <span className="text-accent">cites the exact source text</span> — or rejects
        the finding.
      </h1>
      <p
        className="animate-rise mt-4 max-w-2xl text-base leading-relaxed text-zinc-400"
        style={{ animationDelay: "160ms" }}
      >
        In 2025 Deloitte Australia partially refunded the federal government after an
        AI report contained fabricated citations. AuditAgent makes that failure mode
        impossible by construction: <span className="text-zinc-200">every accepted
        finding re-slices the raw contract exactly</span>, or the citation gate throws
        it out. Measured against <span className="text-zinc-200">CUAD</span> — 510 real
        contracts, 13,000+ lawyer labels.
      </p>
      <div
        className="animate-rise mt-7 flex flex-wrap gap-3"
        style={{ animationDelay: "240ms" }}
      >
        <a
          href="/auditagent/demo"
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
            <span className="text-zinc-100">The headline is the anchorer, not a horse
            race.</span> The win is citation faithfulness <span className="text-zinc-100">
            +0.29</span> (replicated on Claude at +0.33) — same detections, citations
            that land on the right text. The gate is a{" "}
            <span className="text-zinc-100">precision / integrity</span> mechanism, not a
            claim that &ldquo;the agent beats single-shot&rdquo;.
          </li>
          <li>
            <span className="text-zinc-100">Detection ≠ severity.</span> CUAD scores
            detection (L1 — did it find the clause?). Risk severity (L2) is a
            deterministic rule layer, never presented as measured accuracy.
          </li>
          <li>
            <span className="text-zinc-100">CUAD is a US corpus.</span> The architecture
            is corpus-agnostic and deployable on Australian contracts; clause risk is
            jurisdiction-neutral. The demo contract is synthetic.
          </li>
          <li>
            <span className="text-zinc-100">The honest limit:</span> 14 accepted findings
            re-slice the contract exactly but miss the gold clause region (right answer,
            wrong location). The gate checks slice-integrity, not gold-overlap — so it
            can&apos;t catch these. That&apos;s the next quality target.
          </li>
        </ul>
      </div>

      {/* ── Problem ──────────────────────────────────────────────────── */}
      <Section eyebrow="The problem" title="LLMs are &ldquo;lazy&rdquo; — and a missed clause is the dangerous error">
        <p>
          Contract review is the highest-volume agentic use case at the Big 4 (Deloitte
          Zora, KPMG Clara). The 2025 <span className="text-zinc-200">ContractEval</span>{" "}
          benchmark ran 19 LLMs on CUAD and found they falsely answer &ldquo;no related
          clause&rdquo; when one is present. In review, a{" "}
          <span className="text-zinc-200">false negative is the error that sinks the
          deal</span> — you miss the indemnity, the change-of-control trigger, the
          uncapped liability. And every finding a client acts on has to be traceable to
          the words in the contract, not a plausible paraphrase.
        </p>
      </Section>

      {/* ── Architecture ─────────────────────────────────────────────── */}
      <Section eyebrow="Architecture" title="Four agents, one non-negotiable invariant">
        <p className="mb-5">
          The pipeline runs on <span className="text-zinc-200">LangGraph</span>. Its
          foundation is a single invariant that everything else builds on:
        </p>
        <pre className="mb-5 overflow-x-auto rounded-lg border border-surface-border bg-surface p-3 text-xs text-zinc-300">
          <code>raw_text[span.start_char : span.end_char] == span.text   # always, exactly</code>
        </pre>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {AGENTS.map((a, i) => (
            <div
              key={a.name}
              className="flow-card relative rounded-lg border border-surface-border bg-surface-raised p-3"
              style={{
                animation: "flowPulse 3.4s ease-in-out infinite",
                animationDelay: `${i * 0.45}s`,
              }}
            >
              <a.icon className="h-5 w-5 text-accent" />
              <p className="mt-2 text-sm font-medium text-zinc-200">{a.name}</p>
              <p className="mt-0.5 text-xs text-zinc-500">{a.note}</p>
              <p className="mt-2 text-[10px] uppercase tracking-wide text-zinc-600">
                {a.model}
              </p>
              {i < AGENTS.length - 1 && (
                <ArrowRight
                  className="flow-arrow absolute -right-2.5 top-1/2 hidden h-4 w-4 -translate-y-1/2 text-accent sm:block"
                  style={{
                    animation: "flowArrow 3.4s ease-in-out infinite",
                    animationDelay: `${i * 0.45 + 0.22}s`,
                  }}
                />
              )}
            </div>
          ))}
        </div>
        <p className="mt-4 flex items-center gap-2 text-xs text-zinc-500">
          <GitBranch className="h-3.5 w-3.5" /> The Reviewer is the citation gate: an
          uncited or mis-cited finding is re-run once, then rejected. A hash-chained,
          tamper-evident audit log records every step; an in-contract prompt-injection is
          flagged and refused (OWASP LLM01); a human Approve/Escalate gate can pause the
          run (resumable LangGraph interrupt).
        </p>
      </Section>

      {/* ── Eval evidence ────────────────────────────────────────────── */}
      <Section eyebrow="Evidence" title="Measured on real lawyer labels, reproducible at temp 0">
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
            DeepSeek V4 Flash, full CUAD test split (n=102), temperature 0, 2×
            reproducibility-checked — at <span className="text-zinc-200">$0.0035 and 3.4 s
            per contract</span>, measured from token usage, not guessed. A baseline ladder
            (B0 published RoBERTa → B1 single-shot → B2 agent) makes the comparison fair;
            the offline deterministic run validates the measurement machinery in CI
            without an API key.
          </span>
        </p>

        {/* Per-clause table */}
        <div className="mt-6 overflow-hidden rounded-lg border border-surface-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Clause (v1 — 5 of CUAD&apos;s 41)</th>
                <th className="px-4 py-2.5 text-right font-medium">F1</th>
                <th className="px-4 py-2.5 text-right font-medium">Cite faith.</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-border">
              {PER_CLAUSE.map((r) => (
                <tr key={r.c} className="bg-surface-raised">
                  <td className="px-4 py-2.5 text-zinc-300">{r.c}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-zinc-200">{r.f1}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-zinc-200">{r.cite}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* ── Technical decisions / ADR ────────────────────────────────── */}
      <Section eyebrow="Technical decisions" title="What I chose, and why">
        <div className="space-y-3">
          {[
            {
              icon: Quote,
              t: "Fuzzy to locate, exact to cite",
              d: "A naive exact-match anchorer scored 0.555 faithfulness because models paraphrase. The fix: fuzzy matching only LOCATES the span; the stored citation is always a literal raw-text slice that must round-trip. Same detections, faithfulness 0.555 → 0.849. Weakening that round-trip would defeat the whole project, so it stays strict.",
            },
            {
              icon: CircleAlert,
              t: "A precision fix that held recall",
              d: "uncapped_liability was over-firing (precision 0.20). Tightening the clause definition lifted precision to 0.39 with no recall loss — the dangerous false-negatives stayed caught. The change lives in clause definitions + a regression test, not a prompt tweak.",
            },
            {
              icon: Cpu,
              t: "Cheap model in prod, strong model as the twin",
              d: "DeepSeek V4 Flash runs production (cost); Claude Sonnet 4.6 is the benchmark twin on the identical pipeline — swap the key, not the code. A model's published numbers belong only to that model. DeepSeek is non-deterministic at temp 0 on the single hardest clause; that's documented, not hidden.",
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
        <a href="/auditagent/demo" className="inline-flex items-center gap-1.5 text-accent hover:underline">
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
        <a href="#about-numbers" className="inline-flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200">
          <ScrollText className="h-4 w-4" /> About the numbers
        </a>
        <span className="ml-auto inline-flex items-center gap-1.5 text-xs text-zinc-600">
          <Boxes className="h-3.5 w-3.5" /> CUAD · ContractEval · OWASP LLM01
        </span>
      </div>
    </div>
  );
}
