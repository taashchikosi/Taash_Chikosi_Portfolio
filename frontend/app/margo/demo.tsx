"use client";

/**
 * /margo live demo — the 4-step journey, laid out to match mockups/margo-demo-mockup.html.
 * Rendered as the body of the shared CasePage "Live Demo" panel. Nothing here is scripted:
 * every number is computed by the live engine over The Wren's real data.
 *
 *   Step 1  See the data        — download the full dataset (reproduce any number yourself)
 *   Step 2  Margo reads it       — Square ✓ · QuickBooks ✓ + GET /digest insight cards (the hook)
 *   Step 3  Tap for receipts     — explainer; each card opens inline to POST /receipts (the proof)
 *   Step 4  Or just ask          — owner chips + free-form → POST /ask (5 statuses); BYO closer
 *
 * Layout = the mockup's numbered .step rail. The digest (a code-computed GET, no LLM) loads on
 * mount so the page reads documents-first like the mockup; the LLM /ask only fires on a
 * deliberate chip/Ask click (no auto-fire of the model). Real /ask ~7s (generous timeout,
 * visible thinking state); blocked/out_of_scope return null sql/rows — never throws on null.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Activity } from "lucide-react";
import { RunMetrics, type RunTelemetry } from "@/components/run-metrics";

// ── API shapes (authoritative: engine app/agent.py · main.py · watchdog.py) ──────
type AskStatus = "answered" | "blocked" | "clarify" | "out_of_scope" | "failed";

type AskResponse = {
  question?: string;
  status: AskStatus;
  sql: string | null;
  readback: string | null;
  columns: string[] | null;
  rows: (string | number | null)[][] | null;
  receipts: Record<string, string | number | null>[] | null;
  confidence: string;
  consistency: { score: number; n_agree: number; n_samples: number } | null;
  note: string | null;
  latency_ms: number;
  run_telemetry?: RunTelemetry | null;
};

type DigestCard = {
  key: string;
  title: string;
  dollar_value: number;
  plain_english: string;
  drilldown_query: string;
};
type Digest = { business: string; cards: DigestCard[]; top3: DigestCard[] };

type ReceiptsResponse = {
  columns: string[];
  rows: (string | number | null)[][];
  n: number;
  sql: string;
  latency_ms: number;
};

type ByoSession = {
  token: string;
  format: string;
  columns: string[];
  n_rows: number;
  scope_note: string;
  queries_allowed: number;
};

const CSV_HREF = "/margo/the-wren_full-data.csv";
const TIMEOUT_MS = 25000; // real /ask ~7s — spec: do not time out under 25s

// Icon per digest check key (engine watchdog.py). Falls back to a chart glyph.
const CARD_ICON: Record<string, string> = {
  margin_mix: "🕯️",
  dead_stock: "📦",
  stockout_movers: "🔁",
  staffing_peak: "⏰",
  wow_revenue: "📈",
};

// Owner-language starter chips — each VERIFIED to return `answered` on the engine.
// (The red-team refusal beat still fires if a visitor TYPES a destructive query; this
// ask panel is for questions only, so no destructive chip is offered.)
const CHIPS: { label: string; q: string; kind: "real" | "redteam" }[] = [
  { label: "Which category makes the most profit?", q: "Which category makes the most profit?", kind: "real" },
  { label: "What didn't sell last month?", q: "What didn't sell last month?", kind: "real" },
  { label: "Top 5 products by revenue", q: "top 5 products by revenue", kind: "real" },
];

const fmtMoney = (n: number) => "$" + Math.round(n).toLocaleString("en-US");

// Display a table cell without leaking float noise (e.g. 2336.5499999999997 → "2,336.55").
// Integers keep no decimals; non-integers round to ≤2 dp with thousands separators. No "$" —
// numeric columns aren't all money (qty, counts), so the column header carries the unit.
const fmtCell = (cell: string | number | null): string => {
  if (cell === null) return "—";
  if (typeof cell === "number" && Number.isFinite(cell)) {
    return Number.isInteger(cell)
      ? cell.toLocaleString("en-US")
      : Number(cell.toFixed(2)).toLocaleString("en-US", { maximumFractionDigits: 2 });
  }
  return String(cell);
};

async function api<T>(
  url: string,
  init: RequestInit,
  signal: AbortSignal,
): Promise<{ ok: boolean; status: number; data: T | null }> {
  const res = await fetch(url, { ...init, signal });
  let data: T | null = null;
  try {
    data = (await res.json()) as T;
  } catch {
    data = null;
  }
  return { ok: res.ok, status: res.status, data };
}

// ─────────────────────────────────────────────────────────────────────────────
export function Demo({ apiBase, accent }: { apiBase: string; accent?: string }) {
  const acc = accent ?? "var(--acc)";
  const [digest, setDigest] = useState<Digest | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "done" | "error">("loading");

  useEffect(() => {
    // Documents-first like the mockup: load the digest on mount. It is code-computed
    // (no LLM) — the model is only ever called on a deliberate /ask in Step 4.
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    (async () => {
      try {
        const d = await api<Digest>(`${apiBase}/digest`, { method: "GET" }, ctrl.signal);
        if (!d.ok || !d.data) throw new Error("digest");
        setDigest(d.data);
        setLoadState("done");
      } catch {
        setLoadState("error");
      }
    })();
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [apiBase]);

  return (
    <div>
      {/* flow orientation (mockup .flowmeta) */}
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11.5,
          color: acc,
          fontWeight: 700,
          textTransform: "uppercase",
          letterSpacing: "0.1em",
          marginBottom: 24,
        }}
      >
        Demo flow · 4 simple steps
      </div>

      {/* Step 1 — see the data (the realism proof) */}
      <Step n={1} title="See the data the Retail Analyst Agent is reading">
        <VerifyDownload />
      </Step>

      {/* Step 2 — Margo reads it (connection strip + the Monday digest) */}
      <Step n={2} title="The Retail Analyst Agent reads it and tells you what matters">
        {loadState === "loading" && (
          <div className="status">
            <span className="d live" style={{ background: acc }} />
            Reading the shop&apos;s data…
          </div>
        )}
        {loadState === "error" && (
          <OfflineNote>
            Couldn&apos;t reach the Retail Analyst Agent&apos;s engine to load the live digest. The demo talks to a real
            backend; if it&apos;s cold, retry in a moment.
          </OfflineNote>
        )}
        {loadState === "done" && digest && (
          <>
            <p style={{ margin: "0 0 12px", color: "var(--dim)", fontSize: 13, lineHeight: 1.55 }}>
              <strong style={{ color: "var(--acc)" }}>→</strong> <strong>Tap any card for the receipts</strong> — every number opens to the actual
              rows behind it (the proof). The SQL is one click further, for anyone who wants it.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 11 }}>
              {digest.cards.map((c) => (
                <DigestCardRow key={c.key} card={c} apiBase={apiBase} acc={acc} />
              ))}
            </div>
          </>
        )}
      </Step>

      {/* Step 3 — ask anything in plain English */}
      <Step
        n={3}
        title="Or just ask in plain English"
        lead="No SQL, no menus. Free-form questions prove it isn't canned — every answer comes back with the rows behind it."
      >
        <AskPanel apiBase={apiBase} acc={acc} />
      </Step>

      {/* Step 4 — bring your own file */}
      <Step
        n={4}
        title="Bring your own file"
        lead="Upload your own Square or QuickBooks export — the Retail Analyst Agent reads it in-session and answers from your rows."
        last
      >
        <ByoCloser apiBase={apiBase} acc={acc} />
      </Step>
    </div>
  );
}

// ── The numbered step rail (mockup .step / .num) ──────────────────────────────
function Step({
  n,
  title,
  lead,
  last,
  children,
}: {
  n: number;
  title: string;
  lead?: string;
  last?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div style={{ position: "relative", paddingLeft: 54, paddingBottom: last ? 0 : 34 }}>
      {!last && (
        <span
          style={{
            position: "absolute",
            left: 17,
            top: 38,
            bottom: 0,
            width: 2,
            background: "var(--line)",
          }}
        />
      )}
      <span
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: 36,
          height: 36,
          borderRadius: "50%",
          background: "var(--s3)",
          border: "0.5px solid var(--line2)",
          display: "grid",
          placeItems: "center",
          fontWeight: 700,
          fontSize: 15,
          color: "var(--btn-acc, var(--acc))",
          zIndex: 1,
        }}
      >
        {n}
      </span>
      <h2 style={{ fontSize: 18, letterSpacing: "-0.01em", color: "var(--btn-acc, var(--acc))", marginBottom: lead ? 4 : 14 }}>
        {title}
      </h2>
      {lead && (
        <p style={{ color: "var(--dim)", fontSize: 13, lineHeight: 1.55, marginBottom: 16 }}>{lead}</p>
      )}
      {children}
    </div>
  );
}

// ── Step 1 body ────────────────────────────────────────────────────────────────
function VerifyDownload() {
  return (
    <a
      href={CSV_HREF}
      download
      style={{
        display: "flex",
        alignItems: "center",
        gap: 13,
        textDecoration: "none",
        background: "rgba(95,208,138,0.10)",
        border: "0.5px solid rgba(95,208,138,0.32)",
        borderRadius: 12,
        padding: "13px 16px",
      }}
    >
      <span style={{ fontSize: 20 }}>📊</span>
      <span style={{ display: "flex", flexDirection: "column", lineHeight: 1.4 }}>
        <b style={{ fontSize: 14, color: "var(--tx)" }}>Download the full dataset</b>
        <span style={{ fontSize: 12, color: "var(--dim)" }}>
          20,960 sales · 1,201 products · every row the Retail Analyst Agent queries — check it in Excel
        </span>
      </span>
      <span style={{ marginLeft: "auto", color: "var(--green)", fontSize: 17 }}>⬇</span>
    </a>
  );
}

// ── Step 2 body ────────────────────────────────────────────────────────────────
function DigestCardRow({ card, apiBase, acc }: { card: DigestCard; apiBase: string; acc: string }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [receipts, setReceipts] = useState<ReceiptsResponse | null>(null);
  const [showSql, setShowSql] = useState(false);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (state === "done" || state === "loading") return;
    setState("loading");
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const r = await api<ReceiptsResponse>(
        `${apiBase}/receipts`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: card.drilldown_query }),
        },
        ctrl.signal,
      );
      if (!r.ok || !r.data) throw new Error("receipts");
      setReceipts(r.data);
      setState("done");
    } catch {
      setState("error");
    } finally {
      clearTimeout(timer);
    }
  }

  return (
    <div
      style={{
        background: "var(--s1)",
        border: "0.5px solid var(--line)",
        borderRadius: 12,
        overflow: "hidden",
      }}
    >
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="digest-row"
        style={{
          alignItems: "center",
          gap: 14,
          width: "100%",
          textAlign: "left",
          padding: "15px 16px",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          color: "inherit",
          font: "inherit",
        }}
      >
        <span className="digest-icon" style={{ fontSize: 21, flexShrink: 0 }}>{CARD_ICON[card.key] ?? "📊"}</span>
        <span className="digest-mid" style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: "block", fontSize: 14, fontWeight: 700, color: "var(--tx)", letterSpacing: "-0.01em" }}>
            {card.title}
          </span>
          <span style={{ display: "block", marginTop: 5 }}>
            {toBullets(card.plain_english).map((b, i) => (
              <span
                key={i}
                style={{
                  display: "flex", gap: 7, fontSize: 12, color: "var(--dim)",
                  lineHeight: 1.5, marginTop: i ? 3 : 0, textAlign: "left",
                }}
              >
                <span aria-hidden style={{ color: acc, flexShrink: 0, lineHeight: 1.5 }}>•</span>
                <span style={{ flex: 1, minWidth: 0 }}>{b}</span>
              </span>
            ))}
          </span>
        </span>
        <span className="digest-stat" style={{ flexShrink: 0, textAlign: "right" }}>
          <span style={{ display: "block", fontFamily: "var(--mono)", fontSize: 13, color: "var(--green)" }}>
            {fmtMoney(card.dollar_value)}
          </span>
          <span style={{ display: "block", fontSize: 11.5, color: open ? "var(--dim)" : acc, marginTop: 3 }}>
            {open ? "hide receipts" : "see receipts →"}
          </span>
        </span>
      </button>

      {open && (
        <div style={{ borderTop: "0.5px solid var(--line)", padding: 16, background: "var(--s2)" }}>
          {state === "loading" && (
            <div className="status">
              <span className="d live" style={{ background: acc }} />
              Pulling the rows behind the number…
            </div>
          )}
          {state === "error" && (
            <OfflineNote>Couldn&apos;t load the receipts for this card. Retry in a moment.</OfflineNote>
          )}
          {state === "done" && receipts && (
            <>
              <MonoLabel>Receipts — the rows behind the number ({receipts.n} total)</MonoLabel>
              <RowsTable columns={receipts.columns} rows={receipts.rows} max={8} />
              <SqlToggle
                sql={receipts.sql}
                show={showSql}
                onToggle={() => setShowSql((s) => !s)}
                execMs={receipts.latency_ms}
              />
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Step 4 body ────────────────────────────────────────────────────────────────
const ASK_LIMIT = 5; // questions per visitor for this demo

function AskPanel({ apiBase, acc }: { apiBase: string; acc: string }) {
  const [question, setQuestion] = useState("");
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [data, setData] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [asked, setAsked] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const trimmed = question.trim();
  const valid = trimmed.length >= 3 && trimmed.length <= 300;
  const busy = status === "running";
  const limitReached = asked >= ASK_LIMIT;

  async function ask(qRaw: string) {
    const q = qRaw.trim();
    if (q.length < 3 || q.length > 300) {
      setError("Question must be between 3 and 300 characters.");
      setStatus("error");
      return;
    }
    if (asked >= ASK_LIMIT) {
      setError(`You've used all ${ASK_LIMIT} questions for this demo — refresh the page to ask more.`);
      setStatus("error");
      return;
    }
    setQuestion(q);
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    setStatus("running");
    setError(null);
    setData(null);
    try {
      const r = await api<AskResponse>(
        `${apiBase}/ask`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: q }),
        },
        ctrl.signal,
      );
      if (!r.ok || !r.data) {
        const friendly =
          r.status === 429
            ? "The demo is busy right now (rate limit). Give it a few seconds and try again."
            : `Couldn't reach the engine (HTTP ${r.status}).`;
        throw new Error(friendly);
      }
      setData(r.data);
      setStatus("done");
      // Only a real answered response spends one of the demo's questions — a clarify,
      // block, out-of-scope, failure or timeout doesn't burn the visitor's budget.
      if (r.data.status === "answered") setAsked((a) => a + 1);
    } catch (e) {
      setError(
        ctrl.signal.aborted
          ? "The engine took too long (real asks can take ~7s — please retry)."
          : e instanceof Error
            ? e.message
            : "Request failed.",
      );
      setStatus("error");
    } finally {
      clearTimeout(timer);
    }
  }

  return (
    <div>
      {/* pill chips (mockup .qchip) */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 13 }}>
        {CHIPS.map((c) => (
          <button
            key={c.q}
            type="button"
            className="qchip"
            disabled={busy || limitReached}
            onClick={() => ask(c.q)}
            style={{
              cursor: busy ? "not-allowed" : "pointer",
              opacity: busy ? 0.5 : 1,
              ...(c.kind === "redteam"
                ? { color: "var(--amber)", borderColor: "rgba(230,180,91,0.45)" }
                : null),
            }}
          >
            {c.kind === "redteam" ? "⛔ " : ""}
            {c.label}
          </button>
        ))}
      </div>

      {/* how to get an accurate answer — Margo answers from the shop's real tables */}
      <p style={{ fontSize: 12, lineHeight: 1.55, color: "var(--dim)", marginBottom: 10 }}>
        💡 <strong style={{ color: "var(--tx)" }}>For the best answer, be specific</strong> — name a metric and,
        if it matters, a timeframe (e.g. &ldquo;top 5 products by <em>profit</em> last month&rdquo;). The Retail Analyst Agent answers
        questions about this shop&apos;s products, categories, sales and stock — ask about those and it returns the
        exact rows behind the number.
      </p>

      <form
        style={{ display: "flex", gap: 9, flexWrap: "wrap" }}
        onSubmit={(e) => {
          e.preventDefault();
          if (valid && !busy) ask(trimmed);
        }}
      >
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={300}
          disabled={limitReached}
          placeholder={limitReached ? "Demo question limit reached — refresh to ask more" : "Ask about the shop…"}
          aria-label="Ask the Retail Analyst Agent about the shop"
          style={{ ...inputStyle, opacity: limitReached ? 0.5 : 1 }}
        />
        <button
          type="submit"
          className="btn pri"
          disabled={!valid || busy || limitReached}
          style={{ opacity: !valid || busy || limitReached ? 0.5 : 1, cursor: !valid || busy || limitReached ? "not-allowed" : "pointer" }}
        >
          {busy ? "Thinking…" : "Ask Retail Analyst Agent"}
        </button>
      </form>
      <div style={{ marginTop: 8, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--mut)" }}>
        {limitReached
          ? `${ASK_LIMIT} of ${ASK_LIMIT} demo questions used — refresh the page to start over.`
          : `${ASK_LIMIT - asked} of ${ASK_LIMIT} demo questions left.`}
      </div>

      <div aria-live="polite" style={{ marginTop: 15 }}>
        {status === "running" && (
          <div className="status">
            <span className="d live" style={{ background: acc }} />
            Drafting the query, running it read-only, checking the result… (real asks take ~7s)
          </div>
        )}
        {status === "error" && <OfflineNote>{error}</OfflineNote>}
        {status === "done" && data && <AnswerCard data={data} acc={acc} />}
      </div>
    </div>
  );
}

// One plain-English sentence saying what the answer is, built ONLY from the
// returned columns/rows — it never invents a number. A single value is stated
// outright; one row is read out; many rows give the count (the table is the proof).
function fmtVal(v: string | number | null): string {
  if (v == null) return "—";
  return typeof v === "number" ? v.toLocaleString() : v;
}
function plainAnswer(columns: string[], rows: (string | number | null)[][]): string {
  const n = rows.length;
  if (n === 0) return "Nothing matched that question — there are no rows to show.";
  const label = (i: number) => (columns[i] ?? `column ${i + 1}`).replace(/_/g, " ");
  if (n === 1 && columns.length === 1) return `${label(0)} is ${fmtVal(rows[0][0])}.`;
  if (n === 1) return columns.slice(0, 3).map((_, i) => `${label(i)} ${fmtVal(rows[0][i])}`).join(", ") + ".";
  return `${n.toLocaleString()} rows matched — the full list is below.`;
}

// Langfuse-style agent trace for the answered run (mirrors the Energy Modeller /
// AuditAgent TracePanel) — built from this run's real data: the schema link, the
// LLM SQL draft, the two safety boundaries, the read-only execute, the optional
// self-consistency vote, and the plain-English readback. Margo records every step
// in Langfuse (see the tech stack); this is that trace, in-page.
type MTraceKind = "llm" | "tool" | "gate";
function MargoTrace({ data, acc }: { data: AskResponse; acc: string }) {
  const rows = data.rows ?? [];
  const model = data.run_telemetry?.model ?? "the model";
  const c = data.consistency;
  const spans: { name: string; kind: MTraceKind; detail: string }[] = [
    { name: "tool · schema.link", kind: "tool", detail: "picked the tables & columns for your question" },
    { name: "llm · draft_sql", kind: "llm", detail: `${model} wrote the query · temp 0` },
    { name: "gate · safety.check", kind: "gate", detail: "AST allow-list · SELECT-only · read-only role → passed" },
    { name: "tool · db.execute", kind: "tool", detail: `${rows.length} row${rows.length === 1 ? "" : "s"} returned · read-only` },
    ...(c ? [{ name: "gate · self_consistency", kind: "gate" as MTraceKind, detail: `${c.n_agree}/${c.n_samples} samples agree` }] : []),
    { name: "tool · readback", kind: "tool", detail: "plain-English answer + receipts (the rows)" },
  ];
  const pill = (k: MTraceKind) =>
    k === "llm" ? { t: "LLM", c: "var(--amber)", b: "rgba(230,180,91,.12)" }
      : k === "gate" ? { t: "gate", c: "var(--green)", b: "rgba(91,227,139,.12)" }
        : { t: "tool", c: "var(--dim)", b: "var(--s3)" };
  return (
    <div style={{ marginTop: 12, borderRadius: 12, border: "0.5px solid var(--line2)", background: "var(--s1)", overflow: "hidden" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "11px 14px", borderBottom: "0.5px solid var(--line)" }}>
        <Activity className="h-3.5 w-3.5" style={{ color: acc }} />
        <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--dim)" }}>
          agent trace · this run · recorded in Langfuse
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
              <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)", textAlign: "right" }}>{s.detail}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Renders any of the 5 /ask statuses as its own card — never throws on null.
function AnswerCard({ data, acc }: { data: AskResponse; acc: string }) {
  const [showSql, setShowSql] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);

  if (data.status === "blocked") {
    return (
      <StatusCard tone="amber" icon="⛔" title="Refused" badge="destructive intent">
        <p style={cardBodyStyle}>{data.note ?? "Refused: destructive intent in request."}</p>
        <p style={{ ...cardBodyStyle, fontSize: 12, marginTop: 10 }}>
          The AST allow-list caught this before any SQL ran — no query was generated and the database
          was never touched. The Retail Analyst Agent refuses what it can&apos;t safely run, rather than obeying it.
        </p>
      </StatusCard>
    );
  }

  if (data.status === "out_of_scope") {
    return (
      <StatusCard tone="dim" icon="🛍️" title="Outside the shop's data" badge="out of scope">
        <p style={cardBodyStyle}>{data.note ?? "I can only answer questions about your shop's data."}</p>
      </StatusCard>
    );
  }

  if (data.status === "clarify") {
    return (
      <StatusCard tone="acc" icon="🤔" title="The Retail Analyst Agent needs a metric" badge="clarify" acc={acc}>
        <p style={cardBodyStyle}>{data.note ?? "That question is ambiguous — which measure did you mean?"}</p>
      </StatusCard>
    );
  }

  if (data.status === "failed") {
    return (
      <StatusCard tone="amber" icon="⚠️" title="Couldn't produce a query" badge="failed">
        <p style={cardBodyStyle}>
          {data.note ?? "The Retail Analyst Agent couldn't build a working query for that — try rephrasing."}
        </p>
      </StatusCard>
    );
  }

  // answered
  const columns = data.columns ?? [];
  const rows = data.rows ?? [];
  const c = data.consistency;
  const plain = plainAnswer(columns, rows);
  return (
    <div style={{ border: "0.5px solid var(--line)", background: "var(--s1)", borderRadius: 14, padding: 18 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
        <span style={{ color: "var(--green)", fontSize: 16 }}>✓</span>
        <strong style={{ fontSize: 15, color: "var(--tx)" }}>Answered</strong>
        <span style={badgeStyle(acc)}>{data.confidence} confidence</span>
        {c && (
          <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)" }}>
            self-consistency {c.n_agree}/{c.n_samples} agree
          </span>
        )}
        <span style={{ marginLeft: "auto", fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)" }}>
          {(data.latency_ms / 1000).toFixed(1)}s
        </span>
      </div>
      <p style={{ ...cardBodyStyle, marginTop: 12, color: "var(--tx)", fontWeight: 600 }}>{plain}</p>
      <div style={{ marginTop: 14 }}>
        <MonoLabel>Receipts — the rows behind the number</MonoLabel>
        <RowsTable columns={columns} rows={rows} max={10} />
      </div>
      {data.sql && (
        <SqlToggle sql={data.sql} show={showSql} onToggle={() => setShowSql((s) => !s)} />
      )}
      {/* Langfuse trace — same pattern as the agentic projects: open the per-step trace of this run, right before Results. */}
      <div style={{ marginTop: 14, marginBottom: 26 }}>
        <button
          onClick={() => setTraceOpen((o) => !o)}
          className="btn"
          style={{ display: "inline-flex", alignItems: "center", gap: 7 }}
          aria-expanded={traceOpen}
        >
          <Activity className="h-4 w-4" style={{ color: acc }} />
          {traceOpen ? "Hide the agent trace" : "Open the agent trace"}
          <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--dim)" }}>· Langfuse</span>
        </button>
        {traceOpen && <MargoTrace data={data} acc={acc} />}
      </div>
      <RunMetrics
        telemetry={data.run_telemetry}
        accent={acc}
        heading="Results"
      />
    </div>
  );
}

// ── Closer — bring your own file ──────────────────────────────────────────────
// Downloadable sample exports (in public/margo) — used by the one-click "Try a
// sample" buttons (fetched + uploaded) and the download links, so the file the
// visitor can grab is the exact file the button tests. Both parse via the real
// /byo/upload path. These are genuine-format exports for a DIFFERENT business than
// the scripted Wren demo — "Cadence Cyclery", an independent bike shop — so BYO
// proves Margo reads a real Square item-sales CSV and a real QuickBooks P&L Detail
// (account sections, "Total for …" subtotals, $1,234 / (parenthesised) amounts).
const SQUARE_SAMPLE_URL = "/margo/cadence-cyclery-square-item-sales.csv";
const QUICKBOOKS_SAMPLE_URL = "/margo/cadence-cyclery-quickbooks-pl.csv";

// Starter questions matched to what each file can actually answer — a Square
// item-sales export has products (item · qty · gross profit · margin), a
// QuickBooks P&L has accounting rows (income/expense accounts · amounts · dates),
// so asking a product question of a P&L (or vice-versa) is what triggers a clarify.
// Steering the demoer to file-appropriate questions keeps the answer path clean.
const BYO_STARTERS: Record<string, string[]> = {
  square: [
    "Top 5 products by profit",
    "Best-selling items by units sold",
    "Which category has the highest margin?",
  ],
  quickbooks: [
    "Biggest expense categories",
    "Monthly revenue trend",
    "Total income vs expenses",
  ],
};

function ByoCloser({ apiBase, acc }: { apiBase: string; acc: string }) {
  const [session, setSession] = useState<ByoSession | null>(null);
  const [uploadMsg, setUploadMsg] = useState<{ tone: "ok" | "warn"; text: string } | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const [bq, setBq] = useState("");
  const [bStatus, setBStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [bData, setBData] = useState<AskResponse | null>(null);
  const [remaining, setRemaining] = useState<number | null>(null);
  const [bErr, setBErr] = useState<string | null>(null);

  async function upload(content: string) {
    setUploading(true);
    setUploadMsg(null);
    setSession(null);
    setBData(null);
    setBStatus("idle");
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const r = await api<ByoSession & { detail?: string }>(
        `${apiBase}/byo/upload`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        },
        ctrl.signal,
      );
      if (r.status === 400 && r.data?.detail) {
        setUploadMsg({ tone: "warn", text: r.data.detail });
        return;
      }
      if (!r.ok || !r.data?.token) throw new Error("upload failed");
      setSession(r.data);
      setRemaining(r.data.queries_allowed);
      setUploadMsg({ tone: "ok", text: r.data.scope_note });
    } catch {
      setUploadMsg({
        tone: "warn",
        text: "Couldn't reach the Retail Analyst Agent to read that file. The upload talks to a real backend — retry in a moment.",
      });
    } finally {
      clearTimeout(timer);
      setUploading(false);
    }
  }

  async function trySample(url: string) {
    setUploading(true);
    try {
      const r = await fetch(url, { cache: "no-store" });
      if (!r.ok) throw new Error("sample fetch failed");
      await upload(await r.text());
    } catch {
      setUploadMsg({ tone: "warn", text: "Couldn't load the sample file from here — retry in a moment." });
      setUploading(false);
    }
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => upload(String(reader.result ?? ""));
    reader.readAsText(f);
    e.target.value = "";
  }

  async function byoAsk() {
    if (!session) return;
    const q = bq.trim();
    if (q.length < 3) return;
    setBStatus("running");
    setBData(null);
    setBErr(null);
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    try {
      const r = await api<AskResponse & { queries_remaining: number }>(
        `${apiBase}/byo/ask`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: session.token, question: q }),
        },
        ctrl.signal,
      );
      if (!r.ok || !r.data) {
        const friendly =
          r.status === 429
            ? "The demo is busy right now (rate limit). Give it a few seconds and try again."
            : r.status === 403
              ? "This file's question limit has been reached — upload a file again to start over."
              : `Couldn't reach the engine (HTTP ${r.status}).`;
        throw new Error(friendly);
      }
      setBData(r.data);
      if (typeof r.data.queries_remaining === "number") setRemaining(r.data.queries_remaining);
      setBStatus("done");
    } catch (e) {
      setBErr(e instanceof Error ? e.message : "Request failed.");
      setBStatus("error");
    } finally {
      clearTimeout(timer);
    }
  }

  async function close() {
    if (session) {
      try {
        await fetch(`${apiBase}/byo/close`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: session.token }),
        });
      } catch {
        /* best-effort */
      }
    }
    setSession(null);
    setUploadMsg(null);
    setBData(null);
    setBStatus("idle");
    setRemaining(null);
  }

  const outOfQueries = remaining != null && remaining <= 0;

  return (
    <div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "flex-start" }}>
        <button type="button" className="btn" disabled={uploading} onClick={() => fileRef.current?.click()}>
          {uploading ? "Reading…" : "Upload a CSV"}
        </button>
        {/* Each sample carries a download link so the demoer can open the exact file Margo queries. */}
        <div style={{ display: "inline-flex", flexDirection: "column", gap: 3, alignItems: "flex-start" }}>
          <button type="button" className="btn" disabled={uploading} onClick={() => trySample(SQUARE_SAMPLE_URL)}>
            Try a sample Square export
          </button>
          <a href={SQUARE_SAMPLE_URL} download style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: acc }}>
            ↓ view the .csv
          </a>
        </div>
        <div style={{ display: "inline-flex", flexDirection: "column", gap: 3, alignItems: "flex-start" }}>
          <button type="button" className="btn" disabled={uploading} onClick={() => trySample(QUICKBOOKS_SAMPLE_URL)}>
            Try a sample QuickBooks export
          </button>
          <a href={QUICKBOOKS_SAMPLE_URL} download style={{ fontFamily: "var(--mono)", fontSize: 10.5, color: acc }}>
            ↓ view the .csv
          </a>
        </div>
        {session && (
          <button type="button" className="btn" onClick={close} style={{ marginLeft: "auto" }}>
            Close &amp; delete
          </button>
        )}
        <input ref={fileRef} type="file" accept=".csv,text/csv" hidden onChange={onFile} />
      </div>

      {uploadMsg && (
        <div
          style={{
            marginTop: 12,
            borderRadius: 9,
            padding: "11px 14px",
            fontSize: 12,
            lineHeight: 1.6,
            color: "var(--tx)",
            border:
              uploadMsg.tone === "ok"
                ? "0.5px solid rgba(95,208,138,0.28)"
                : "0.5px solid rgba(230,180,91,0.38)",
            background: uploadMsg.tone === "ok" ? "rgba(95,208,138,0.10)" : "rgba(230,180,91,0.10)",
          }}
        >
          {uploadMsg.tone === "ok" ? "✓ " : "⚠️ "}
          {session && uploadMsg.tone === "ok" && (
            <b style={{ color: "var(--green)" }}>
              {session.format === "square" ? "Square export detected. " : "QuickBooks export detected. "}
            </b>
          )}
          {uploadMsg.text}
        </div>
      )}

      {session && (
        <div style={{ marginTop: 14 }}>
          {/* Starters matched to THIS file's columns — click to fill, so the demoer
              asks something the file can actually answer (no needless clarify). */}
          {(BYO_STARTERS[session.format] ?? []).length > 0 && (
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 10 }}>
              {(BYO_STARTERS[session.format] ?? []).map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setBq(s)}
                  disabled={outOfQueries}
                  style={{
                    fontFamily: "var(--mono)", fontSize: 12, color: acc,
                    background: `color-mix(in srgb, ${acc} 12%, transparent)`,
                    border: `0.5px solid color-mix(in srgb, ${acc} 40%, transparent)`,
                    borderRadius: 8, padding: "6px 11px", cursor: outOfQueries ? "not-allowed" : "pointer",
                    opacity: outOfQueries ? 0.5 : 1,
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          <form
            style={{ display: "flex", gap: 8, flexWrap: "wrap" }}
            onSubmit={(e) => {
              e.preventDefault();
              if (!outOfQueries && bStatus !== "running") byoAsk();
            }}
          >
            <input
              type="text"
              value={bq}
              onChange={(e) => setBq(e.target.value)}
              maxLength={300}
              disabled={outOfQueries}
              placeholder={
                outOfQueries
                  ? "Question limit reached for this file"
                  : session.format === "square"
                    ? "e.g. top 5 products by profit"
                    : "e.g. biggest expense categories"
              }
              aria-label="Ask about your uploaded file"
              style={{ ...inputStyle, opacity: outOfQueries ? 0.5 : 1 }}
            />
            <button
              type="submit"
              className="btn pri"
              disabled={outOfQueries || bStatus === "running" || bq.trim().length < 3}
              style={{
                opacity: outOfQueries || bStatus === "running" || bq.trim().length < 3 ? 0.5 : 1,
                cursor: outOfQueries ? "not-allowed" : "pointer",
              }}
            >
              {bStatus === "running" ? "Thinking…" : "Ask"}
            </button>
          </form>
          {remaining != null && (
            <div style={{ marginTop: 8, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--mut)" }}>
              {remaining} of {session.queries_allowed} questions left on this file
            </div>
          )}
          <div aria-live="polite" style={{ marginTop: 12 }}>
            {bStatus === "running" && (
              <div className="status">
                <span className="d live" style={{ background: acc }} />
                Querying your file read-only…
              </div>
            )}
            {bStatus === "error" && <OfflineNote>{bErr}</OfflineNote>}
            {bStatus === "done" && bData && <AnswerCard data={bData} acc={acc} />}
          </div>
        </div>
      )}

      <div style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--mut)", marginTop: 12, lineHeight: 1.6 }}>
        🔐 Processed in-session · not stored · deleted when you close · 3 questions per file.
      </div>
    </div>
  );
}

// ── Shared bits ───────────────────────────────────────────────────────────────
function MonoLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        marginBottom: 8,
        fontFamily: "var(--mono)",
        fontSize: 11.5,
        textTransform: "uppercase",
        letterSpacing: "0.07em",
        color: "var(--mut)",
      }}
    >
      {children}
    </div>
  );
}

function RowsTable({
  columns,
  rows,
  max,
}: {
  columns: string[];
  rows: (string | number | null)[][];
  max: number;
}) {
  const shown = rows.slice(0, max);
  const extra = rows.length - shown.length;
  // Receipts render on a white "paper" surface (the rows are the proof) — light theme
  // colours (from SQL_LIGHT) so they read like a real report, matching the query block.
  return (
    <div style={{ overflowX: "auto", border: `1px solid ${SQL_LIGHT.border}`, borderRadius: 9, background: SQL_LIGHT.bg }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12, textAlign: "left" }}>
        <thead>
          <tr style={{ background: "#f3f4f6" }}>
            {columns.map((c) => (
              <th
                key={c}
                style={{
                  padding: "8px 11px",
                  fontFamily: "var(--mono)",
                  fontSize: 11.5,
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                  color: SQL_LIGHT.punct,
                  borderBottom: `1px solid ${SQL_LIGHT.border}`,
                }}
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((r, ri) => (
            <tr key={ri} style={{ borderBottom: `1px solid ${SQL_LIGHT.border}` }}>
              {r.map((cell, ci) => (
                <td key={ci} style={{ padding: "8px 11px", color: cell === null ? "#8a8f98" : SQL_LIGHT.text }}>
                  {fmtCell(cell)}
                </td>
              ))}
            </tr>
          ))}
          {extra > 0 && (
            <tr>
              <td
                colSpan={columns.length || 1}
                style={{ padding: "8px 11px", color: "#8a8f98", fontFamily: "var(--mono)", fontSize: 11.5, background: SQL_LIGHT.bg }}
              >
                + {extra.toLocaleString("en-US")} more row{extra === 1 ? "" : "s"} in the dataset
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

// ── Plain-English → bullet points (digest card descriptions) ────────────────────
// The engine returns each insight as authored prose ("[finding] — [action]." with
// one or two sentences). For scannability we split it into a "finding / so-what"
// bullet list: break on the em-dash clause and on sentence boundaries, tidy each.
function toBullets(text: string): string[] {
  return (text || "")
    .split(/\s+—\s+|(?<=\.)\s+(?=[A-Z(])/)
    .map((s) => s.trim().replace(/\.$/, ""))
    .filter(Boolean)
    .map((s) => s.charAt(0).toUpperCase() + s.slice(1));
}

// ── SQL pretty-printer + syntax highlighter ─────────────────────────────────────
// The query the LLM drafts arrives on one line; we put each major clause on its own
// line and indent ON/AND/OR, then colour keywords / functions / strings / numbers so
// the "code wrote this, not me typing prose" point reads at a glance.
const SQL_KW = new Set(
  "SELECT FROM WHERE GROUP ORDER BY HAVING LIMIT OFFSET JOIN LEFT RIGHT INNER OUTER FULL CROSS ON AND OR NOT NULL IS IN AS LIKE BETWEEN UNION ALL DISTINCT CASE WHEN THEN ELSE END ASC DESC EXISTS".split(" "),
);
const SQL_FN = new Set(
  "COUNT SUM AVG MIN MAX ROUND COALESCE CAST ABS DATE STRFTIME LOWER UPPER LENGTH SUBSTR".split(" "),
);

function formatSql(raw: string): string {
  let s = (raw || "").replace(/\s+/g, " ").trim();
  s = s.replace(
    /\s+\b(FROM|LEFT JOIN|RIGHT JOIN|INNER JOIN|FULL JOIN|CROSS JOIN|JOIN|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|UNION ALL|UNION)\b/gi,
    "\n$1",
  );
  s = s.replace(/\s+\b(ON|AND|OR)\b/gi, "\n  $1");
  return s;
}

// Light-theme SQL palette — the query renders on a white card, so colours are picked
// for contrast on white (all ≥ 4.5:1), not the dark surface used elsewhere.
const SQL_LIGHT = {
  bg: "#ffffff",
  text: "#1f2430", // default identifiers
  keyword: "#0b62d6", // blue, bold
  fn: "#8250df", // purple
  string: "#0a7d33", // green
  number: "#0550ae", // deep blue
  punct: "#57606a", // grey
  border: "#e2e5ea",
};

function highlightSql(formatted: string): ReactNode[] {
  const re = /('(?:[^']|'')*')|(\d+(?:\.\d+)?)|([A-Za-z_][A-Za-z0-9_]*)|([(),.*=<>!+\-/|]+)|(\s+)/g;
  const out: ReactNode[] = [];
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(formatted)) !== null) {
    const [, str, num, word, punct, ws] = m;
    if (str !== undefined) out.push(<span key={i} style={{ color: SQL_LIGHT.string }}>{str}</span>);
    else if (num !== undefined) out.push(<span key={i} style={{ color: SQL_LIGHT.number }}>{num}</span>);
    else if (word !== undefined) {
      const up = word.toUpperCase();
      if (SQL_KW.has(up)) out.push(<span key={i} style={{ color: SQL_LIGHT.keyword, fontWeight: 700 }}>{word}</span>);
      else if (SQL_FN.has(up)) out.push(<span key={i} style={{ color: SQL_LIGHT.fn }}>{word}</span>);
      else out.push(<span key={i}>{word}</span>);
    } else if (punct !== undefined) out.push(<span key={i} style={{ color: SQL_LIGHT.punct }}>{punct}</span>);
    else out.push(<span key={i}>{ws}</span>);
    i++;
  }
  return out;
}

function SqlToggle({
  sql,
  show,
  onToggle,
  execMs,
}: {
  sql: string;
  show: boolean;
  onToggle: () => void;
  execMs?: number; // real SQL execution time (ms) — shown only where it's the query's own runtime
}) {
  return (
    <div style={{ marginTop: 12 }}>
      <button
        type="button"
        className="btn"
        onClick={onToggle}
        aria-expanded={show}
        style={{ fontFamily: "var(--mono)", fontSize: 11.5, padding: "7px 12px" }}
      >
        {show ? "Hide query" : "</> Show query"}
      </button>
      {show && (
        <>
          <pre
            style={{
              marginTop: 9,
              overflowX: "auto",
              background: SQL_LIGHT.bg,
              border: `1px solid ${SQL_LIGHT.border}`,
              borderRadius: 8,
              padding: 14,
              fontFamily: "var(--mono)",
              fontSize: 12,
              lineHeight: 1.7,
              color: SQL_LIGHT.text,
              whiteSpace: "pre",
              tabSize: 2,
            }}
          >
            {highlightSql(formatSql(sql))}
          </pre>
          <div style={{ marginTop: 8, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--mut)", lineHeight: 1.7 }}>
            ✓ passed the <b style={{ color: "var(--green)" }}>AST allow-list</b> · ✓ ran under the{" "}
            <b style={{ color: "var(--green)" }}>read-only role</b> · code computed the numbers from the
            rows — the LLM only drafted the query
            {typeof execMs === "number" ? ` (query ran in ${Math.round(execMs)} ms)` : ""}.
          </div>
        </>
      )}
    </div>
  );
}

function StatusCard({
  tone,
  icon,
  title,
  badge,
  acc,
  children,
}: {
  tone: "amber" | "dim" | "acc";
  icon: string;
  title: string;
  badge: string;
  acc?: string;
  children: React.ReactNode;
}) {
  const color = tone === "amber" ? "var(--amber)" : tone === "acc" ? acc ?? "var(--acc)" : "var(--dim)";
  const border = tone === "amber" ? "rgba(230,180,91,0.4)" : tone === "acc" ? "var(--line2)" : "var(--line)";
  const bg = tone === "amber" ? "rgba(230,180,91,0.06)" : "var(--s1)";
  return (
    <div style={{ border: `0.5px solid ${border}`, background: bg, borderRadius: 14, padding: 18 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 17 }}>{icon}</span>
        <strong style={{ fontSize: 15, color: "var(--tx)" }}>{title}</strong>
        <span
          style={{
            fontFamily: "var(--mono)",
            fontSize: 11.5,
            textTransform: "uppercase",
            letterSpacing: "0.07em",
            color,
            background: tone === "amber" ? "rgba(230,180,91,0.15)" : "var(--s3)",
            borderRadius: 6,
            padding: "2px 8px",
          }}
        >
          {badge}
        </span>
      </div>
      {children}
    </div>
  );
}

function OfflineNote({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        border: "0.5px solid rgba(230,180,91,0.4)",
        background: "rgba(230,180,91,0.08)",
        borderRadius: 12,
        padding: "12px 16px",
        fontSize: 13,
        lineHeight: 1.6,
        color: "var(--dim)",
      }}
    >
      <strong style={{ color: "var(--amber)" }}>Heads up.</strong> {children}
    </div>
  );
}

// ── shared inline style fragments ──────────────────────────────────────────────
const cardBodyStyle: React.CSSProperties = {
  marginTop: 12,
  fontSize: 14,
  lineHeight: 1.65,
  color: "var(--dim)",
};
const inputStyle: React.CSSProperties = {
  minWidth: 0,
  flex: "1 1 240px",
  background: "var(--s1)",
  border: "0.5px solid var(--line)",
  borderRadius: 10,
  padding: "11px 14px",
  color: "var(--tx)",
  fontSize: 14,
  fontFamily: "inherit",
  outline: "none",
};
const badgeStyle = (acc: string): React.CSSProperties => ({
  fontFamily: "var(--mono)",
  fontSize: 11.5,
  textTransform: "uppercase",
  letterSpacing: "0.07em",
  color: acc,
  background: "var(--s3)",
  borderRadius: 6,
  padding: "2px 8px",
});
