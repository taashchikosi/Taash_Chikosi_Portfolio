"use client";

/**
 * /retrofitgpt/demo — one-click live demo.
 *
 * Flow: pre-loaded Sydney small-office → POST /api/runs (demo_calibrate) → stream
 * the 5-agent trace over SSE → AUTO-APPROVE the HITL gate → fetch the business case
 * → render savings/payback/NPV/tCO₂e + the Reviewer verdict + the demo-calibration
 * badge. One deliberate click (not auto-on-mount — that would let crawlers/refreshes
 * drain the token budget).
 */

import { useRef, useState } from "react";
import {
  ArrowRight, BadgeCheck, CheckCircle2, Clock, Info, Loader2, Play, XCircle,
} from "lucide-react";
import { AGENT_LABELS, type AgentName } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8080";

const ORDER: AgentName[] = ["retriever", "modeler", "sim_runner", "analyzer", "reviewer"];

// Pre-loaded demo: Sydney small office, ~63.5 MWh/yr (→ EUI ~124 kWh/m²·yr).
const DEMO_UTILITY = {
  monthly_kwh: [6800, 6500, 5900, 4900, 4300, 4100, 4200, 4400, 4700, 5300, 5900, 6500],
  annual_cost_aud: 19050,
  tariff_type: "single rate",
};

type NodeState = "pending" | "active" | "done" | "failed";
type RunStatus = "idle" | "running" | "done" | "error";

type Result = {
  building: { type: string; floor_area_m2: number; ncc_climate_zone: number; baseline_eui_kwh_m2_yr: number };
  recommended: {
    scenario: string; energy_savings_pct: number; cost_savings_aud_per_year: number;
    retrofit_cost_aud: number; simple_payback_years: number; npv_aud: number;
    carbon_reduction_tco2e_per_year: number;
  };
  review: { approved: boolean; nmbe_pct: number | null; cvrmse_pct: number | null };
  sources: { tariff: string; emission_factor: string };
  demo_calibration: boolean;
};

const fmt = (n: number) => n.toLocaleString("en-AU", { maximumFractionDigits: 0 });

export default function DemoPage() {
  const [status, setStatus] = useState<RunStatus>("idle");
  const [nodes, setNodes] = useState<Record<AgentName, NodeState>>(
    () => Object.fromEntries(ORDER.map((a) => [a, "pending"])) as Record<AgentName, NodeState>,
  );
  const [calibrated, setCalibrated] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const setNode = (a: AgentName, s: NodeState) =>
    setNodes((prev) => ({ ...prev, [a]: s }));

  async function runDemo() {
    setStatus("running");
    setError(null);
    setResult(null);
    setCalibrated(false);
    setNodes(Object.fromEntries(ORDER.map((a) => [a, "pending"])) as Record<AgentName, NodeState>);

    let runId: string;
    try {
      const res = await fetch(`${API_BASE}/api/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ utility: DEMO_UTILITY, demo_calibrate: true }),
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        throw new Error(detail.detail ?? `HTTP ${res.status}`);
      }
      runId = (await res.json()).run_id;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the run.");
      setStatus("error");
      return;
    }

    const es = new EventSource(`${API_BASE}/api/runs/${runId}/events`);
    esRef.current = es;

    es.onmessage = async (msg) => {
      const ev = JSON.parse(msg.data) as { agent: string; status: string };
      const { agent, status: st } = ev;

      if (agent === "calibrate_demo") setCalibrated(true);

      if (ORDER.includes(agent as AgentName)) {
        const a = agent as AgentName;
        if (st === "started" || st === "awaiting_approval" || st === "progress") setNode(a, "active");
        else if (st === "completed") setNode(a, "done");
        else if (st === "failed") setNode(a, "failed");
      }

      // Auto-approve the human-in-the-loop gate (kept visible, advanced for the demo).
      // The Modeler's work is finished at the gate, so mark it done rather than
      // leaving it spinning while the rest of the pipeline runs.
      if (agent === "modeler" && st === "awaiting_approval") {
        setNode("modeler", "done");
        await fetch(`${API_BASE}/api/runs/${runId}/approve`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action: "approve" }),
        }).catch(() => {});
      }

      if (st === "done" || st === "failed" || st === "human_review") {
        es.close();
        if (st === "failed") {
          setNode("reviewer", "failed");
          setError("A pipeline stage failed — check the backend logs.");
          setStatus("error");
          return;
        }
        setNode("reviewer", "done");
        try {
          const r = await fetch(`${API_BASE}/api/runs/${runId}/result`);
          setResult(await r.json());
        } catch {
          /* result fetch optional */
        }
        setStatus("done");
      }
    };

    es.onerror = () => {
      es.close();
      if (status !== "done") {
        setError("Lost connection to the live agent. Is the backend reachable?");
        setStatus("error");
      }
    };
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight text-white">
        RetrofitGPT — live demo
      </h1>
      <p className="mt-1 text-sm text-zinc-500">
        A pre-loaded building runs through all five agents and real EnergyPlus. One click.
      </p>

      {/* Pre-loaded building card */}
      <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-surface-border bg-surface-raised px-5 py-4 text-sm">
        <span className="text-zinc-300">🏢 DOE Small Office</span>
        <span className="text-zinc-500">Sydney · NCC zone 5</span>
        <span className="text-zinc-500">511 m²</span>
        <span className="text-zinc-500">12 months of bills</span>
        <button
          onClick={runDemo}
          disabled={status === "running"}
          className="ml-auto inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-black transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {status === "running" ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Running…
            </>
          ) : (
            <>
              <Play className="h-4 w-4" /> {status === "idle" ? "Run the demo" : "Run again"}
            </>
          )}
        </button>
      </div>

      {/* What to expect — set timing expectations before the click. */}
      <p className="mt-3 flex items-start gap-2 px-1 text-xs leading-relaxed text-zinc-500">
        <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        A full run takes <span className="text-zinc-400">~30–50s</span> — it runs real
        EnergyPlus simulations (baseline + retrofit scenarios) plus live LLM calls, not a
        cached result. That&apos;s genuine computation; it&apos;d be that slow on the 2nd
        and 100th run too. The wait is the physics, not a cold start — the trace below
        shows live progress.
      </p>

      {/* Agent trace */}
      <div className="mt-6 space-y-2">
        {ORDER.map((a) => {
          const s = nodes[a];
          return (
            <div
              key={a}
              className="flex items-center justify-between rounded-lg border border-surface-border bg-surface-raised px-4 py-3"
            >
              <span className="text-sm text-zinc-300">
                {AGENT_LABELS[a].emoji} {AGENT_LABELS[a].label}
              </span>
              <span className="inline-flex items-center gap-1.5 text-xs">
                {s === "active" && (
                  <span className="inline-flex items-center gap-1.5 text-accent">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" /> running
                  </span>
                )}
                {s === "done" && (
                  <span className="inline-flex items-center gap-1.5 text-accent">
                    <CheckCircle2 className="h-3.5 w-3.5" /> done
                  </span>
                )}
                {s === "failed" && (
                  <span className="inline-flex items-center gap-1.5 text-red-400">
                    <XCircle className="h-3.5 w-3.5" /> failed
                  </span>
                )}
                {s === "pending" && <span className="text-zinc-600">idle</span>}
              </span>
            </div>
          );
        })}
        {calibrated && (
          <p className="flex items-center gap-1.5 px-1 text-xs text-amber-300/80">
            <Info className="h-3.5 w-3.5" /> HITL gate auto-approved · demo bills
            synthesised from the baseline (disclosed)
          </p>
        )}
      </div>

      {error && (
        <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/5 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Business case result */}
      {result && (
        <div className="mt-8 rounded-xl border border-surface-border bg-surface-raised p-6">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-white">Business case</h2>
            {result.review.approved ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-accent/40 bg-accent-soft px-2.5 py-0.5 text-xs font-medium text-accent">
                <CheckCircle2 className="h-3 w-3" /> Reviewer approved
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-xs font-medium text-amber-200">
                approval withheld
              </span>
            )}
            {result.demo_calibration && (
              <a
                href="/retrofitgpt#about-model"
                className="ml-auto inline-flex items-center gap-1 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 text-[11px] font-medium text-amber-200 hover:bg-amber-500/20"
              >
                <BadgeCheck className="h-3 w-3" /> Demo calibration
              </a>
            )}
          </div>

          <p className="mt-3 text-sm text-zinc-400">
            Recommended: <span className="text-zinc-100">{result.recommended.scenario}</span>{" "}
            on a {result.building.type} ({result.building.baseline_eui_kwh_m2_yr} kWh/m²·yr baseline)
          </p>

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              { k: `${result.recommended.energy_savings_pct}%`, v: "energy saved" },
              { k: `${result.recommended.simple_payback_years} yr`, v: "payback" },
              { k: `$${fmt(result.recommended.npv_aud)}`, v: "NPV (25 yr)" },
              { k: `${result.recommended.carbon_reduction_tco2e_per_year} t`, v: "CO₂e / yr" },
            ].map((m) => (
              <div key={m.v} className="rounded-lg border border-surface-border bg-surface p-3">
                <p className="text-lg font-semibold text-white">{m.k}</p>
                <p className="text-xs text-zinc-500">{m.v}</p>
              </div>
            ))}
          </div>

          <p className="mt-4 text-xs text-zinc-600">
            Calibration: NMBE {result.review.nmbe_pct ?? "—"}% · CV-RMSE{" "}
            {result.review.cvrmse_pct ?? "—"}% (ASHRAE GL14) · sources:{" "}
            {result.sources.tariff}, {result.sources.emission_factor}
          </p>

          <a
            href="/retrofitgpt"
            className="mt-5 inline-flex items-center gap-1.5 text-sm text-accent hover:underline"
          >
            How this works <ArrowRight className="h-4 w-4" />
          </a>
        </div>
      )}
    </div>
  );
}
