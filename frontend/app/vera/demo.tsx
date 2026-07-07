"use client";

// Live demo for Vera — the paced "day in the life" (follows Vera Demo Mockup v2).
//   GET  /demo/handoff   → approved_bills[] (10) + exceptions[] (2)   [seam-contract payload]
//   GET  /demo/catches   → the same catches WITH evidence: the real price sparkline,
//                          the quoted-vs-billed pair, and each flagged bill's real total
//   POST /demo/run/{sid} → per-bill gauntlet (duplicate-payment + prompt-injection refusals)
//
// Every number rendered is real backend output — nothing is fabricated client-side.
// Act 1 streams the month's 50 real supplier bills into an inbox, the 10 leaks surface as
// catch cards (price creep · over-quote · duplicate), and it closes on Vera's OWN scoreboard
// (Robin is shelved — no handoff beat).
//
// The v3 CasePage wraps this in a "Live Demo" panel that supplies the heading + honest
// note, so this component renders only the widget. Told in the owner's language — dollars
// caught and hours back — never "F1".

import { useCallback, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  Play,
  TrendingUp,
  FileWarning,
  CopyCheck,
  CheckCircle2,
  Loader2,
  Download,
  RotateCcw,
  Activity,
} from "lucide-react";
import { Byo } from "./byo";
import { fmtAud, FX_NOTE } from "@/lib/fx";

const ROSE = "#f1879b";

const money = (n: number, max = 2) => {
  // Show cents when the amount has them ($8.40, $790.60) but keep whole sums clean
  // ($791, $228,396) — avoids the "$8.4" that a flat minimumFractionDigits:0 produced.
  // Clamp min ≤ max: callers that pass max=0 (whole-dollar display) must not force 2
  // decimals, or Intl throws "maximumFractionDigits value is out of range".
  const v = Number(n ?? 0);
  const hasCents = Math.abs(v - Math.round(v)) > 1e-9;
  const min = Math.min(hasCents ? 2 : 0, max);
  return (
    "$" +
    v.toLocaleString(undefined, {
      minimumFractionDigits: min,
      maximumFractionDigits: max,
    })
  );
};

/* ── handoff (the seam payload: clean bills + leaks) ─────────────────────── */
type LineItem = { description: string; qty: number; unit: string; unit_price: number; line_total: number };
type ApprovedBill = {
  bill_id: string;
  supplier_name: string;
  invoice_number: string;
  currency: string;
  subtotal: number;
  tax: number;
  total: number;
  gl_code: string;
  line_items: LineItem[];
};
type Exception = {
  bill_id: string;
  supplier_name: string;
  type: string;
  detail: string;
  dollar_impact: number;
  status: string;
};
type Handoff = { approved_bills: ApprovedBill[]; exceptions: Exception[] };

/* ── catches WITH evidence (UI proof surfaces) ──────────────────────────── */
type Evidence = {
  sparkline?: number[];
  established_price?: number;
  previous_price?: number;
  new_price?: number;
  order_quantity?: number;
  over_per_unit?: number;
  pct_vs_previous?: number;
  pct_vs_established?: number;
  quoted_unit_price?: number;
  billed_unit_price?: number;
  quantity?: number;
  item_key?: string;
  // duplicate-payment evidence
  duplicate_of?: string;
  first_date?: string;
  second_date?: string;
  amount?: number;
};

// One place for the three catch types' label + icon, so the cards and the HITL panel agree.
const CATCH_LABEL: Record<string, string> = {
  price_creep: "Price creep",
  quote_mismatch: "Over quote",
  duplicate: "Duplicate",
};
// One hue per leak type so the grid scans at a glance (hex, not var — the cards use
// alpha suffixes like `${accent}14`). Amber = creep, cyan = over-quote, rose = duplicate.
const CATCH_ACCENT: Record<string, string> = {
  price_creep: "#E6B45B",
  quote_mismatch: "#2DD4BF",
  duplicate: "#F1879B",
};
function CatchIcon({ type, accent = "#E6B45B" }: { type: string; accent?: string }) {
  const Icon = type === "price_creep" ? TrendingUp : type === "duplicate" ? CopyCheck : FileWarning;
  return <Icon className="h-3.5 w-3.5 shrink-0" style={{ color: accent }} aria-hidden />;
}
type CatchUI = {
  bill_id: string;
  supplier_name: string;
  type: string;
  detail: string;
  dollar_impact: number;
  status: string;
  evidence: Evidence;
  item_label: string;
  bill_total: number;
  invoice_number: string;
};
type CatchesResp = { catches: CatchUI[]; history_count: number };

/* ── demo economics: real measured telemetry + the manual-review time-back ─── */
type Econ = {
  n_bills: number;
  model: string | null;
  measured: boolean;
  per_invoice: { tokens: number | null; cost_usd: number | null; latency_s: number };
  month: { tokens: number | null; cost_usd: number | null; latency_s: number; llm_calls: number };
  manual: { min_per_invoice: number; cost_per_invoice: number; source: string };
  week: {
    typical_invoices: number;
    manual_hrs: number;
    vera_hands_on_hrs: number;
    exceptions_reviewed: number;
    hours_back: number;
  };
};

type Row = { key: string; supplier: string; label: string; amount: number; flag: boolean; impact?: number };

/* AEM-style Results metric card (matches energy-modeller MetricCard + run-metrics). */
function ResCard({
  accent,
  num,
  label,
  children,
}: {
  accent: string;
  num: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <div style={{ background: "#22242b", padding: 16 }}>
      <div style={{ fontFamily: "var(--disp)", fontWeight: 600, fontSize: 26, letterSpacing: "-0.02em", color: accent, lineHeight: 1.1 }}>
        {num}
      </div>
      <div style={{ marginTop: 6, fontFamily: "var(--mono)", fontSize: "var(--fs-label-sm, 11.5px)", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--dim)" }}>
        {label}
      </div>
      <p style={{ margin: "8px 0 0", fontSize: "var(--fs-label-sm, 11.5px)", color: "var(--dim)" }}>{children}</p>
    </div>
  );
}

const RES_GRID: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
  gap: 1,
  overflow: "hidden",
  borderRadius: 12,
  border: "0.5px solid var(--line)",
  background: "var(--line)",
};

const reduceMotion = () =>
  typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/* Real price history as a mini bar chart — the climb ends in the accent-coloured current
   bill; the prior order is a lighter grey so "was $X → now $Y" reads at a glance. */
function Spark({ prices, accent = "#E6B45B" }: { prices: number[]; accent?: string }) {
  if (!prices || prices.length < 2) return null;
  const max = Math.max(...prices);
  const min = Math.min(...prices);
  const span = max - min || 1;
  return (
    <div className="flex items-end gap-1" style={{ height: 46 }} aria-hidden>
      {prices.map((p, i) => {
        const last = i === prices.length - 1;
        const prev = i === prices.length - 2;
        const h = 9 + ((p - min) / span) * 34;
        return (
          <div
            key={i}
            title={money(p)}
            style={{
              flex: "1 1 0", minWidth: 6, maxWidth: 15, height: h, borderRadius: "3px 3px 0 0",
              background: last ? accent : prev ? "rgba(255,255,255,0.28)" : "var(--s3)",
            }}
          />
        );
      })}
    </div>
  );
}

/* Over-quote: two proportional bars, quoted (grey) vs billed (accent) — the gap is the leak. */
function QuoteBars({ quoted, billed, accent }: { quoted: number; billed: number; accent: string }) {
  const max = Math.max(quoted, billed) || 1;
  const Row = ({ label, val, fill }: { label: string; val: number; fill: string }) => (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[9.5px] uppercase tracking-[0.08em] text-dim" style={{ width: 40 }}>{label}</span>
      <div className="h-2 flex-1 overflow-hidden rounded-full" style={{ background: "var(--s3)" }}>
        <div className="h-full rounded-full" style={{ width: `${(val / max) * 100}%`, background: fill }} />
      </div>
      <span className="font-mono text-[11px] tabular-nums text-tx" style={{ width: 52, textAlign: "right" }}>{money(val)}</span>
    </div>
  );
  return (
    <div className="flex flex-col gap-1.5">
      <Row label="quoted" val={quoted} fill="rgba(255,255,255,0.28)" />
      <Row label="billed" val={billed} fill={accent} />
    </div>
  );
}

/* Duplicate: the same amount on two invoices — two stacked receipt chips (paid + duplicate). */
function DupChips({ a, b, accent }: { a: string; b: string; accent: string }) {
  const Chip = ({ id, tag, strong }: { id: string; tag: string; strong?: boolean }) => (
    <div
      className="flex items-center justify-between rounded-md px-2.5 py-1.5"
      style={{ background: "var(--s2)", border: `0.5px solid ${strong ? `${accent}55` : "var(--line2)"}` }}
    >
      <span className="font-mono text-[11px] text-tx">{id}</span>
      <span className="font-mono text-[8.5px] uppercase tracking-[0.1em]" style={{ color: strong ? accent : "var(--dim)" }}>{tag}</span>
    </div>
  );
  return (
    <div className="flex flex-col gap-1">
      <Chip id={a} tag="paid" />
      <Chip id={b} tag="duplicate" strong />
    </div>
  );
}

// Illustrative per-bill pipeline (mirrors the Energy Modeller / AuditAgent
// TracePanel styling) — the security screen, field + line-item extraction, item
// normalisation, the six-month memory lookup, deterministic leak detection, and the
// pay/hold decision. This shows the SHAPE of what Vera runs on each bill. The day
// demo's catches, counts and dollar figures come from the real backend (see Results),
// and the DeepSeek extraction the economics card measures is a real, live call.
type VTraceKind = "llm" | "tool" | "gate";
function VeraTrace({
  acc, bills, memory, model, approved, catchCount, catchMix,
}: {
  acc: string; bills: number; memory: number; model: string; approved: number; catchCount: number; catchMix: string;
}) {
  const spans: { name: string; kind: VTraceKind; detail: string; bad?: boolean }[] = [
    { name: "tool · guard.screen", kind: "tool", detail: `${bills} bills · type / size / injection checks` },
    { name: "llm · extract.fields", kind: "llm", detail: `${model} · invoice#, vendor, date, totals` },
    { name: "llm · extract.line_items", kind: "llm", detail: "per line: qty · unit · unit price" },
    { name: "tool · normalize.items", kind: "tool", detail: "raw descriptions → canonical item keys" },
    { name: "tool · memory.lookup", kind: "tool", detail: `checked against ${memory} past bills` },
    { name: "gate · detect.leaks", kind: "gate", detail: `${catchCount} caught${catchMix ? ` · ${catchMix}` : ""}`, bad: catchCount > 0 },
    { name: "gate · decision", kind: "gate", detail: `${approved} auto-cleared · ${catchCount} held for review` },
  ];
  const pill = (k: VTraceKind) =>
    k === "llm" ? { t: "LLM", c: "var(--amber)", b: "rgba(230,180,91,.12)" }
      : k === "gate" ? { t: "gate", c: "var(--green)", b: "rgba(91,227,139,.12)" }
        : { t: "tool", c: "var(--dim)", b: "var(--s3)" };
  return (
    <div style={{ marginTop: 12, borderRadius: 12, border: "0.5px solid var(--line2)", background: "var(--s1)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "11px 14px", borderBottom: "0.5px solid var(--line)" }}>
        <Activity className="h-3.5 w-3.5" style={{ color: acc }} />
        <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--dim)" }}>
          the pipeline the Document Intelligence Agent runs on every bill
        </span>
      </div>
      <div>
        {spans.map((s, i) => {
          const p = pill(s.kind);
          return (
            <div key={i} style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 12, alignItems: "baseline", padding: "8px 14px", borderTop: i ? "0.5px solid var(--line)" : "none" }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--tx)" }}>
                <span style={{ fontSize: 11.5, letterSpacing: "0.04em", textTransform: "uppercase", padding: "1px 5px", borderRadius: 4, color: p.c, background: p.b }}>{p.t}</span>
                {s.name}
              </span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: s.bad ? "var(--amber)" : "var(--dim)", textAlign: "right" }}>{s.detail}</span>
            </div>
          );
        })}
      </div>
      <div style={{ padding: "10px 14px", borderTop: "0.5px solid var(--line)", fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)", lineHeight: 1.55 }}>
        The shape of the Document Intelligence Agent&apos;s per-bill pipeline. The day run above replays seeded results (its catches,
        counts and dollars are computed live by the backend); BYO uploads below run this pipeline for
        real — live DeepSeek extraction, recorded in Langfuse.
      </div>
    </div>
  );
}

export function Demo({ apiBase, accent }: { apiBase: string; accent?: string }) {
  const acc = accent ?? "var(--cyan)";

  const [launched, setLaunched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const [catches, setCatches] = useState<CatchUI[]>([]);
  const [memory, setMemory] = useState(270);
  const [inbox, setInbox] = useState<Row[]>([]);
  const [shown, setShown] = useState(0);
  const [showCards, setShowCards] = useState(false);
  const [showScore, setShowScore] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const [showApproval, setShowApproval] = useState(false); // HITL gate before Results
  const [econ, setEcon] = useState<Econ | null>(null);

  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  useEffect(() => clearTimers, []);

  const buildInbox = (h: Handoff, cs: CatchUI[]): Row[] => {
    const clean: Row[] = h.approved_bills.map((b) => {
      const li = b.line_items?.[0];
      const label = li ? `${li.description}${li.qty > 1 ? ` ×${li.qty}` : ""}` : b.invoice_number;
      return { key: b.bill_id, supplier: b.supplier_name, label, amount: b.total, flag: false };
    });
    // flagged bills land last — the money moment of the run
    const flagged: Row[] = cs.map((c) => ({
      key: c.bill_id,
      supplier: c.supplier_name,
      label: c.item_label || c.detail,
      amount: c.bill_total ?? 0,
      flag: true,
      impact: c.dollar_impact,
    }));
    return [...clean, ...flagged];
  };

  const startReveal = useCallback((rows: Row[]) => {
    if (reduceMotion()) {
      setShown(rows.length);
      setShowCards(true);
      setShowApproval(true);
      return;
    }
    // Batch-reveal so the full month (~50 bills) streams in ~3s instead of ~18s.
    const n = rows.length;
    const perTick = Math.max(1, Math.ceil(n / 22));
    const interval = 150;
    let tick = 1;
    for (let c = perTick; c < n; c += perTick, tick++) {
      const sc = c;
      timers.current.push(setTimeout(() => setShown(sc), 200 + tick * interval));
    }
    const endT = 200 + (tick + 1) * interval;
    timers.current.push(setTimeout(() => setShown(n), endT));
    timers.current.push(setTimeout(() => setShowCards(true), endT + 400));
    // Results are gated behind the human-in-the-loop approval, not auto-shown.
    timers.current.push(setTimeout(() => setShowApproval(true), endT + 1000));
  }, []);

  const loadDemo = useCallback(async () => {
    setLaunched(true);
    setLoading(true);
    setErr(null);
    clearTimers();
    setShown(0);
    setShowCards(false);
    setShowScore(false);
    setShowApproval(false);
    try {
      const [hr, cr] = await Promise.all([
        fetch(`${apiBase}/demo/handoff`),
        fetch(`${apiBase}/demo/catches`),
      ]);
      if (!hr.ok) throw new Error(`HTTP ${hr.status}`);
      if (!cr.ok) throw new Error(`HTTP ${cr.status}`);
      const h = (await hr.json()) as Handoff;
      const c = (await cr.json()) as CatchesResp;
      setHandoff(h);
      setCatches(c.catches);
      setMemory(c.history_count || 270);
      const rows = buildInbox(h, c.catches);
      setInbox(rows);
      startReveal(rows);
      // Real cost/latency/tokens + the time-back — measured on one live extraction,
      // projected to the month. Non-blocking: the cards fill in by the time the
      // Results section reveals (~2s later). Never fabricated if the fetch fails.
      fetch(`${apiBase}/demo/economics`)
        .then((r) => (r.ok ? r.json() : null))
        .then((e: Econ | null) => e && setEcon(e))
        .catch(() => {});
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not reach the backend");
    } finally {
      setLoading(false);
    }
  }, [apiBase, startReveal]);

  const replay = () => {
    if (!inbox.length) return;
    clearTimers();
    setShown(0);
    setShowCards(false);
    setShowScore(false);
    setShowApproval(false);
    startReveal(inbox);
  };

  /* derived (running totals come straight from the revealed real bills) */
  const shownRows = inbox.slice(0, shown);
  const cleared = shownRows.filter((r) => !r.flag).reduce((s, r) => s + r.amount, 0);
  const caught = shownRows.filter((r) => r.flag).reduce((s, r) => s + (r.impact || 0), 0);
  const totalCaught = catches.reduce((s, c) => s + c.dollar_impact, 0);
  const creepingSuppliers = new Set(
    catches.filter((c) => c.type === "price_creep").map((c) => c.supplier_name),
  ).size;
  // catch mix by type — the demo's variety headline (creep · over-quote · duplicate)
  const catchMix = ["price_creep", "quote_mismatch", "duplicate"]
    .map((t) => ({ n: catches.filter((c) => c.type === t).length, label: CATCH_LABEL[t].toLowerCase() }))
    .filter((x) => x.n > 0)
    .map((x) => `${x.n} ${x.label}`)
    .join(" · ");

  /* ── Pre-launch: one deliberate CTA, the mockup's "Run the day" ──────────── */
  if (!launched) {
    return (
      <div className="rounded-2xl border border-line bg-s1 p-6">
        <p className="text-sm leading-relaxed text-dim">
          The demo opens with six months of Lola&apos;s Café bills already in memory — that history is
          what lets the Document Intelligence Agent flag a price that quietly crept up and catch a bill above its agreed quote.
          Press play and watch a full month of <strong className="text-tx">50 supplier bills</strong> come in:
          most clear automatically, and the Document Intelligence Agent catches the ones that don&apos;t.
        </p>
        <p className="mt-2 text-xs leading-relaxed text-dim" style={{ opacity: 0.8 }}>
          Lola&apos;s Café is a sample business built for this demo — the 50 bills and the six-month
          history are realistic constructed data (download them below); the catches, counts and dollar
          figures are all computed live by the backend.
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button type="button" onClick={loadDemo} className="btn pri justify-center" aria-label="Run the day">
            <Play className="h-4 w-4" aria-hidden />
            Run the day
          </button>
          <a className="btn" href={`${apiBase}/demo/bills.zip`} download>
            <Download className="h-4 w-4" aria-hidden />
            Download the 50 sample bills
          </a>
          <a className="btn" href={`${apiBase}/demo/memory.txt`} download>
            <Download className="h-4 w-4" aria-hidden />
            See the 6-month memory (.txt)
          </a>
        </div>
        <p className="mt-2 font-mono text-[11px] text-dim">
          the exact files the Document Intelligence Agent reads · and the price history it remembers
        </p>
      </div>
    );
  }

  return (
    <div>
      <style>{`@keyframes veraRise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}`}</style>

      {/* ══ Section 1 — Vera catches money across the month's 50 bills ══ */}
      <h3 className="mb-4" style={{ fontFamily: "var(--disp)", fontSize: "var(--fs-display-sm, 24px)", fontWeight: 700, letterSpacing: "-0.01em", color: acc }}>
        <span style={{ color: acc }}>①</span> The Document Intelligence Agent catches money in 50 supplier bills
      </h3>

      {/* ── HUD: memory + running money, counts up as the real bills land ── */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <div className="flex items-center gap-2">
            <span
              style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--green)" }}
              aria-hidden
            />
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-dim">
              {loading ? "loading this café's history…" : `checked against ${memory} past bills`}
            </span>
          </div>
          {/* Keep the sample-bills download available during + after the run, not just pre-launch. */}
          <a className="btn" href={`${apiBase}/demo/bills.zip`} download>
            <Download className="h-3.5 w-3.5" aria-hidden />
            Download the 50 sample bills
          </a>
        </div>
        <div className="flex gap-5">
          <div className="text-right">
            <div className="font-display text-[22px] font-semibold tabular-nums" style={{ color: acc }}>
              {money(cleared, 0)}
            </div>
            <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-dim">cleared to pay</div>
          </div>
          <div className="text-right">
            <div className="font-display text-[22px] font-semibold tabular-nums" style={{ color: "var(--amber)" }}>
              {money(caught, 0)}
            </div>
            <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-dim">caught before payment</div>
          </div>
        </div>
      </div>

      {err && (
        <div
          className="mt-4 flex items-center justify-between gap-3 rounded-xl border p-3 text-sm"
          style={{ borderColor: "rgba(241,135,155,0.4)", background: "rgba(241,135,155,0.08)" }}
          role="alert"
        >
          <span style={{ color: ROSE }}>Couldn&apos;t load the café — {err}.</span>
          <button onClick={loadDemo} className="btn">
            Retry
          </button>
        </div>
      )}

      {/* ── the month's bills, streaming into an inbox ── */}
      {!err && (
        <div className="mt-4 overflow-hidden rounded-xl border border-line">
          <div className="flex items-center justify-between border-b border-line bg-s2 px-4 py-2">
            <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-dim">Today&apos;s inbox</span>
            <span className="font-mono text-[11px] text-dim">
              {shown} / {inbox.length || 50}
            </span>
          </div>
          <div className="max-h-[380px] overflow-y-auto">
            {shownRows.map((r) => (
              <div
                key={r.key}
                className="items-center border-b border-line px-4 py-2 text-sm last:border-0"
                style={{
                  display: "grid",
                  gap: 12,
                  gridTemplateColumns: "18px 1fr auto",
                  animation: "veraRise .28s ease both",
                  background: r.flag ? "rgba(230,180,91,0.06)" : undefined,
                }}
              >
                <span aria-hidden>
                  {r.flag ? (
                    <span style={{ color: "var(--amber)" }}>⚠</span>
                  ) : (
                    <CheckCircle2 className="h-4 w-4" style={{ color: "var(--green)" }} />
                  )}
                </span>
                <span className="truncate text-tx">
                  {r.supplier} <span className="text-dim">· {r.label}</span>
                </span>
                <span className="tabular-nums text-tx">{money(r.amount)}</span>
              </div>
            ))}
            {shown === 0 && (
              <div className="flex items-center gap-2.5 px-4 py-3 text-sm text-dim">
                <Loader2 className="h-4 w-4 animate-spin" style={{ color: acc }} aria-hidden />
                Reading this month&apos;s bills against six months of memory…
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── what Vera caught across the month — colour-coded by leak type, in dollars ── */}
      {showCards && catches.length > 0 && (
        <div className="mt-6" style={{ animation: "veraRise .4s ease both" }}>
          <style>{`
            .vcatch{transition:transform .2s cubic-bezier(.2,0,0,1),box-shadow .2s,border-color .2s}
            .vcatch:hover{transform:translateY(-2px);border-color:var(--vc-bd);box-shadow:0 18px 44px -26px var(--vc-glow)}
            @media(prefers-reduced-motion:reduce){.vcatch{transition:none}.vcatch:hover{transform:none;box-shadow:none}}
          `}</style>
          <div className="mb-3 flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
            <span className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.14em]" style={{ color: "var(--amber)" }}>
              <span style={{ width: 6, height: 6, borderRadius: 99, background: "var(--amber)" }} />
              What the Document Intelligence Agent caught
            </span>
            <span className="font-mono text-[11px] text-dim">
              {catches.length} leak{catches.length === 1 ? "" : "s"} in {inbox.length || 50} bills · flagged for you, not paid
            </span>
          </div>
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(264px, 1fr))" }}>
            {catches.map((c, i) => {
              const accent = CATCH_ACCENT[c.type] ?? "#E6B45B";
              const ev = c.evidence ?? {};
              return (
                <article
                  key={i}
                  className="vcatch overflow-hidden rounded-2xl"
                  style={{
                    background: "linear-gradient(180deg, var(--s1), rgba(255,255,255,0.015))",
                    border: "0.5px solid var(--line)",
                    ["--vc-bd" as string]: `${accent}88`,
                    ["--vc-glow" as string]: `${accent}55`,
                  } as CSSProperties}
                >
                  <div style={{ height: 3, background: `linear-gradient(90deg, ${accent}, ${accent}22 60%, transparent)` }} />
                  <div className="p-4">
                    {/* header: type chip · money hero */}
                    <div className="flex items-start justify-between gap-3">
                      <span
                        className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1"
                        style={{ background: `${accent}14`, border: `0.5px solid ${accent}33` }}
                      >
                        <CatchIcon type={c.type} accent={accent} />
                        <span className="font-mono text-[10px] font-medium uppercase tracking-[0.1em]" style={{ color: accent }}>
                          {CATCH_LABEL[c.type] ?? "Flagged"}
                        </span>
                      </span>
                      <div className="text-right">
                        <div className="font-display font-semibold tabular-nums" style={{ fontSize: 26, lineHeight: 1, letterSpacing: "-0.02em", color: accent }}>
                          {money(c.dollar_impact)}
                        </div>
                        <div className="mt-1 font-mono text-[9px] uppercase tracking-[0.09em] text-dim">saved · before you pay</div>
                      </div>
                    </div>
                    {/* who + what */}
                    <div className="mt-3">
                      <div className="font-display font-semibold text-tx" style={{ fontSize: 16, letterSpacing: "-0.01em" }}>{c.supplier_name}</div>
                      <div className="font-mono text-[11px] text-dim">{c.item_label}</div>
                    </div>
                    {/* evidence — a real visual per leak type */}
                    <div className="mt-3 pt-3" style={{ borderTop: "0.5px solid var(--line)" }}>
                      {c.type === "price_creep" && ev.sparkline && (
                        <>
                          <Spark prices={ev.sparkline} accent={accent} />
                          <div className="mt-2 font-mono text-[11px] text-dim">
                            was {money(ev.previous_price ?? 0)} → now <span className="text-tx">{money(ev.new_price ?? 0)}</span>
                            {ev.pct_vs_previous != null ? ` · +${Math.round(ev.pct_vs_previous * 100)}%` : ""} · ×{ev.order_quantity ?? 0}
                          </div>
                        </>
                      )}
                      {c.type === "quote_mismatch" && ev.quoted_unit_price != null && (
                        <>
                          <QuoteBars quoted={ev.quoted_unit_price} billed={ev.billed_unit_price ?? 0} accent={accent} />
                          <div className="mt-2 font-mono text-[11px] text-dim">
                            {money(ev.over_per_unit ?? 0)} over × {ev.quantity ?? 0} = <span className="text-tx">{money(c.dollar_impact)}</span>
                          </div>
                        </>
                      )}
                      {c.type === "duplicate" && ev.duplicate_of && (
                        <>
                          <DupChips a={ev.duplicate_of} b={c.invoice_number} accent={accent} />
                          <div className="mt-2 font-mono text-[11px] text-dim">
                            same {money(ev.amount ?? c.dollar_impact)} billed twice · pay once
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Human-in-the-loop: a person signs off before anything is paid ──────
          An INLINE panel in the flow (not a blocking overlay) right before Results —
          it carries the hard evidence for each flag (the numbers + why), then gates
          the Results on the owner's approval. */}
      {showApproval && !showScore && (
        <div
          className="mt-5 rounded-2xl border p-4"
          style={{ borderColor: `${acc}66`, background: `${acc}0d`, animation: "veraRise .3s ease both" }}
          role="region"
          aria-label="Human approval required before payment"
        >
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="font-mono text-[11px] uppercase tracking-[0.12em]" style={{ color: acc }}>⏸ Human in the loop</span>
            <span className="font-mono text-[11px] text-dim">
              {handoff?.approved_bills.length ?? 0} clean · {catches.length} held · {money(totalCaught, 0)} caught
            </span>
          </div>
          <p className="mt-1.5 text-sm text-tx">
            <strong>Approve this month before anything is paid.</strong>{" "}
            <span className="text-dim">The Document Intelligence Agent cleared {handoff?.approved_bills.length ?? 0} bills and is holding {catches.length} for you — here is exactly what it flagged and why:</span>
          </p>

          {/* hard evidence, per flag */}
          <ul className="mt-3 space-y-2">
            {catches.map((c, i) => (
              <li key={i} className="rounded-xl border border-line bg-s1 p-3">
                <div className="flex items-center gap-2">
                  <CatchIcon type={c.type} />
                  <span className="text-sm font-semibold text-tx">{c.supplier_name}</span>
                  <span className="text-xs text-dim">· {c.item_label}</span>
                  <span className="ml-auto font-display text-lg font-semibold tabular-nums" style={{ color: "var(--amber)" }}>
                    {money(c.dollar_impact)}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-relaxed text-dim">{c.detail}</p>
                {c.type === "price_creep" && c.evidence?.sparkline && (
                  <div className="mt-2 flex items-center gap-3">
                    <Spark prices={c.evidence.sparkline} />
                    <span className="font-mono text-[11px] text-dim">
                      {money(c.evidence.previous_price ?? 0)} → {money(c.evidence.new_price ?? 0)} last order
                      {c.evidence.pct_vs_previous != null ? ` · +${Math.round(c.evidence.pct_vs_previous * 100)}%` : ""}
                    </span>
                  </div>
                )}
                {c.type === "quote_mismatch" && c.evidence?.quoted_unit_price != null && (
                  <p className="mt-1 font-mono text-[11px] text-dim">
                    quoted {money(c.evidence.quoted_unit_price)} → billed {money(c.evidence.billed_unit_price ?? 0)} × {c.evidence.quantity ?? 0} = {money(c.dollar_impact)} over
                  </p>
                )}
                {c.type === "duplicate" && c.evidence?.duplicate_of && (
                  <p className="mt-1 font-mono text-[11px] text-dim">
                    same {money(c.evidence.amount ?? c.dollar_impact)} on {c.invoice_number} &amp; {c.evidence.duplicate_of} → pay once, not twice
                  </p>
                )}
              </li>
            ))}
          </ul>

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button className="btn pri" onClick={() => setShowScore(true)} aria-label="Approve the clean bills and see results">
              <CheckCircle2 className="h-4 w-4" aria-hidden />
              Approve clean bills · hold the flags
            </button>
            <span className="font-mono text-[11px] text-dim">the {catches.length} flagged stay held for you · nothing auto-paid</span>
          </div>
        </div>
      )}

      {/* ── Results — Lola's month + the time a typical week gives back ─────────
          Matches the Agentic Energy Modeller "Results" section: a bold heading +
          trust badges + metric-card grids. Outcomes are real backend output; cost +
          tokens are measured on one live extraction and projected across the month's
          bills, while latency is the real per-bill figure (it doesn't sum across bills). */}
      {showScore && (
        <div className="mt-5" style={{ animation: "veraRise .45s ease both" }}>
          {/* Per-bill pipeline — same visual pattern as the agentic projects, shown right before Results. */}
          <div style={{ marginBottom: 16 }}>
            <button
              onClick={() => setTraceOpen((o) => !o)}
              className="btn"
              style={{ display: "inline-flex", alignItems: "center", gap: 7 }}
              aria-expanded={traceOpen}
            >
              <Activity className="h-4 w-4" style={{ color: acc }} />
              {traceOpen ? "Hide the pipeline" : "See how the Document Intelligence Agent reads a bill"}
            </button>
            {traceOpen && (
              <VeraTrace
                acc={acc}
                bills={inbox.length || 50}
                memory={memory}
                model={econ?.model ?? "deepseek-chat"}
                approved={handoff?.approved_bills.length ?? 0}
                catchCount={catches.length}
                catchMix={catchMix}
              />
            )}
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
            <h3 style={{ fontFamily: "var(--disp)", fontSize: "var(--fs-display-md, 30px)", fontWeight: 700, letterSpacing: "-0.02em", color: "var(--tx)", margin: 0 }}>
              Results
            </h3>
          </div>

          {/* trust signals */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 7, borderRadius: 9, padding: "7px 13px", fontFamily: "var(--mono)", fontWeight: 600, fontSize: "var(--fs-ui, 14px)", color: acc, border: `0.5px solid ${acc}55`, background: `${acc}14` }}>
              ✓ 94.3% field-extraction accuracy · tested on 28 real invoices
            </span>
          </div>

          {/* outcomes — real from the run */}
          <div style={RES_GRID}>
            <ResCard accent="var(--amber)" num={money(totalCaught, 0)} label="saved before you pay these bills">
              {catches.length} leak{catches.length === 1 ? "" : "s"} — {catchMix || `${creepingSuppliers} creeping`} · the overcharge on these invoices, not a yearly estimate
            </ResCard>
            <ResCard accent={acc} num={String(handoff?.approved_bills.length ?? 0)} label="bills auto-cleared">
              read, checked & approved to pay — hands-off
            </ResCard>
          </div>

          {/* cost & speed — measured per invoice, projected across the month's bills */}
          <div style={{ ...RES_GRID, marginTop: 1 }}>
            <ResCard accent={acc} num={econ ? fmtAud(econ.month.cost_usd) : "—"} label="cost this month (AUD)">
              {econ ? `measured per invoice × ${econ.n_bills} bills · ${econ.model} · ${FX_NOTE}` : "…"}
            </ResCard>
            <ResCard accent={acc} num={econ ? `${econ.per_invoice.latency_s.toFixed(1)}s` : "—"} label="model latency per bill">
              {econ ? `real wall-clock · one live ${econ.model} extraction` : "…"}
            </ResCard>
            <ResCard accent={acc} num={econ && econ.month.tokens != null ? econ.month.tokens.toLocaleString() : "—"} label="LLM tokens used">
              {econ ? `measured per invoice × ${econ.n_bills} bills` : "…"}
            </ResCard>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button onClick={replay} className="btn" aria-label="Replay the day">
              <RotateCcw className="h-4 w-4" aria-hidden />
              Replay the day
            </button>
            <span className="font-mono text-[11px] text-dim">
              {handoff?.approved_bills.length} clean bills approved · {catches.length} flagged for the owner
            </span>
          </div>
        </div>
      )}

      {/* ══ Section 2 — the demoer uploads their own bills (field extraction) ══ */}
      <div className="mt-8 border-t border-line pt-6">
        <h3 className="mb-4" style={{ fontFamily: "var(--disp)", fontSize: "var(--fs-display-sm, 24px)", fontWeight: 700, letterSpacing: "-0.01em", color: acc }}>
          <span style={{ color: acc }}>②</span> Upload your own bills
        </h3>
        <Byo apiBase={apiBase} accent={acc} />
      </div>
    </div>
  );
}
