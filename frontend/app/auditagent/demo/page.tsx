"use client";

/**
 * /auditagent/demo — one-click live demo.
 *
 * Flow: pre-loaded synthetic contract → POST /review/sample (buyer perspective) →
 * render every finding with its EXACT cited span + char offsets, the accept/reject
 * verdict from the citation gate, and the hash-chained audit-trail badge. One
 * deliberate click (not auto-on-mount — that would let crawlers drain the rate limit).
 *
 * /review/sample is synchronous (no SSE), so the pipeline strip shows a single
 * "running" state during the fetch and resolves to done — no faked per-agent timing.
 */

import { useState } from "react";
import {
  ArrowRight, BadgeCheck, CheckCircle2, Clock, Info, Link2, Loader2, Play,
  ShieldAlert, XCircle,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_AUDITAGENT_API_BASE ?? "http://localhost:8002";

const PIPELINE = [
  { key: "extractor", emoji: "📑", label: "Extractor" },
  { key: "classifier", emoji: "🏷️", label: "Classifier" },
  { key: "risk", emoji: "⚖️", label: "Risk Analyzer" },
  { key: "reviewer", emoji: "✅", label: "Reviewer (gate)" },
] as const;

const CLAUSE_LABEL: Record<string, string> = {
  change_of_control: "Change of Control",
  uncapped_liability: "Uncapped Liability",
  auto_renewal: "Auto-renewal Notice",
  non_compete: "Non-Compete",
  termination_for_convenience: "Termination for Convenience",
};

type Citation = { quote: string; start_char: number; end_char: number; span_id?: string | null };
type Finding = {
  clause: string;
  status: string; // accepted | rejected_uncited | rejected_bad_citation | rejected_injection
  risk: string | null; // high | medium | info
  citation: Citation | null;
  retries: number;
};
type Memo = {
  perspective: string;
  n_findings_total: number;
  n_accepted: number;
  n_rejected: number;
  high_risk: string[];
  injection_flags: string[];
  hitl_status: string;
};
type ReviewResponse = {
  session_id: string;
  memo: Memo;
  findings: Finding[];
  audit_chain_valid: boolean;
};

type RunStatus = "idle" | "running" | "done" | "error";

const RISK_STYLE: Record<string, string> = {
  high: "border-red-500/40 bg-red-500/10 text-red-300",
  medium: "border-amber-500/40 bg-amber-500/10 text-amber-200",
  info: "border-surface-border bg-surface text-zinc-400",
};

function clauseName(key: string) {
  return CLAUSE_LABEL[key] ?? key.replace(/_/g, " ");
}

export default function AuditAgentDemo() {
  const [status, setStatus] = useState<RunStatus>("idle");
  const [data, setData] = useState<ReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function runDemo() {
    setStatus("running");
    setError(null);
    setData(null);
    try {
      const res = await fetch(`${API_BASE}/review/sample?perspective=buyer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!res.ok) {
        if (res.status === 401)
          throw new Error("The demo backend requires a token on this route. (Deploy note: keep /review/sample open behind the rate-limit for the public demo.)");
        if (res.status === 429)
          throw new Error("Rate limit reached — give it a minute and try again.");
        const detail = await res.json().catch(() => ({}));
        throw new Error((detail as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      setData((await res.json()) as ReviewResponse);
      setStatus("done");
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Could not reach the live agent. Is the backend deployed and NEXT_PUBLIC_AUDITAGENT_API_BASE set?",
      );
      setStatus("error");
    }
  }

  const nodeState = (i: number): "pending" | "active" | "done" => {
    if (status === "done") return "done";
    if (status === "running") return "active";
    return "pending";
  };

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight text-white">
        AuditAgent — live demo
      </h1>
      <p className="mt-1 text-sm text-zinc-500">
        A pre-loaded contract runs through all four agents. Every finding is shown with
        the exact text it cites — or the gate&apos;s reason for rejecting it.
      </p>

      {/* Pre-loaded contract card */}
      <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-sm">
        <span className="text-zinc-300">📄 Sample services agreement</span>
        <span className="text-zinc-500">5 target clause types</span>
        <span className="text-zinc-500">buyer perspective</span>
        <button
          onClick={runDemo}
          disabled={status === "running"}
          className="ml-auto inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-black transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {status === "running" ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Reviewing…
            </>
          ) : (
            <>
              <Play className="h-4 w-4" /> {status === "idle" ? "Run the review" : "Run again"}
            </>
          )}
        </button>
      </div>

      <p className="mt-3 flex items-start gap-2 px-1 text-xs leading-relaxed text-zinc-500">
        <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        A run takes a few seconds — live LLM calls (DeepSeek in production), not a cached
        result. The citation gate re-slices the raw contract to prove every quote.
      </p>

      {/* Pipeline strip */}
      <div className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {PIPELINE.map((n, i) => {
          const s = nodeState(i);
          return (
            <div
              key={n.key}
              className="flex items-center justify-between rounded-lg border border-surface-border bg-surface-raised px-3 py-2.5"
            >
              <span className="text-sm text-zinc-300">
                {n.emoji} <span className="hidden sm:inline">{n.label}</span>
              </span>
              {s === "active" && <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" />}
              {s === "done" && <CheckCircle2 className="h-3.5 w-3.5 text-accent" />}
              {s === "pending" && <span className="h-1.5 w-1.5 rounded-full bg-zinc-600" />}
            </div>
          );
        })}
      </div>

      {error && (
        <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Results */}
      {data && (
        <div className="mt-8">
          {/* Summary header */}
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-surface-border bg-surface-raised px-5 py-4">
            <h2 className="text-lg font-semibold text-white">Risk memo</h2>
            <span className="text-sm text-zinc-500">
              {data.memo.n_accepted} accepted · {data.memo.n_rejected} rejected by the gate
            </span>
            {data.audit_chain_valid && (
              <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent-soft px-2.5 py-0.5 text-[11px] font-medium text-accent">
                <Link2 className="h-3 w-3" /> Audit chain valid
              </span>
            )}
          </div>

          {data.memo.injection_flags.length > 0 && (
            <p className="mt-3 flex items-center gap-1.5 px-1 text-xs text-amber-300/90">
              <ShieldAlert className="h-3.5 w-3.5" /> Prompt-injection detected and refused
              ({data.memo.injection_flags.length})
            </p>
          )}

          {/* Findings */}
          <div className="mt-4 space-y-3">
            {data.findings.map((f, i) => {
              const accepted = f.status === "accepted";
              return (
                <div
                  key={`${f.clause}-${i}`}
                  className="rounded-xl border border-surface-border bg-surface-raised p-4"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-zinc-100">
                      {clauseName(f.clause)}
                    </span>
                    {f.risk && (
                      <span
                        className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${
                          RISK_STYLE[f.risk] ?? RISK_STYLE.info
                        }`}
                      >
                        {f.risk} risk
                      </span>
                    )}
                    <span
                      className={`ml-auto inline-flex items-center gap-1 text-xs font-medium ${
                        accepted ? "text-accent" : "text-amber-300"
                      }`}
                    >
                      {accepted ? (
                        <>
                          <CheckCircle2 className="h-3.5 w-3.5" /> cited &amp; accepted
                        </>
                      ) : (
                        <>
                          <XCircle className="h-3.5 w-3.5" /> {f.status.replace(/_/g, " ")}
                        </>
                      )}
                    </span>
                  </div>

                  {f.citation ? (
                    <blockquote className="mt-3 border-l-2 border-accent/50 bg-surface px-3 py-2 text-sm italic text-zinc-300">
                      &ldquo;{f.citation.quote}&rdquo;
                      <span className="mt-1 block not-italic text-[11px] text-zinc-600">
                        chars {f.citation.start_char}–{f.citation.end_char} · verified exact
                        slice of the source
                      </span>
                    </blockquote>
                  ) : (
                    <p className="mt-2 text-xs text-zinc-500">
                      No verifiable citation — the gate rejected this rather than emit an
                      unanchored finding.
                    </p>
                  )}
                </div>
              );
            })}
          </div>

          <a
            href="/auditagent"
            className="mt-6 inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
          >
            How this works <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      )}

      {status === "idle" && !data && (
        <p className="mt-6 flex items-start gap-2 px-1 text-xs text-zinc-600">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" /> The single-shot baseline misses
          clauses buried past its context window and can&apos;t anchor its quotes. The
          agent reads the whole document and proves every citation.
        </p>
      )}
    </div>
  );
}
