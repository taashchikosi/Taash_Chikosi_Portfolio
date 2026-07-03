"use client";

/**
 * Agentic Energy Modeller — live demo. Pattern A (SSE).
 *
 *   1. POST /api/runs  {utility, validate_realism, idf_path, epw_path, city, model_inputs}
 *                                                              → { run_id }
 *   2. EventSource GET /api/runs/{id}/events  (SSE)            → live 5-agent trace
 *        - on  modeler/awaiting_approval  → the run BLOCKS until the human PICKS ONE
 *          proposed measure and approves → POST /api/runs/{id}/approve
 *          {action:"approve", measure:"<key>"}. The backend then simulates baseline +
 *          that one measure (2 EnergyPlus sims ≈ ~50s — the demo time-saver). The gate
 *          is API-enforced human-in-the-loop, not a prompt; nothing auto-advances.
 *   3. GET  /api/runs/{id}/result                              → final business case
 *
 * The 🥇 wow: the LLM never authors a number. The trace shows EnergyPlus 24.2
 * running per scenario (~19s each) and the Reviewer's CBD-cohort realism gate —
 * the simulated baseline EUI must land inside the real disclosed-office cohort's
 * p25–p75 for that city + size, else the Reviewer withholds and routes the demoer
 * back to the inputs. Every figure in the result comes from physics / deterministic
 * finance behind MCP.
 *
 * Reachability note (verified 2026-06-22): the deployed site is HTTPS; the valid
 * TLS surface is the sslip.io host on 443 (port :8080 is plain HTTP and would be
 * blocked as mixed content). This demo is live-backend only — there is NO recorded
 * fallback. If the live stream can't be reached, the widget shows an honest error
 * (cold start / lost connection); it never fabricates a run.
 *
 * Presentation: this renders ONLY the demo widget — no <section>, no heading.
 * The CasePage "Live Demo" panel already provides the heading + the honest note
 * below it. Styled with the mockup tokens/classes (.btn.pri, .demo-embed, …) and
 * inline styles using the CSS vars (var(--acc), var(--s1), var(--line), …).
 */

import { Fragment, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BadgeCheck,
  Cpu,
  Loader2,
  CheckCircle2,
  XCircle,
  Circle,
  ShieldCheck,
  TriangleAlert,
  Leaf,
  Building2,
  MapPin,
  FileCode2,
  ExternalLink,
  Download,
  Activity,
} from "lucide-react";
import {
  CITIES,
  COHORTS,
  MODEL_INPUTS,
  buildingDef,
  cityDef,
  cohortFor,
  pathsFor,
  type BuildingKey,
  type CityKey,
} from "@/lib/energy-modeller-catalog";
import { fmtAud, FX_NOTE } from "@/lib/fx";

/* ── Types mirroring the real captured SSE + result shapes ────────────────── */
type AgentKey = "retriever" | "modeler" | "sim_runner" | "analyzer" | "reviewer";
type NodeState = "pending" | "active" | "done" | "failed";

type SimRow = {
  scenario: string;
  status: string; // running | success | failed
  eui?: number;
  annual_kwh?: number;
  runtime_s?: number;
};

type ScenarioResult = {
  scenario: string;
  energy_savings_pct: number;
  simple_payback_years: number;
  npv_aud: number;
  carbon_reduction_tco2e_per_year: number;
};

type RunResult = {
  building: {
    type: string;
    floor_area_m2: number;
    ncc_climate_zone: number;
    baseline_eui_kwh_m2_yr: number;
  };
  recommended: ScenarioResult & {
    cost_savings_aud_per_year?: number;
    retrofit_cost_aud?: number;
  };
  scenarios: ScenarioResult[];
  review: {
    approved: boolean;
    realistic?: boolean;
    within_cohort: boolean | null;
    cohort_validated: boolean;
    baseline_eui: number | null;
    cohort_p25: number | null;
    cohort_p75: number | null;
    cohort_median: number | null;
    cohort_n: number | null;
    floor_area_realistic: boolean;
    route_to: string;
  };
  sources: { tariff: string; emission_factor: string };
  cohort_validated?: boolean;
};

type Status = "idle" | "running" | "awaiting" | "done" | "error";

// A measure the Modeler proposes at the HITL gate; the demoer picks one to simulate.
type MeasureCandidate = { key: string; description: string; est_cost_aud: number };

type AgentDef = {
  key: AgentKey;
  emblem: string;
  name: string;
  role: string;
  kind: "llm" | "det";
  tag: string;
  purpose: string;
  does: string[]; // short bullets
  doesnt: string[]; // short bullets
  live: string; // shown while the agent is active
  done: string; // shown once the agent completes
};

const AGENTS: AgentDef[] = [
  {
    key: "retriever", emblem: "🔍", name: "Retriever", role: "Reads the inputs",
    kind: "llm", tag: "Claude Sonnet 4.6 · classifies (no numbers)",
    purpose: "Works out what building this is.",
    does: ["Reads the building's model file (IDF) and data, and turns them into one tidy summary the rest of the agents can use."],
    doesnt: ["Invent any number"],
    live: "Reading inputs → classifying type + HVAC",
    done: "classified type + HVAC",
  },
  {
    key: "modeler", emblem: "🔧", name: "Modeler", role: "Picks what to test",
    kind: "llm", tag: "DeepSeek V4 Flash · selects (no numbers)",
    purpose: "Proposes the measures worth testing — you pick one to simulate.",
    does: ["Proposes efficiency measures (LED · efficient equipment · double glazing); you choose one at the gate, and it packages baseline + your pick for the → Sim Runner."],
    doesnt: ["Run physics or compute savings", "Author any number"],
    live: "Proposing LED · efficient equipment · double glazing",
    done: "measures proposed — pick one",
  },
  {
    key: "sim_runner", emblem: "⚙️", name: "Sim Runner", role: "Runs the physics",
    kind: "det", tag: "no LLM · pure physics",
    purpose: "Runs the real physics — baseline + your chosen measure.",
    does: ["Takes the building inputs and your chosen upgrade, and runs them through the real EnergyPlus physics engine — once for the building as-is, then once with the measure you picked (2 real simulations)."],
    doesnt: ["Use an LLM or decide anything", "Touch the original IDF (works on clones)"],
    live: "Driving EnergyPlus 24.2 — per scenario",
    done: "baseline + measure simulated (table below)",
  },
  {
    key: "analyzer", emblem: "📊", name: "Analyzer", role: "Does the math",
    kind: "det", tag: "no LLM · pure math",
    purpose: "Turns sim numbers into comparable figures.",
    does: ["Takes energy results and turns them into plain answers: how much energy and carbon each upgrade saves, using fixed formulae."],
    doesnt: ["Use an LLM or run a sim", "Produce anything that doesn't trace to a sim output"],
    live: "Computing savings · payback · NPV · carbon",
    done: "computed the comparable figures",
  },
  {
    key: "reviewer", emblem: "🛡️", name: "Reviewer", role: "The gate",
    kind: "det", tag: "no LLM · pure math",
    purpose: "Refuses to ship anything it can't defend.",
    does: ["Checks the baseline lands in the real CBD cohort's p25–p75", "Outside → withholds + routes back to inputs"],
    doesnt: ["Tune the model to hit a target", "Pass a number it can't trace — it withholds"],
    live: "Checking baseline vs the real CBD cohort",
    done: "verdict returned (below)",
  },
];

// Display metadata for the efficiency measures, keyed by the backend measure key.
// The Modeler PROPOSES these at the gate; the demoer picks ONE to simulate (keeps the
// live run to 2 EnergyPlus sims). Backend candidate list drives what's shown — this is
// just the icon/label lookup.
const MEASURE_META: Record<string, { icon: string; name: string }> = {
  led_lighting: { icon: "💡", name: "LED lighting" },
  efficient_equipment: { icon: "🔌", name: "Efficient equipment" },
  double_glazing: { icon: "🪟", name: "Double glazing" },
};
const measureMeta = (key: string) =>
  MEASURE_META[key] ?? { icon: "🔧", name: key.replace(/_/g, " ") };

// Pre-loaded reference-building inputs (demo payload shape). idf_path/epw_path are
// merged in from the Step-1 selection at submit time (see runDemo → pathsFor), and
// the run carries the `validate_realism` flag (the cohort gate). NOTE: this is a
// pre-loaded building, not user-uploaded data — never describe it as "bills".
const PAYLOAD = {
  utility: {
    monthly_kwh: [5800, 5600, 5200, 4800, 4400, 4200, 4300, 4500, 4900, 5100, 5400, 5700],
    annual_cost_aud: 19050,
    tariff_type: "single rate",
  },
};

const ACC = "var(--acc)";

export function Demo({
  apiBase,
  accent = ACC,
}: {
  apiBase: string;
  accent?: string;
}) {
  // Office scope is locked to Medium (the only size with a real disclosed CBD
  // cohort); the demoer picks the city whose weather it runs against.
  const [building] = useState<BuildingKey>("medium_office");
  const [city, setCity] = useState<CityKey>("sydney");

  // Step 1b: the nine editable model inputs. Each starts at its calibrated set-point
  // (def); only inputs moved OFF def are sent, so an untouched run is a true no-op
  // and the baseline lands inside the CBD cohort → the Reviewer approves. Move an
  // energy driver far enough and the real EnergyPlus baseline EUI leaves the cohort
  // p25–p75 → the Reviewer genuinely withholds and routes back to the inputs.
  const [inputs, setInputs] = useState<Record<string, number>>(
    () => Object.fromEntries(MODEL_INPUTS.map((m) => [m.field, m.def])),
  );
  // Only the inputs the user actually moved off their calibrated default get sent.
  function dirtyModelInputs(): Record<string, number> {
    const out: Record<string, number> = {};
    for (const m of MODEL_INPUTS) {
      if (Math.abs((inputs[m.field] ?? m.def) - m.def) > 1e-9) out[m.field] = inputs[m.field];
    }
    return out;
  }
  const dirtyCount = Object.keys(dirtyModelInputs()).length;

  const [status, setStatus] = useState<Status>("idle");
  const [warming, setWarming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nodes, setNodes] = useState<Record<AgentKey, NodeState>>({
    retriever: "pending",
    modeler: "pending",
    sim_runner: "pending",
    analyzer: "pending",
    reviewer: "pending",
  });
  const [sims, setSims] = useState<SimRow[]>([]);
  const [approved, setApproved] = useState(false);
  const [result, setResult] = useState<RunResult | null>(null);
  // HITL measure choice: the Modeler proposes candidates (from the awaiting_approval
  // event); the demoer picks ONE to simulate. `chosenMeasure` is the selected key.
  const [candidates, setCandidates] = useState<MeasureCandidate[]>([]);
  const [chosenMeasure, setChosenMeasure] = useState<string | null>(null);
  // Per-run telemetry: latency is measured client-side (real wall-clock); tokens AND
  // cost are the real deltas of the backend's /health counters across this run (cost
  // is priced per-provider server-side, not a flat blend). Null until the run lands.
  const [telemetry, setTelemetry] = useState<{ latencyMs: number; tokens: number | null; costUsd: number | null } | null>(null);

  const esRef = useRef<EventSource | null>(null);
  const approvedRef = useRef(false);
  const runIdRef = useRef<string | null>(null);
  const runStartRef = useRef<number | null>(null);    // wall-clock start of this run
  const startTokensRef = useRef<number | null>(null);  // /health token counter at start
  const startCostRef = useRef<number | null>(null);    // /health USD cost counter at start
  const gateShownAtRef = useRef<number | null>(null);  // when the approval gate appeared
  const gatePauseMsRef = useRef<number>(0);            // how long the human took to approve
  // SSE robustness: did we ever receive a real event (cold-start vs mid-run drop),
  // and a grace timer so a transient EventSource reconnect isn't treated as fatal.
  const gotDataRef = useRef(false);
  const failTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sim-runner progress (the long pole — ~20s per EnergyPlus scenario) + the
  // staggered finish so the instant Analyzer/Reviewer steps read as distinct.
  const [simStartedAt, setSimStartedAt] = useState<number | null>(null);
  const [scenarioStartedAt, setScenarioStartedAt] = useState<number | null>(null);
  const [scenarioName, setScenarioName] = useState<string | null>(null);
  const finishingRef = useRef(false);
  const finishTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Clean up the SSE stream + any pending finish-sequence timers on unmount.
  useEffect(() => {
    const timers = finishTimers.current;
    return () => {
      esRef.current?.close();
      if (failTimerRef.current) clearTimeout(failTimerRef.current);
      timers.forEach(clearTimeout);
    };
  }, []);

  function reset() {
    setError(null);
    setSims([]);
    setApproved(false);
    setResult(null);
    setCandidates([]);
    setChosenMeasure(null);
    setTelemetry(null);
    runStartRef.current = null;
    startTokensRef.current = null;
    gateShownAtRef.current = null;
    gatePauseMsRef.current = 0;
    approvedRef.current = false;
    runIdRef.current = null;
    gotDataRef.current = false;
    if (failTimerRef.current) {
      clearTimeout(failTimerRef.current);
      failTimerRef.current = null;
    }
    setWarming(false);
    finishingRef.current = false;
    finishTimers.current.forEach(clearTimeout);
    finishTimers.current = [];
    setSimStartedAt(null);
    setScenarioStartedAt(null);
    setScenarioName(null);
    setNodes({
      retriever: "pending",
      modeler: "pending",
      sim_runner: "pending",
      analyzer: "pending",
      reviewer: "pending",
    });
  }

  function setNode(key: AgentKey, state: NodeState) {
    setNodes((n) => ({ ...n, [key]: state }));
  }

  // Merge a sim_runner progress event into the per-scenario table.
  function upsertSim(row: SimRow) {
    setSims((prev) => {
      const i = prev.findIndex((r) => r.scenario === row.scenario);
      if (i === -1) return [...prev, row];
      const next = prev.slice();
      next[i] = { ...next[i], ...row };
      return next;
    });
  }

  async function fetchResult(runId: string) {
    try {
      const r = await fetch(`${apiBase}/api/runs/${runId}/result`);
      if (r.ok) setResult((await r.json()) as RunResult);
    } catch {
      /* result is best-effort; the trace already told the story */
    }
  }

  // Real per-run LLM tokens = the delta of the backend's rolling 24h token counter
  // across the run (single-presenter demo → this run's tokens). Best-effort; null if
  // /health is unreachable or the counter didn't move.
  async function readHealthCounters(): Promise<{ tokens: number | null; cost: number | null }> {
    try {
      const r = await fetch(`${apiBase}/health`, { cache: "no-store" });
      if (!r.ok) return { tokens: null, cost: null };
      const j = await r.json();
      const t = j?.token_budget?.used_last_24h;
      const c = j?.token_budget?.cost_used_last_24h;
      return {
        tokens: typeof t === "number" ? t : null,
        cost: typeof c === "number" ? c : null,
      };
    } catch {
      return { tokens: null, cost: null };
    }
  }

  // Capture latency (real wall-clock) + tokens + cost (real counter deltas) at landing.
  async function captureTelemetry() {
    // System latency = total wall-clock MINUS the human-paced approval pause.
    const latencyMs = runStartRef.current
      ? Date.now() - runStartRef.current - gatePauseMsRef.current
      : 0;
    const end = await readHealthCounters();
    const sTok = startTokensRef.current;
    const sCost = startCostRef.current;
    const tokens =
      sTok != null && end.tokens != null && end.tokens >= sTok ? end.tokens - sTok : null;
    const costUsd =
      sCost != null && end.cost != null && end.cost >= sCost
        ? Math.round((end.cost - sCost) * 1e6) / 1e6
        : null;
    setTelemetry({ latencyMs, tokens, costUsd });
  }

  // The Analyzer (deterministic math) and Reviewer (range-check) finish in the same
  // sub-second instant the sim ends, so the raw events would flip all three steps at
  // once. Reveal them as distinct, legible steps — the work is real and sequential,
  // just fast — then release the result.
  function runFinishSequence(ok: boolean, runId: string) {
    finishingRef.current = true;
    setNode("sim_runner", "done");
    setNode("analyzer", "active");
    const push = (fn: () => void, ms: number) =>
      finishTimers.current.push(setTimeout(fn, ms));
    push(() => setNode("analyzer", "done"), 750);
    push(() => setNode("reviewer", "active"), 1050);
    push(() => setNode("reviewer", ok ? "done" : "failed"), 1850);
    push(() => {
      setStatus("done");
      void fetchResult(runId);
      void captureTelemetry();
    }, 1950);
  }

  async function approveRun(runId: string, measure: string | null) {
    try {
      await fetch(`${apiBase}/api/runs/${runId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // The demoer's single measure choice — the backend simulates baseline + this one.
        body: JSON.stringify({ action: "approve", ...(measure ? { measure } : {}) }),
      });
      setApproved(true);
    } catch {
      /* the SSE stream will surface a failure if approval didn't land */
    }
  }

  // CLICK-ONLY human-in-the-loop: the gate UI calls this when the demoer approves the
  // Modeler's plan WITH a chosen measure. Nothing auto-advances — the pipeline blocks
  // server-side at `awaiting_approval` until this POST lands. Requires a measure pick.
  function onApprove() {
    const id = runIdRef.current;
    if (!id || approvedRef.current || !chosenMeasure) return;
    approvedRef.current = true;
    // Record how long the human took at the gate so it can be excluded from latency
    // (latency should be the system's compute time, not the operator's think time).
    if (gateShownAtRef.current) gatePauseMsRef.current = Date.now() - gateShownAtRef.current;
    setStatus("running");
    void approveRun(id, chosenMeasure);
  }

  // Cold containers (a sleeping VPS) can take ~20–30s on the first hit. Ping /health
  // with retries so a cold start becomes a short, reassured wait — never a failed demo.
  async function warmUpBackend(): Promise<boolean> {
    for (let i = 0; i < 9; i++) {
      try {
        const r = await fetch(`${apiBase}/health`, { cache: "no-store" });
        if (r.ok) return true;
      } catch {
        /* not awake yet — keep pinging */
      }
      await new Promise((res) => setTimeout(res, 3500));
    }
    return false;
  }

  async function runDemo() {
    // Guard against overlapping runs: ignore extra clicks while one is already
    // running/awaiting (double-clicks would otherwise spawn rival EventSources
    // and surface a spurious "Run failed").
    if (status === "running" || status === "awaiting") return;
    reset();
    setStatus("running");
    // Telemetry baseline: stamp the start time + the token counter so the result panel
    // can report this run's real latency and tokens.
    runStartRef.current = Date.now();
    void readHealthCounters().then(({ tokens, cost }) => {
      startTokensRef.current = tokens;
      startCostRef.current = cost;
    });

    // Warm the backend first: a cold/idle container becomes a short, reassured wait
    // (the "Waking…" banner) instead of a failed POST. Pings /health with retries;
    // if it never wakes we still attempt the run and let the error path speak.
    setWarming(true);
    await warmUpBackend();
    setWarming(false);

    let runId: string;
    try {
      const mi = dirtyModelInputs();
      const res = await fetch(`${apiBase}/api/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // The selected building + city resolve to the IDF + weather file the
        // backend runs; the grid carbon factor follows the city's state. Only
        // moved model inputs are sent; the CBD-cohort realism gate is always on.
        body: JSON.stringify({
          utility: PAYLOAD.utility,
          validate_realism: true,
          ...pathsFor(building, city),
          ...(Object.keys(mi).length ? { model_inputs: mi } : {}),
        }),
      });
      if (!res.ok) {
        const friendly =
          res.status === 429
            ? "The demo hit its rate limit (too many runs just now). Give it a minute and try again."
            : res.status === 503
              ? "The demo's daily simulation budget has been reached — it resets within 24h."
              : `Couldn't start the run (HTTP ${res.status}).`;
        throw new Error(friendly);
      }
      runId = (await res.json()).run_id as string;
      runIdRef.current = runId;
    } catch (e) {
      const raw = e instanceof Error ? e.message : "";
      setError(
        raw && !/failed to fetch/i.test(raw)
          ? raw
          : "Couldn't reach the simulation backend — it may be waking from a cold start. Try again in ~30s.",
      );
      setStatus("error");
      return;
    }

    const es = new EventSource(`${apiBase}/api/runs/${runId}/events`);
    esRef.current = es;

    es.onopen = () => {
      // (Re)connected — any in-flight transient-failure timer is moot.
      if (failTimerRef.current) {
        clearTimeout(failTimerRef.current);
        failTimerRef.current = null;
      }
    };

    es.onmessage = (msg) => {
      // A real event arrived → the stream is healthy; cancel any pending fail timer
      // and record that we've had data (distinguishes cold-start from a mid-run drop).
      gotDataRef.current = true;
      if (failTimerRef.current) {
        clearTimeout(failTimerRef.current);
        failTimerRef.current = null;
      }
      let ev: { agent?: string; status?: string; payload?: Record<string, unknown> };
      try {
        ev = JSON.parse(msg.data);
      } catch {
        return; // keepalive / non-JSON line
      }
      const agent = ev.agent as AgentKey | "done" | "failed" | undefined;
      const st = ev.status;
      const payload = ev.payload ?? {};

      // Terminal marker: the backend emits {agent:"reviewer", status:"done"} (or a
      // top-level agent:"done") as the LAST event. Approved → green; withheld → the
      // Reviewer rejected, so the node goes amber and the result shows the gate firing.
      if (st === "done" || agent === "done") {
        const ok = payload.approved !== false;
        es.close();
        // Reveal sim→analyzer→reviewer as distinct steps instead of all at once.
        runFinishSequence(ok, runId);
        return;
      }
      if (agent === "failed" || st === "failed") {
        if (agent && agent in nodes) setNode(agent as AgentKey, "failed");
        es.close();
        setStatus("error");
        // A real pipeline/infra error carries payload.message/error — surface it
        // honestly rather than blaming the Reviewer's gate. A genuine withhold
        // arrives as done + approved:false (handled above), never as "failed".
        const msg =
          typeof payload.message === "string" && payload.message
            ? payload.message
            : typeof payload.error === "string" && payload.error
              ? `The run hit an error: ${payload.error}`
              : "The run failed — the simulation backend hit an error. Try again in a moment.";
        setError(msg);
        return;
      }

      if (!agent || !(agent in nodes)) return;
      const key = agent as AgentKey;

      // Once the sim is done, the analyzer + reviewer fire in the same instant —
      // suppress their raw events so runFinishSequence reveals them in order.
      if (finishingRef.current && (key === "analyzer" || key === "reviewer")) return;

      if (st === "started" || st === "progress") {
        setNode(key, "active");
        if (key === "sim_runner") {
          setSimStartedAt((t) => t ?? Date.now());
          if (payload.scenario && payload.status === "running") {
            setScenarioStartedAt(Date.now());
            setScenarioName(String(payload.scenario));
          }
          if (payload.scenario) {
            upsertSim({
              scenario: String(payload.scenario),
              status: String(payload.status ?? "running"),
              eui: typeof payload.eui === "number" ? payload.eui : undefined,
              annual_kwh: typeof payload.annual_kwh === "number" ? payload.annual_kwh : undefined,
              runtime_s: typeof payload.runtime_s === "number" ? payload.runtime_s : undefined,
            });
          }
        }
      } else if (st === "completed") {
        setNode(key, "done");
        // Sim done → from here, gate the instant analyzer/reviewer events.
        if (key === "sim_runner") finishingRef.current = true;
      } else if (st === "awaiting_approval") {
        // CLICK-ONLY HITL — surface the approval gate and WAIT. Do not auto-approve.
        // The Modeler proposes the candidate measures; the demoer picks ONE.
        setNode("modeler", "done");
        gateShownAtRef.current = Date.now(); // start of the human-paced approval pause
        const ms = (Array.isArray(payload.measures) ? payload.measures : []) as MeasureCandidate[];
        setCandidates(ms);
        setChosenMeasure((cur) => cur ?? ms[0]?.key ?? null); // default-select the first
        setStatus("awaiting");
      }
    };

    es.onerror = () => {
      // EventSource fires onerror on TRANSIENT blips too — most notably while the
      // server holds the stream open through the awaiting_approval pause, or a brief
      // network drop. The browser auto-reconnects in that case (readyState ===
      // CONNECTING); closing + erroring on the first event (the old behaviour) aborted
      // an otherwise-healthy run and was the suspected "drops before the approval gate"
      // bug. So: only fail immediately when the stream is fully CLOSED (browser gave up
      // / HTTP error). For a transient CONNECTING state, give the reconnect a grace
      // window and fail only if no event arrives in time (onmessage/onopen clear it).
      const fail = () => {
        if (failTimerRef.current) {
          clearTimeout(failTimerRef.current);
          failTimerRef.current = null;
        }
        es.close();
        // Honest error either way (no recorded fallback): "never connected" reads as a
        // cold start; a drop after we'd already streamed events reads as a lost stream.
        const msg = gotDataRef.current
          ? "Lost connection to the live stream mid-run."
          : "Couldn't reach the live backend — it may be waking from a cold start. Try again in ~30s.";
        setStatus((cur) => {
          if (cur === "running" || cur === "awaiting") {
            setError(msg);
            return "error";
          }
          return cur;
        });
      };
      if (es.readyState === EventSource.CLOSED) {
        fail();
        return;
      }
      // CONNECTING → let the browser's auto-reconnect try; fail only if it doesn't recover.
      if (failTimerRef.current == null) {
        failTimerRef.current = setTimeout(fail, 12000);
      }
    };
  }

  const busy = status === "running" || status === "awaiting";
  // The run is "validated" when the Reviewer range-checked the baseline against a
  // real verified CBD cohort (all four cities today); elsewhere it's illustrative.
  const cohortValidated = result?.review.cohort_validated ?? result?.cohort_validated ?? false;

  // Step-1 selection → characteristics shown before the run.
  const b = buildingDef(building);
  const c = cityDef(city);

  const statusLine =
    status === "running"
      ? "Streaming the agent trace…"
      : status === "awaiting"
        ? "Paused — approve the plan to run the simulation"
        : status === "done"
          ? "Run complete — Reviewer returned its verdict"
          : status === "error"
            ? "Run failed"
            : "";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Intro — the one choice the demoer makes before running */}
      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.55, color: "var(--dim)" }}>
        <strong style={{ color: "var(--acc)" }}>→</strong> <strong style={{ color: "var(--tx)" }}>Pick a city below to run the model against</strong>, choose your
        inputs, then press <strong style={{ color: "var(--tx)" }}>Launch Live Demo</strong>. The building is
        scope-locked to a Medium office; the city you choose sets the climate zone, the grid carbon factor, and
        the real CBD office cohort your baseline is validated against.
      </p>

      {/* ── Step 1 — pick a building, then the city it runs against ─────────── */}
      <div
        style={{
          borderRadius: 12,
          border: "0.5px solid var(--line)",
          background: "#22242b",
          padding: 16,
          display: "flex",
          flexDirection: "column",
          gap: 14,
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: 20 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6,
              fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.06em",
              textTransform: "uppercase", color: "var(--dim)" }}>
              <Building2 className="h-3.5 w-3.5" /> Building
            </span>
            <span style={{ borderRadius: 8, padding: "6px 12px", fontFamily: "var(--disp)",
              fontSize: 13, fontWeight: 500, color: accent,
              border: `0.5px solid ${accent}`, background: "rgba(91,156,255,0.08)" }}
              title="Office, Medium — the only size with a real disclosed CBD cohort to validate against">
              Medium Office · scope-locked
            </span>
          </div>
          <PillRow
            icon={<MapPin className="h-3.5 w-3.5" />}
            label="City / weather file"
            accent={accent}
            options={CITIES.map((x) => ({ key: x.key, label: x.label }))}
            value={city}
            disabled={busy}
            onPick={(k) => setCity(k as CityKey)}
          />
        </div>

        {/* Two cards: the pre-loaded building, and what's fed to the modeller —
            all deterministic facts; the IDF model file is downloadable. */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(290px, 1fr))", gap: 12 }}>
          <SpecCard icon="🏢" title="Building characteristics">
            <SpecLine k="Type" v="Office (commercial)" />
            <SpecLine k="Prototype" v="DOE Ref. Medium Office" />
            <SpecLine k="Storeys" v={String(b.storeys)} />
            <SpecLine k="Floor area (medium band)" v="2,500 – 10,000 m²" />
            <SpecLineIdf k="Geometry (IDF)" href={`/models/${b.download}`} fileName={b.download} />
          </SpecCard>
          <SpecCard icon="⚙️" title="What goes into the modeller">
            <SpecLine k="Weather (EPW)" v={c.epw} mono valueColor="var(--acc)" />
            <SpecLine k="NCC climate zone" v={`${c.nccClimateZone} · ${c.nccZoneDescriptor}`} />
            <SpecLine k="Grid carbon (Scope 2)" v={`${c.electricityScope2.toFixed(2)} kgCO₂e/kWh · ${c.emissionFactorSource}`} />
            <SpecLine k="Inputs" v="the 9 below" />
            <SpecLine k="Validation" v="CBD-cohort realism gate" />
          </SpecCard>
        </div>
      </div>

      {/* Step 1b — the nine editable model inputs (test the gate) */}
      <ModelInputsCard
        accent={accent}
        values={inputs}
        disabled={busy}
        dirtyCount={dirtyCount}
        onChange={(field, v) => setInputs((s) => ({ ...s, [field]: v }))}
        onReset={() =>
          setInputs(Object.fromEntries(MODEL_INPUTS.map((m) => [m.field, m.def])))
        }
      />

      {/* Controls — one deliberate primary button at the top */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12 }}>
        <button onClick={runDemo} disabled={busy} className="btn pri" aria-busy={busy}>
          {busy ? (
            <>
              <Loader2 className="h-4 w-4" style={{ animation: "spin 1s linear infinite" }} />
              Running the physics…
            </>
          ) : (
            <>
              Launch Live Demo
              <ArrowRight className="h-4 w-4" />
            </>
          )}
        </button>

        {/* Beside the button before launch — sets the expectation honestly. */}
        {status === "idle" && (
          <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--dim)", maxWidth: 460 }}>
            Run it live on real EnergyPlus, ~50s for 2 real simulations.
          </span>
        )}

        {statusLine && (
          <span
            aria-live="polite"
            style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--dim)" }}
          >
            {statusLine}
          </span>
        )}

        {cohortValidated && (
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              borderRadius: 8,
              padding: "4px 9px",
              fontFamily: "var(--mono)",
              fontSize: 11.5,
              color: accent,
              border: `0.5px solid ${accent}`,
              background: "rgba(91,156,255,0.08)",
            }}
            title="Baseline range-checked against the real disclosed CBD office cohort"
          >
            <BadgeCheck className="h-3.5 w-3.5" />
            validated vs real CBD cohort
          </span>
        )}
      </div>

      {/* Before launch: a still of the demo so people see what they're about to run. */}
      {status === "idle" && (
        <div className="demo-embed" style={{ padding: 0, overflow: "hidden" }}>
          <img
            src="/img/aem-demo-section.jpg"
            alt="The Agentic Energy Modeller demo — a 5-agent run driving a real EnergyPlus building-energy simulation."
            style={{ display: "block", width: "100%", height: "auto" }}
          />
        </div>
      )}

      {/* Waking a cold backend — turns a cold start into a short, reassured wait */}
      {warming && (
        <Banner>
          <Loader2 className="h-4 w-4 animate-spin" style={{ flexShrink: 0, marginTop: 2 }} />
          <p style={{ margin: 0, lineHeight: 1.6 }}>
            Waking the simulation backend… the first run after it&apos;s been idle can take ~30s. This is
            normal — the live run starts automatically once it&apos;s up.
          </p>
        </Banner>
      )}

      {/* Error — never silent */}
      {status === "error" && (
        <Banner role="alert">
          <TriangleAlert className="h-4 w-4" style={{ flexShrink: 0, marginTop: 2 }} />
          <p style={{ margin: 0, lineHeight: 1.6 }}>
            Couldn&apos;t complete the run{error ? `: ${error}` : "."} The container
            may be waking, or the Reviewer withheld approval — press Launch Live Demo to try again.
          </p>
        </Banner>
      )}

      {/* ── Act 1 — the 5-agent vertical pipeline (explanation beside each) ── */}
      {status !== "idle" && (
        <div>
          <SectionLabel title="The agents run" note="2 touch an LLM · none author a number" />
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 1,
              overflow: "hidden",
              borderRadius: 14,
              border: "0.5px solid var(--line)",
              background: "var(--line)",
            }}
          >
            {AGENTS.map((a, i) => (
              <Fragment key={a.key}>
                <AgentRow
                  agent={a}
                  state={nodes[a.key]}
                  accent={accent}
                  isLast={i === AGENTS.length - 1}
                />
                {/* CLICK-ONLY HITL gate — injected right under the Modeler row */}
                {a.key === "modeler" && status === "awaiting" && (
                  <ApprovalGate
                    accent={accent}
                    building={b}
                    city={c}
                    inputs={inputs}
                    candidates={candidates}
                    chosen={chosenMeasure}
                    onPick={setChosenMeasure}
                    onApprove={onApprove}
                  />
                )}
                {/* Live progress for the long EnergyPlus step — keeps the demoer
                    confident it's running (~20s per scenario), not stuck. */}
                {a.key === "sim_runner" && nodes.sim_runner === "active" && (
                  <SimProgress
                    accent={accent}
                    simStartedAt={simStartedAt}
                    scenarioStartedAt={scenarioStartedAt}
                    scenarioName={scenarioName}
                    doneCount={sims.filter((s) => s.status === "success").length}
                  />
                )}
              </Fragment>
            ))}
          </div>

          {approved && status !== "awaiting" && (
            <div
              style={{
                marginTop: 12,
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: 12,
                color: "var(--dim)",
              }}
            >
              <ShieldCheck className="h-3.5 w-3.5" style={{ color: accent }} />
              <span>
                Approval gate cleared at{" "}
                <code style={{ color: "var(--tx)" }}>awaiting_approval</code> —
                API-enforced human-in-the-loop, not a prompt.
              </span>
            </div>
          )}
        </div>
      )}

      {/* Final business case — released ONLY if the Reviewer approved. A withheld
          run shows the failing gate, not a polished result (the honest path). */}
      {result && (result.review.approved
        ? <ResultPanel result={result} sims={sims} accent={accent} city={city} building={building} telemetry={telemetry} />
        : <WithheldPanel result={result} accent={accent} city={city} building={building} onReset={() => {
            setInputs(Object.fromEntries(MODEL_INPUTS.map((m) => [m.field, m.def])));
          }} />)}
    </div>
  );
}

/* ── A simple section header — title + rule + optional note ────────────────── */
function SectionLabel({ title, note }: { title: string; note?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
      <span style={{ fontFamily: "var(--disp)", fontSize: 15, fontWeight: 600, color: "var(--tx)" }}>{title}</span>
      <span style={{ flex: 1, height: 1, background: "var(--line)" }} />
      {note && <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)" }}>{note}</span>}
    </div>
  );
}

/* ── CLICK-ONLY HITL approval gate — the human picks ONE measure + approves the ──
   Modeler's plan before EnergyPlus runs. The pipeline blocks server-side at
   `awaiting_approval` until the demoer clicks; nothing auto-advances. Shows exactly
   what's approved: the building, the model file, the sim parameters, and the measure
   choice. Picking one measure keeps the live run to 2 EnergyPlus sims (~50s). */
function ApprovalGate({
  accent,
  building,
  city,
  inputs,
  candidates,
  chosen,
  onPick,
  onApprove,
}: {
  accent: string;
  building: ReturnType<typeof buildingDef>;
  city: ReturnType<typeof cityDef>;
  inputs: Record<string, number>;
  candidates: MeasureCandidate[];
  chosen: string | null;
  onPick: (key: string) => void;
  onApprove: () => void;
}) {
  const chosenName = chosen ? measureMeta(chosen).name : null;
  const val = (field: string) => inputs[field] ?? MODEL_INPUTS.find((m) => m.field === field)?.def ?? 0;
  const area = val("floor_area_m2");
  const params: [string, string][] = [
    ["Floor area", `${Math.round(area).toLocaleString()} m²`],
    ["Equipment / plug load", `${val("equipment_w_m2").toFixed(1)} W/m²`],
    ["Lighting power density", `${val("lighting_w_m2").toFixed(1)} W/m²`],
    ["HVAC efficiency", `COP ${val("hvac_cop").toFixed(2)}`],
    ["Glazing U-value", `${val("window_u").toFixed(2)} W/m²·K`],
    ["Schedules", "AU whole-building office (occupancy + hours)"],
    ["Weather + climate", `${city.epw} · NCC ${city.nccClimateZone}`],
    ["Constructions", `prototype envelope + grid ${city.electricityScope2.toFixed(2)} kgCO₂e/kWh`],
  ];
  return (
    <div
      style={{
        background: "rgba(91,156,255,0.07)",
        borderTop: `0.5px solid ${accent}`,
        borderBottom: `0.5px solid ${accent}`,
        padding: 16,
      }}
    >
      <p style={{ margin: "0 0 14px", fontSize: 12, lineHeight: 1.5, color: "var(--tx)" }}>
        ⏸ <strong style={{ color: accent }}>Pick one measure, then approve.</strong>{" "}
        You&apos;re approving the modelling plan — the building, the model file, the
        parameters, and your chosen measure — not the numbers (they don&apos;t exist
        yet). One measure keeps the live run to <strong style={{ color: "var(--tx)" }}>2 real
        EnergyPlus simulations</strong> (baseline + your pick, ~50s).
      </p>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 18, marginBottom: 15 }}>
        <div>
          <GateLabel>🏢 Building to model</GateLabel>
          <GateKV k="Type" v={`Office · ${building.label}`} />
          <GateKV k="Floor area" v={`${Math.round(area).toLocaleString()} m²`} />
          <GateKV k="City · zone" v={`${city.label} · NCC ${city.nccClimateZone}`} />
          <GateKV k="Weather (EPW)" v={city.epw} />
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontFamily: "var(--mono)", fontSize: 11.5, padding: "3px 0" }}>
            <span style={{ color: "var(--dim)" }}>Model file (IDF)</span>
            <a
              href={`/models/${building.download}`}
              download
              title={`Download ${building.download}`}
              style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--cyan)", fontWeight: 600, borderBottom: "1px dashed rgba(45,212,191,0.4)" }}
            >
              <FileCode2 className="h-3 w-3" /> {building.download}
            </a>
          </div>
        </div>
        <div>
          <GateLabel bold>🔧 Pick one measure to simulate</GateLabel>
          <div style={{ display: "flex", flexDirection: "column", gap: 7, marginTop: 4 }}>
            {candidates.map((m) => {
              const meta = measureMeta(m.key);
              const isSel = chosen === m.key;
              return (
                <button
                  key={m.key}
                  type="button"
                  data-measure={m.key}
                  onClick={() => onPick(m.key)}
                  aria-pressed={isSel}
                  style={{
                    display: "flex", alignItems: "flex-start", gap: 9, textAlign: "left",
                    width: "100%", cursor: "pointer", padding: "9px 11px", borderRadius: 9,
                    background: isSel ? "rgba(91,156,255,0.14)" : "rgba(255,255,255,0.02)",
                    border: `0.5px solid ${isSel ? accent : "var(--line)"}`,
                  }}
                >
                  <span
                    aria-hidden
                    style={{
                      flexShrink: 0, marginTop: 1, width: 14, height: 14, borderRadius: "50%",
                      border: `1.5px solid ${isSel ? accent : "var(--dim)"}`,
                      background: isSel
                        ? `radial-gradient(circle, ${accent} 0 4px, transparent 5px)`
                        : "transparent",
                    }}
                  />
                  <span style={{ minWidth: 0 }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--tx)", fontWeight: 600 }}>
                      {meta.icon} {meta.name}
                    </span>
                    <span style={{ display: "block", fontSize: 11.5, color: "var(--dim)", lineHeight: 1.4, marginTop: 2 }}>
                      {m.description}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div style={{ borderTop: "0.5px solid var(--line)", paddingTop: 13, marginBottom: 15 }}>
        <GateLabel>⚙️ Exactly what the Sim Runner feeds EnergyPlus (from the IDF + your edits)</GateLabel>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "5px 18px", marginTop: 9 }}>
          {params.map(([k, v]) => (
            <div key={k} style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)", lineHeight: 1.45 }}>
              <span style={{ color: accent }}>•</span> {k} — <strong style={{ color: "var(--tx)", fontWeight: 600 }}>{v}</strong>
            </div>
          ))}
        </div>
      </div>

      <button onClick={onApprove} className="btn pri" disabled={!chosen}>
        <CheckCircle2 className="h-4 w-4" />
        {chosenName ? `Approve & simulate ${chosenName}` : "Pick a measure to continue"}
      </button>
    </div>
  );
}

function GateLabel({ children, bold }: { children: React.ReactNode; bold?: boolean }) {
  return (
    <div style={{ fontFamily: "var(--mono)", fontSize: bold ? 11.5 : 10, letterSpacing: "0.06em", textTransform: "uppercase", color: bold ? "var(--tx)" : "var(--dim)", fontWeight: bold ? 700 : 400, marginBottom: 9 }}>
      {children}
    </div>
  );
}
function GateKV({ k, v }: { k: string; v: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, fontFamily: "var(--mono)", fontSize: 11.5, padding: "3px 0" }}>
      <span style={{ color: "var(--dim)" }}>{k}</span>
      <strong style={{ color: "var(--tx)", fontWeight: 600, textAlign: "right" }}>{v}</strong>
    </div>
  );
}

/* ── Reviewer-withheld panel — the gate firing for real ───────────────────── */
function WithheldPanel({
  result,
  accent,
  city,
  building,
  onReset,
}: {
  result: RunResult;
  accent: string;
  city: CityKey;
  building: BuildingKey;
  onReset: () => void;
}) {
  const r = result.review;
  // Prefer the live cohort the Reviewer gated on; fall back to the verified catalog
  // cohort for the selected city so the strip always has a real range to plot.
  const cat = cohortFor(city, building);
  const p25 = r.cohort_p25 ?? cat?.p25 ?? null;
  const p75 = r.cohort_p75 ?? cat?.p75 ?? null;
  const n = r.cohort_n ?? cat?.n ?? null;
  return (
    <div style={{ borderTop: "0.5px solid var(--line)", paddingTop: 22 }}>
      <SectionLabel title="Withheld by the gate" note="the Reviewer did its job" />
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 12,
          borderRadius: 12,
          border: "0.5px solid rgba(230,180,91,0.4)",
          background: "rgba(230,180,91,0.07)",
          color: "var(--amber)",
          padding: 16,
        }}
      >
        <TriangleAlert className="h-5 w-5" style={{ flexShrink: 0, marginTop: 2 }} />
        <div style={{ fontSize: 13, lineHeight: 1.6 }}>
          <strong style={{ color: "var(--tx)" }}>Reviewer withheld approval.</strong>{" "}
          The model inputs you set produced a baseline EUI outside the real disclosed
          range for a {city} medium office, so the business case was{" "}
          <strong style={{ color: "var(--tx)" }}>not released</strong> — the gate is
          real, not theatre. Adjust the inputs and re-run.
          <div
            style={{
              marginTop: 10,
              fontFamily: "var(--mono)",
              fontSize: 12,
              color: "var(--tx)",
            }}
          >
            baseline EUI {r.baseline_eui?.toFixed(1) ?? "—"} kWh/m²·yr · outside real
            CBD cohort p25 {p25?.toFixed(0) ?? "—"}–p75 {p75?.toFixed(0) ?? "—"}
            {n ? ` (n=${n})` : ""} · route_to {r.route_to}
          </div>
          <button
            onClick={onReset}
            className="btn"
            style={{ marginTop: 14 }}
          >
            Reset inputs to default &amp; re-run
          </button>
        </div>
      </div>
    </div>
  );
}

/* ── A small reusable amber banner (recorded / error) ─────────────────────── */
function Banner({
  children,
  role,
}: {
  children: React.ReactNode;
  role?: "alert";
}) {
  return (
    <div
      role={role}
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 12,
        borderRadius: 12,
        border: "0.5px solid rgba(230,180,91,0.4)",
        background: "rgba(230,180,91,0.07)",
        color: "var(--amber)",
        padding: 16,
        fontSize: 13,
      }}
    >
      {children}
    </div>
  );
}

/* ── Step-1 selector: a labelled row of pill toggles ──────────────────────── */
function PillRow({
  icon,
  label,
  options,
  value,
  onPick,
  accent,
  disabled,
}: {
  icon: React.ReactNode;
  label: string;
  options: { key: string; label: string }[];
  value: string;
  onPick: (key: string) => void;
  accent: string;
  disabled?: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          fontFamily: "var(--mono)",
          fontSize: 11.5,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--dim)",
        }}
      >
        {icon}
        {label}
      </span>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {options.map((o) => {
          const on = o.key === value;
          return (
            <button
              key={o.key}
              onClick={() => onPick(o.key)}
              disabled={disabled}
              aria-pressed={on}
              style={{
                borderRadius: 8,
                padding: "6px 12px",
                fontFamily: "var(--disp)",
                fontSize: 13,
                fontWeight: 500,
                cursor: disabled ? "not-allowed" : "pointer",
                opacity: disabled && !on ? 0.5 : 1,
                color: on ? accent : "var(--dim)",
                border: `0.5px solid ${on ? accent : "var(--line)"}`,
                background: on ? "rgba(91,156,255,0.08)" : "var(--s1)",
                transition: "all 0.12s ease",
              }}
            >
              {o.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ── A titled facts card (Building characteristics / What goes into the modeller) ── */
function SpecCard({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
  return (
    <div style={{ borderRadius: 12, border: "0.5px solid var(--line)", background: "var(--s1)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "11px 14px" }}>
        <span style={{ fontSize: 14 }}>{icon}</span>
        <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--tx)" }}>
          {title}
        </span>
      </div>
      <div>{children}</div>
    </div>
  );
}

const SPEC_ROW: React.CSSProperties = {
  display: "flex", alignItems: "baseline", justifyContent: "space-between",
  gap: 12, padding: "9px 14px", borderTop: "0.5px solid var(--line)",
};

function SpecLine({ k, v, mono, valueColor }: { k: string; v: string; mono?: boolean; valueColor?: string }) {
  return (
    <div style={SPEC_ROW}>
      <span style={{ fontSize: 12, color: "var(--dim)" }}>{k}</span>
      <span style={{ fontSize: 12, fontFamily: mono ? "var(--mono)" : "inherit", color: valueColor ?? "var(--tx)", textAlign: "right" }}>
        {v}
      </span>
    </div>
  );
}

/* The IDF model file, as a real downloadable link (served from /public/models). */
function SpecLineIdf({ k, href, fileName }: { k: string; href: string; fileName: string }) {
  return (
    <div style={SPEC_ROW}>
      <span style={{ fontSize: 12, color: "var(--dim)" }}>{k}</span>
      <a
        href={href}
        download
        title={`Download ${fileName}`}
        style={{ display: "inline-flex", alignItems: "center", gap: 5, fontFamily: "var(--mono)", fontSize: 12, color: "var(--acc)", borderBottom: "1px solid rgba(91,156,255,0.4)", paddingBottom: 1 }}
      >
        <Download className="h-3 w-3" /> {fileName}
      </a>
    </div>
  );
}

/* ── Step-1b: the nine editable model inputs (test the gate) ───────────────── */
function ModelInputsCard({
  accent,
  values,
  disabled,
  dirtyCount,
  onChange,
  onReset,
}: {
  accent: string;
  values: Record<string, number>;
  disabled?: boolean;
  dirtyCount: number;
  onChange: (field: string, v: number) => void;
  onReset: () => void;
}) {
  return (
    <div
      style={{
        borderRadius: 12,
        border: "0.5px solid var(--line)",
        background: "var(--s1)",
        padding: 16,
        display: "flex",
        flexDirection: "column",
        gap: 14,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <span
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            fontFamily: "var(--mono)", fontSize: 11.5, fontWeight: 700, letterSpacing: "0.06em",
            textTransform: "uppercase", color: "var(--tx)",
          }}
        >
          <Cpu className="h-3.5 w-3.5" />
          Select model inputs
        </span>
        <button
          onClick={onReset}
          disabled={disabled || dirtyCount === 0}
          className="btn"
          style={{ fontSize: 12, opacity: dirtyCount === 0 ? 0.5 : 1 }}
        >
          Reset to default{dirtyCount ? ` (${dirtyCount})` : ""}
        </button>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))",
          gap: 14,
        }}
      >
        {MODEL_INPUTS.map((m) => (
          <InputRow
            key={m.field}
            def={m}
            value={values[m.field] ?? m.def}
            accent={accent}
            disabled={disabled}
            onChange={(v) => onChange(m.field, v)}
          />
        ))}
      </div>
    </div>
  );
}

function InputRow({
  def,
  value,
  accent,
  disabled,
  onChange,
}: {
  def: (typeof MODEL_INPUTS)[number];
  value: number;
  accent: string;
  disabled?: boolean;
  onChange: (v: number) => void;
}) {
  const dirty = Math.abs(value - def.def) > 1e-9;
  const worse =
    (def.worse === "up" && value > def.def) || (def.worse === "down" && value < def.def);
  const hint = !dirty
    ? ""
    : !def.energy
      ? "resizes the building · total energy scales, EUI ~flat"
      : worse
        ? "↑ EUI"
        : "↓ EUI";
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
        <span style={{ fontSize: 12, color: "var(--tx)" }} title={def.help}>
          {dirty && (
            <span style={{ color: accent, marginRight: 5 }} aria-label="modified">●</span>
          )}
          {def.label}
        </span>
        <span style={{ fontFamily: "var(--mono)", fontSize: 12, color: dirty ? accent : "var(--dim)" }}>
          {value}
          <span style={{ color: "var(--dim)" }}> {def.unit}</span>
        </span>
      </div>
      <input
        type="range"
        min={def.min}
        max={def.max}
        step={def.step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ width: "100%", accentColor: accent }}
      />
      {hint && (
        <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: def.energy ? "var(--amber)" : "var(--dim)" }}>
          {hint}
        </span>
      )}
    </div>
  );
}

/* ── One agent in the vertical pipeline — emblem · meta + tag · explanation
   (purpose / ✓ Does / ✕ Doesn't / live line) · status — matching the mockup. ── */
/* ── Live Sim-Runner progress — the long pole (~20s per EnergyPlus scenario).
   Ticks an elapsed clock + a per-scenario countdown/bar so the demoer can see the
   model is running, not frozen. ──────────────────────────────────────────────── */
function SimProgress({
  accent,
  simStartedAt,
  scenarioStartedAt,
  scenarioName,
  doneCount,
}: {
  accent: string;
  simStartedAt: number | null;
  scenarioStartedAt: number | null;
  scenarioName: string | null;
  doneCount: number;
}) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, []);
  const EST = 22; // measured ~21s per scenario on real EnergyPlus
  const totalEl = simStartedAt ? Math.max(0, (now - simStartedAt) / 1000) : 0;
  const scEl = scenarioStartedAt ? Math.max(0, (now - scenarioStartedAt) / 1000) : 0;
  const remain = Math.max(0, EST - scEl);
  const pct = Math.min(96, (scEl / EST) * 100);
  const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
  const label = scenarioName ? scenarioName.replace(/_/g, " ") : "preparing the model";
  return (
    <div style={{ background: "var(--s2)", borderTop: `0.5px solid ${accent}`, padding: "13px 16px 15px 76px" }}>
      <div style={{ fontSize: 12, color: "var(--tx)", lineHeight: 1.5, marginBottom: 11 }}>
        Your building is being run through <b style={{ color: accent }}>EnergyPlus</b> — a real,
        physics-based energy simulation engine. The computation genuinely takes ~20&nbsp;s per scenario,
        so this step is the slow one by design. <b style={{ color: "var(--tx)" }}>Nothing is broken — the
        model is working.</b>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)" }}>
        <span>
          ⏱ running real EnergyPlus — scenario {doneCount + 1}{" "}
          (<span style={{ color: "var(--tx)" }}>{label}</span>)
        </span>
        <span style={{ color: "var(--tx)" }}>{mmss(totalEl)} elapsed</span>
      </div>
      <div style={{ marginTop: 9, height: 6, borderRadius: 4, background: "var(--s3)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: accent, borderRadius: 4, transition: "width .25s linear" }} />
      </div>
      <div style={{ marginTop: 7, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)" }}>
        {remain > 1.5 ? `~${Math.ceil(remain)}s left on this scenario` : "finishing this scenario…"} · each EnergyPlus run ≈ 20s · the model is running, not stuck
      </div>
    </div>
  );
}

function AgentRow({
  agent,
  state,
  accent,
  isLast,
}: {
  agent: AgentDef;
  state: NodeState;
  accent: string;
  isLast: boolean;
}) {
  const active = state === "active";
  const done = state === "done";
  const failed = state === "failed";

  const emBorder = active ? accent : done ? "var(--green)" : failed ? "var(--amber)" : "var(--line2)";
  const nameColor = state === "pending" ? "var(--dim)" : "var(--tx)";
  const liveColor = active ? "var(--acc)" : done ? "var(--green)" : failed ? "var(--amber)" : "var(--dim)";
  const liveText = active
    ? `● ${agent.live}`
    : done
      ? `✓ ${agent.done}`
      : failed
        ? "✕ withheld — see the gate"
        : "";

  const tagStyle = { color: "var(--acc)", background: "rgba(91,156,255,.1)", border: "0.5px solid rgba(91,156,255,.3)" };

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "46px 184px 1fr 22px",
        alignItems: "flex-start",
        gap: 14,
        background: active ? "var(--s2)" : "var(--s1)",
        padding: "15px 16px",
        position: "relative",
        transition: "background 0.25s ease",
      }}
    >
      {/* the vertical thread connecting the emblems down the pipeline */}
      {!isLast && (
        <span style={{ position: "absolute", left: 38, top: 34, bottom: -1, width: 1, background: "var(--line)", zIndex: 0 }} />
      )}

      {/* emblem */}
      <div
        style={{
          width: 38, height: 38, borderRadius: 11, display: "grid", placeItems: "center",
          fontSize: 19, background: "var(--s2)", border: `0.5px solid ${emBorder}`, zIndex: 1,
          boxShadow: active ? "0 0 0 3px rgba(91,156,255,0.13)" : "none", transition: "border-color 0.25s ease",
        }}
      >
        {agent.emblem}
      </div>

      {/* name · role · LLM/no-LLM tag */}
      <div style={{ paddingTop: 2 }}>
        <div style={{ fontFamily: "var(--disp)", fontWeight: 600, fontSize: 14, color: nameColor }}>{agent.name}</div>
        <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)", marginTop: 2 }}>{agent.role}</div>
        <span
          style={{
            display: "inline-block", fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.04em",
            textTransform: "uppercase", padding: "2px 6px", borderRadius: 5, marginTop: 7, ...tagStyle,
          }}
        >
          {agent.tag}
        </span>
      </div>

      {/* explanation beside the agent */}
      <div style={{ paddingTop: 1 }}>
        <div style={{ fontSize: 12, color: "var(--tx)", lineHeight: 1.45, fontWeight: 700 }}>{agent.purpose}</div>
        <ExBlock label="✓ Does" labelColor="var(--acc)" items={agent.does} />
        <ExBlock label="✕ Doesn't" labelColor="var(--acc)" items={agent.doesnt} />
        {liveText && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, marginTop: 9, color: liveColor, lineHeight: 1.4 }}>
            {liveText}
          </div>
        )}
      </div>

      {/* status indicator */}
      <div style={{ justifySelf: "center", paddingTop: 4 }}>
        {active && <Loader2 className="h-4 w-4" style={{ color: accent, animation: "spin 1s linear infinite" }} />}
        {done && <CheckCircle2 className="h-4 w-4" style={{ color: "var(--green)" }} />}
        {failed && <XCircle className="h-4 w-4" style={{ color: "var(--amber)" }} />}
        {state === "pending" && <Circle className="h-3.5 w-3.5" style={{ color: "var(--line2)" }} />}
      </div>
    </div>
  );
}

function ExBlock({ label, labelColor, items }: { label: string; labelColor: string; items: string[] }) {
  return (
    <div
      style={{
        display: "grid", gridTemplateColumns: "66px 1fr", gap: 8, marginTop: 6,
        fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)", lineHeight: 1.5,
      }}
    >
      <b style={{ fontWeight: 600, color: labelColor }}>{label}</b>
      <div>
        {items.map((it, i) => (
          <div key={i} style={{ display: "flex", gap: 6 }}>
            <span style={{ color: labelColor, opacity: 0.7 }}>·</span>
            <span>{it}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── The final business case: the agent trace, then Results (the numbers + where
   the baseline lands vs the real cohort), then the what-if scenarios. ── */
function ResultPanel({
  result,
  sims,
  accent,
  city,
  building,
  telemetry,
}: {
  result: RunResult;
  sims: SimRow[];
  accent: string;
  city: CityKey;
  building: BuildingKey;
  telemetry: { latencyMs: number; tokens: number | null; costUsd: number | null } | null;
}) {
  const r = result;
  const rec = r.recommended;
  const baseEui = r.building.baseline_eui_kwh_m2_yr;
  const area = r.building.floor_area_m2;
  const annualKwh = baseEui * area;
  // Carbon uses the deterministic NGA grid factor implied by the run's emission
  // source (e.g. "NGA 2025 NSW" → NSW 0.64), never an LLM number. Fall back to the
  // selected city's factor, then the national factor.
  const { factor, label: gridLabel } = factorFromSource(r.sources.emission_factor, city);
  const baseCarbon = (annualKwh * factor) / 1000; // tCO₂e/yr
  const fmtNpv = (n: number) =>
    `${n < 0 ? "−" : ""}A$${Math.abs(Math.round(n)).toLocaleString()}`;

  const [traceOpen, setTraceOpen] = useState(false);

  return (
    <div style={{ borderTop: "0.5px solid var(--line)", paddingTop: 22, display: "flex", flexDirection: "column", gap: 26 }}>
      {/* ── The agent trace — right after the agents run, before the results ── */}
      <div>
        <button
          onClick={() => setTraceOpen((o) => !o)}
          className="btn"
          style={{ display: "inline-flex", alignItems: "center", gap: 7 }}
          aria-expanded={traceOpen}
        >
          <Activity className="h-4 w-4" style={{ color: accent }} />
          {traceOpen ? "Hide the agent trace" : "Open the agent trace"}
          <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)" }}>· this run</span>
        </button>
        {traceOpen && <TracePanel result={r} sims={sims} accent={accent} />}
      </div>

      {/* ── Results — the numbers + where the baseline lands vs the cohort ── */}
      <div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
          <h3 style={{ fontFamily: "var(--disp)", fontSize: 30, fontWeight: 700, letterSpacing: "-0.02em", color: "var(--tx)", margin: 0 }}>
            Results
          </h3>
        </div>

        {/* trust signals */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
          <span
            style={{
              display: "inline-flex", alignItems: "center", gap: 6, borderRadius: 8, padding: "5px 10px",
              fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--green)",
              border: "0.5px solid rgba(91,227,139,0.4)", background: "rgba(91,227,139,0.08)",
            }}
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            Reviewer approved
            {r.review.cohort_validated && r.review.within_cohort
              ? ` · baseline ${r.review.baseline_eui?.toFixed(0)} within the real cohort ${r.review.cohort_p25?.toFixed(0)}–${r.review.cohort_p75?.toFixed(0)}${r.review.cohort_n ? ` (n=${r.review.cohort_n})` : ""}`
              : r.review.cohort_validated === false
                ? " · illustrative (no verified cohort for this run)"
                : ""}
          </span>
          <ReceiptBadge color="accent">🔒 LLM never touched a number</ReceiptBadge>
        </div>

        {/* the simulated numbers */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
            gap: 1,
            overflow: "hidden",
            borderRadius: 12,
            border: "0.5px solid var(--line)",
            background: "var(--line)",
          }}
        >
          <MetricCard accent={accent} num={baseEui.toFixed(1)} label="baseline EUI (kWh/m²·yr)">
            {r.building.type} · {Math.round(area).toLocaleString()} m² · NCC zone {r.building.ncc_climate_zone}
          </MetricCard>
          <MetricCard accent={accent} num={Math.round(annualKwh).toLocaleString()} label="est. annual energy (kWh)">
            EnergyPlus baseline
          </MetricCard>
          <MetricCard
            accent={accent}
            num={
              <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Leaf className="h-5 w-5" />
                {baseCarbon.toFixed(1)}
              </span>
            }
            label="est. carbon (tCO₂e/yr)"
          >
            @ {factor.toFixed(2)} {gridLabel}
          </MetricCard>
          <MetricCard accent={accent} num={`${rec.energy_savings_pct.toFixed(1)}%`} label={`best measure — ${rec.scenario}`}>
            {(baseEui * (1 - rec.energy_savings_pct / 100)).toFixed(1)} kWh/m²·yr after this measure
          </MetricCard>
        </div>

        {/* Run telemetry — cost / tokens / latency for THIS run. Latency is real
            wall-clock; tokens are the real /health counter delta; cost is derived. */}
        {telemetry && (() => {
          const tk = telemetry.tokens;
          const tokensReal = typeof tk === "number";
          const tokensVal = tokensReal ? tk : 850;
          // Real per-provider cost from the /health counter delta; fall back to a
          // clearly-labelled estimate only if the cost counter didn't move.
          const costReal = typeof telemetry.costUsd === "number";
          const costUsd = costReal ? telemetry.costUsd! : (tokensVal / 1_000_000) * 5;
          const latS = telemetry.latencyMs / 1000;
          return (
            <div
              style={{
                display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
                gap: 1, overflow: "hidden", borderRadius: 12, marginTop: 1,
                border: "0.5px solid var(--line)", background: "var(--line)",
              }}
            >
              <MetricCard accent={accent} num={`${costReal ? "" : "~"}${fmtAud(costUsd)}`} label="cost of this run (AUD)">
                {costReal ? `measured · this run · per-provider priced (Sonnet + DeepSeek) · ${FX_NOTE}` : "est. — live cost counter unavailable this run"}
              </MetricCard>
              <MetricCard accent={accent} num={tokensReal ? tokensVal.toLocaleString() : `≈${tokensVal}`} label="LLM tokens used">
                {tokensReal ? "measured · this run (live counter)" : "typical per run (live count n/a)"}
              </MetricCard>
              <MetricCard accent={accent} num={`${latS.toFixed(0)}s`} label="latency (compute)">
                real end-to-end · excludes the human approval pause
              </MetricCard>
            </div>
          );
        })()}

        {/* where the baseline lands inside the real disclosed cohorts */}
        <div style={{ marginTop: 16 }}>
          <CohortStrips
            accent={accent}
            city={city}
            building={building}
            baselineEui={r.review.baseline_eui ?? baseEui}
            validated={r.review.cohort_validated}
          />
        </div>
      </div>

      {/* ── What-if scenarios ─────────────────────────────────────────────── */}
      <div>
        <SectionLabel title="What-if scenarios" />
        <MeasureBars result={r} baseEui={baseEui} accent={accent} />
      </div>
    </div>
  );
}

/* ── The run's agent trace — the real spans the pipeline emitted, streamed in-page
   over SSE. Sim spans carry THIS run's actual EnergyPlus EUIs + runtimes; the LLM
   spans show their real outputs; the cohort span shows the reconciled baseline. ── */
type TraceSpan = { name: string; kind: "llm" | "tool" | "human" | "verdict"; detail: string; bad?: boolean };

function TracePanel({ result, sims, accent }: { result: RunResult; sims: SimRow[]; accent: string }) {
  const r = result;
  const measures = r.scenarios.map((s) => s.scenario).join(" · ");
  const spans: TraceSpan[] = [
    { name: "retriever.classify", kind: "llm", detail: `${r.building.type} · NCC zone ${r.building.ncc_climate_zone}` },
    { name: "modeler.select_measures", kind: "llm", detail: measures || "—" },
    { name: "hitl.await_approval", kind: "human", detail: "approved (human click)" },
    ...sims.map((s): TraceSpan => {
      // The baseline sim's progress event carries the EUI computed against the
      // provisional floor area (before area reconciliation), so it reads ~10×
      // high. The Reviewer's baseline_eui is the reconciled, authoritative value —
      // use it here so the trace matches the Results headline. (annual_kwh is
      // absolute energy, not per-area, so it's already correct.)
      const eui =
        s.scenario === "baseline" && r.review.baseline_eui != null
          ? r.review.baseline_eui
          : s.eui;
      return {
        name: `tool · energyplus.run_sim · ${s.scenario}`,
        kind: "tool",
        detail:
          [
            eui != null ? `EUI ${eui.toFixed(1)}` : null,
            s.annual_kwh != null ? `${Math.round(s.annual_kwh).toLocaleString()} kWh` : null,
            s.runtime_s != null ? `${s.runtime_s.toFixed(1)}s` : null,
          ]
            .filter(Boolean)
            .join(" · ") || s.status,
      };
    }),
    { name: "analyzer.compute", kind: "tool", detail: "savings · payback · NPV · carbon" },
    {
      name: "tool · benchmark.cbd_cohort",
      kind: "tool",
      detail:
        r.review.baseline_eui != null
          ? `baseline ${r.review.baseline_eui.toFixed(0)} vs p25 ${r.review.cohort_p25?.toFixed(0) ?? "—"} / p75 ${r.review.cohort_p75?.toFixed(0) ?? "—"} → ${r.review.within_cohort ? "in range" : r.review.within_cohort === false ? "outside" : "illustrative"}`
          : "—",
    },
    {
      name: "reviewer.verdict",
      kind: "verdict",
      detail: r.review.approved ? "APPROVED · business case released" : `WITHHELD · route → ${r.review.route_to}`,
      bad: !r.review.approved,
    },
  ];

  const pill = (kind: TraceSpan["kind"]) =>
    kind === "llm"
      ? { t: "LLM", c: "var(--amber)", b: "rgba(230,180,91,.12)" }
      : kind === "human"
        ? { t: "human", c: "var(--cyan)", b: "rgba(45,212,191,.12)" }
        : kind === "verdict"
          ? { t: "gate", c: "var(--green)", b: "rgba(91,227,139,.12)" }
          : { t: "tool", c: "var(--dim)", b: "var(--s3)" };

  return (
    <div style={{ marginTop: 12, borderRadius: 12, border: "0.5px solid var(--line2)", background: "var(--s1)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "11px 14px", borderBottom: "0.5px solid var(--line)" }}>
        <Activity className="h-3.5 w-3.5" style={{ color: accent }} />
        <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--dim)" }}>
          agent trace · this run
        </span>
      </div>
      <div>
        {spans.map((s, i) => {
          const p = pill(s.kind);
          return (
            <div
              key={i}
              style={{
                display: "grid", gridTemplateColumns: "auto 1fr", gap: 12, alignItems: "baseline",
                padding: "8px 14px", borderTop: i ? "0.5px solid var(--line)" : "none",
              }}
            >
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--tx)" }}>
                <span style={{ fontSize: 11.5, letterSpacing: "0.04em", textTransform: "uppercase", padding: "1px 5px", borderRadius: 4, color: p.c, background: p.b }}>
                  {p.t}
                </span>
                {s.name}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, textAlign: "right", color: s.bad ? "var(--amber)" : s.kind === "verdict" ? "var(--green)" : "var(--dim)" }}>
                {s.detail}
              </span>
            </div>
          );
        })}
      </div>
      <div style={{ padding: "10px 14px", borderTop: "0.5px solid var(--line)", fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)", lineHeight: 1.55 }}>
        These are this run&apos;s real spans, streamed live from the pipeline — the sim steps carry the actual EnergyPlus
        EUIs + runtimes, and the cohort step shows the reconciled baseline the Reviewer gated on. The same run is
        recorded span-by-span in Langfuse (each graph node, with timings + outputs).
      </div>
    </div>
  );
}

/* Map an emission-source label ("NGA 2025 NSW") to its real NGA grid factor via the
   catalog (CITIES carry the verified per-state factor). Never LLM-authored. */
function factorFromSource(source: string, fallbackCity: CityKey): { factor: number; label: string } {
  const up = (source ?? "").toUpperCase();
  const match = CITIES.find((ci) => up.includes(ci.state.toUpperCase()));
  if (match) return { factor: match.electricityScope2, label: `${match.state} grid` };
  const fb = cityDef(fallbackCity);
  return { factor: fb.electricityScope2, label: `${fb.state} grid` };
}

/* ── Act 2 — the simulated baseline plotted inside the real disclosed cohorts
   for ALL FOUR cities. The selected city carries the "you" baseline marker; the
   other three show their real cohort IQR as comparison. All four cohorts are real
   (cbd.gov.au BEEC register, n ≥ 30). A run with no verified cohort still plots
   the marker but labels it illustrative rather than implying a pass/withhold. */
function CohortStrips({
  accent,
  city,
  building,
  baselineEui,
  validated,
}: {
  accent: string;
  city: CityKey;
  building: BuildingKey;
  baselineEui: number | null;
  validated: boolean;
}) {
  const rows = CITIES.map((ci) => ({ ci, cohort: cohortFor(ci.key, building) }))
    .filter((x) => x.cohort && x.cohort.verified);

  // Shared domain across every cohort + the baseline, so the four strips are
  // directly comparable. Pad ~12% so ticks and the marker aren't clipped.
  const vals: number[] = rows.flatMap((x) => [x.cohort!.p25, x.cohort!.p75]);
  if (baselineEui != null) vals.push(baselineEui);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const pad = (hi - lo) * 0.12 || 20;
  const dlo = lo - pad;
  const dhi = hi + pad;
  const pos = (v: number) => Math.max(0, Math.min(100, ((v - dlo) / (dhi - dlo)) * 100));

  const sel = cohortFor(city, building);
  const within =
    baselineEui != null && sel ? baselineEui >= sel.p25 && baselineEui <= sel.p75 : null;

  // Marker colour: only a VALIDATED run carries a pass/withhold verdict (green
  // in-cohort · amber out). An illustrative run (no verified cohort gated it) is
  // neutral — within-ness isn't a verdict there, so don't imply a rejection.
  const markerColor = !validated ? accent : within === false ? "var(--amber)" : "var(--green)";
  const markerGlow = !validated
    ? "rgba(91,156,255,0.55)"
    : within === false
      ? "rgba(230,180,91,0.6)"
      : "rgba(91,227,139,0.6)";

  const selLabel = cityDef(city).label;
  const verdict =
    baselineEui == null
      ? null
      : !validated
        ? { color: "var(--dim)", text: `${selLabel} · baseline EUI ${baselineEui.toFixed(1)} kWh/m²·yr — shown for reference; this run wasn't gate-validated (no verified cohort for it).` }
        : within
          ? { color: "var(--green)", text: `${selLabel} · baseline EUI ${baselineEui.toFixed(1)} kWh/m²·yr lands inside the real disclosed cohort${sel ? ` (p25 ${sel.p25.toFixed(0)}–p75 ${sel.p75.toFixed(0)}, n=${sel.n})` : ""} — validated, not calibrated.` }
          : { color: "var(--amber)", text: `${selLabel} · baseline EUI ${baselineEui.toFixed(1)} kWh/m²·yr is outside the cohort p25–p75 — the Reviewer withholds.` };

  return (
    <div
      style={{
        background: "var(--s1)",
        border: "0.5px solid var(--line2)",
        borderRadius: 14,
        padding: "20px 22px 18px",
      }}
    >
      <div style={{ fontSize: 14, fontWeight: 600, color: "var(--tx)", marginBottom: 4 }}>
        Your simulated baseline vs the real disclosed CBD office cohorts — all four cities
      </div>
      {verdict && (
        <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: verdict.color, marginBottom: 20, lineHeight: 1.5 }}>
          {verdict.text}
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        {rows.map(({ ci, cohort }) => {
          const co = cohort!;
          const isSel = ci.key === city;
          const left = pos(co.p25);
          const right = pos(co.p75);
          return (
            <div
              key={ci.key}
              style={{
                display: "grid",
                gridTemplateColumns: "160px 1fr",
                alignItems: "center",
                gap: 14,
                opacity: isSel ? 1 : 0.62,
              }}
            >
              <div>
                <div style={{ fontFamily: "var(--disp)", fontSize: 13, fontWeight: 600, color: isSel ? accent : "var(--tx)" }}>
                  {ci.label}
                  {isSel && (
                    <span style={{ marginLeft: 6, fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.05em", textTransform: "uppercase", color: accent }}>
                      selected
                    </span>
                  )}
                </div>
                <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)", marginTop: 3 }}>
                  n={co.n} · p25 {co.p25.toFixed(0)} · med {co.medianEui.toFixed(0)} · p75 {co.p75.toFixed(0)}
                </div>
              </div>

              {/* the strip */}
              <div style={{ position: "relative", height: 40 }}>
                {/* axis */}
                <div style={{ position: "absolute", top: 22, left: 0, right: 0, height: 6, borderRadius: 3, background: "var(--s2)" }} />
                {/* IQR band */}
                <div
                  style={{
                    position: "absolute",
                    top: 18,
                    left: `${left}%`,
                    width: `${Math.max(0.5, right - left)}%`,
                    height: 14,
                    background: isSel ? "rgba(91,156,255,0.22)" : "rgba(140,150,165,0.18)",
                    borderLeft: `1px solid ${isSel ? accent : "var(--line2)"}`,
                    borderRight: `1px solid ${isSel ? accent : "var(--line2)"}`,
                    borderRadius: 3,
                  }}
                />
                {/* median tick */}
                <div style={{ position: "absolute", top: 14, left: `${pos(co.medianEui)}%`, width: 1.5, height: 22, background: "var(--tx)" }} />
                {/* the "you" baseline marker — only on the selected city's strip */}
                {isSel && baselineEui != null && (
                  <div
                    style={{
                      position: "absolute",
                      top: -2,
                      left: `${pos(baselineEui)}%`,
                      width: 2,
                      height: 44,
                      background: markerColor,
                      boxShadow: `0 0 10px ${markerGlow}`,
                    }}
                  >
                    <span
                      style={{
                        position: "absolute",
                        top: -22,
                        left: "50%",
                        transform: "translateX(-50%)",
                        whiteSpace: "nowrap",
                        fontFamily: "var(--mono)",
                        fontSize: 11.5,
                        fontWeight: 700,
                        color: "var(--acc-ink)",
                        background: markerColor,
                        padding: "2px 7px",
                        borderRadius: 6,
                      }}
                    >
                      you · {baselineEui.toFixed(0)}
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)", marginTop: 16, lineHeight: 1.5 }}>
        Real cohorts · whole-building offices, mandatory-disclosure size band ·
        source cbd.gov.au BEEC / NABERS register (the real energy figure is the answer key — never an input).
      </div>
      <a
        href="https://www.cbd.gov.au/"
        target="_blank"
        rel="noopener noreferrer"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 7,
          marginTop: 10,
          fontFamily: "var(--mono)",
          fontSize: 12,
          color: accent,
          borderBottom: "1px solid rgba(91,156,255,0.4)",
          paddingBottom: 1,
        }}
      >
        <ExternalLink className="h-3.5 w-3.5" /> open the CBD disclosure register (cbd.gov.au)
      </a>
    </div>
  );
}

/* ── Act 3 — baseline vs each measure as a resulting-EUI bar. Resulting EUI =
   baseline × (1 − savings%), a deterministic transform of the real sim deltas. */
function MeasureBars({ result, baseEui, accent }: { result: RunResult; baseEui: number; accent: string }) {
  void accent;
  const rows = [
    { scenario: "baseline", eui: baseEui, pct: 0, payback: null as number | null, npv: null as number | null, best: false },
    ...result.scenarios.map((s) => ({
      scenario: s.scenario,
      eui: baseEui * (1 - s.energy_savings_pct / 100),
      pct: s.energy_savings_pct,
      payback: s.simple_payback_years,
      npv: s.npv_aud,
      best: s.scenario === result.recommended.scenario,
    })),
  ];
  const maxEui = Math.max(...rows.map((x) => x.eui));
  const fmtNpv = (n: number) => `${n < 0 ? "−" : ""}A$${Math.abs(Math.round(n)).toLocaleString()}`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {rows.map((row) => {
        const isBase = row.scenario === "baseline";
        const win = row.pct > 0;
        const lose = !isBase && row.pct <= 0;
        const fill = isBase
          ? "linear-gradient(90deg,#2a2f38,#3a414d)"
          : row.best
            ? "linear-gradient(90deg,#2563a8,var(--acc))"
            : win
              ? "linear-gradient(90deg,#1f7a4d,var(--green))"
              : "linear-gradient(90deg,#7a5a1f,var(--amber))";
        return (
          <div key={row.scenario} style={{ display: "grid", gridTemplateColumns: "150px 1fr 190px", alignItems: "center", gap: 14 }}>
            <div style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--tx)" }}>
              {row.scenario}
            </div>
            <div style={{ height: 26, background: "var(--s2)", borderRadius: 7, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${(row.eui / maxEui) * 100}%`, borderRadius: 7, background: fill, transition: "width 1s cubic-bezier(.2,0,0,1)" }} />
            </div>
            <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, textAlign: "right", fontWeight: 600, color: isBase ? "var(--dim)" : win ? "var(--green)" : "var(--amber)" }}>
              {isBase ? `${row.eui.toFixed(0)} EUI · reference` : win ? `▼ saves ${row.pct.toFixed(1)}% · ${row.eui.toFixed(0)} EUI` : `▲ +${Math.abs(row.pct).toFixed(1)}% · no saving`}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ReceiptBadge({ children, color }: { children: React.ReactNode; color: "green" | "accent" | "dim" }) {
  const styles =
    color === "green"
      ? { color: "var(--green)", border: "0.5px solid rgba(91,227,139,0.3)", background: "rgba(91,227,139,0.06)" }
      : color === "accent"
        ? { color: "var(--acc)", border: "0.5px solid rgba(91,156,255,0.3)", background: "rgba(91,156,255,0.06)" }
        : { color: "var(--dim)", border: "0.5px solid var(--line2)", background: "transparent" };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontFamily: "var(--mono)", fontSize: 11.5, padding: "6px 11px", borderRadius: 8, ...styles }}>
      {children}
    </span>
  );
}

function MetricCard({
  accent,
  num,
  label,
  children,
}: {
  accent: string;
  num: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ background: "#22242b", padding: 16 }}>
      <div
        style={{
          fontFamily: "var(--disp)",
          fontWeight: 600,
          fontSize: 26,
          letterSpacing: "-0.02em",
          color: accent,
          lineHeight: 1.1,
        }}
      >
        {num}
      </div>
      <div
        style={{
          marginTop: 6,
          fontFamily: "var(--mono)",
          fontSize: 11.5,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: "var(--dim)",
        }}
      >
        {label}
      </div>
      <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--dim)" }}>{children}</p>
    </div>
  );
}
