// Shared per-run telemetry strip — cost · tokens · latency for the run the visitor
// just executed. Fed by the backend's `run_telemetry` object (the same shape across
// Iris/Margo/Vera): { model, tokens, llm_calls, cost_usd, latency_s }. Latency is
// always real wall-clock; tokens/cost are real when a live model ran, and show "—"
// with an honest caption on a path that answered without calling the model.
//
// With `heading` set, this renders as the demo's **Results** section — a big bold
// heading + metric cards, matching the Energy Modeller & AuditAgent Results design
// (display heading 30px/700 · cards: 26px accent number + uppercase mono label).
import type { ReactNode } from "react";
import { fmtAud, FX_NOTE } from "@/lib/fx";

export type RunTelemetry = {
  model?: string | null;
  tokens?: number | null;
  llm_calls?: number | null;
  cost_usd?: number | null;
  latency_s?: number | null;
};

export function RunMetrics({
  telemetry,
  accent = "var(--accent, #4ea1ff)",
  heading,
  subtitle,
  scope = "this run",
  badge,
}: {
  telemetry: RunTelemetry | null | undefined;
  accent?: string;
  /** When set, render a "Results" section heading above the cards (matches AEM/AuditAgent). */
  heading?: string;
  /** Optional mono caption beside the heading. */
  subtitle?: string;
  /** What the numbers cover, e.g. "this run" (default) or "this conversation". */
  scope?: string;
  /** Optional accuracy/quality trust-chip rendered below the heading (a fixed eval
   *  number, not per-run). E.g. "84.4% execution accuracy · retail holdout". */
  badge?: ReactNode;
}) {
  if (!telemetry) return null;
  const live = telemetry.tokens != null;
  // Cost is measured in USD (providers bill in USD) and shown in AUD — see lib/fx.ts.
  const cost = fmtAud(telemetry.cost_usd);
  const tokens = telemetry.tokens != null ? telemetry.tokens.toLocaleString() : "—";
  const latency = telemetry.latency_s != null ? `${telemetry.latency_s.toFixed(1)}s` : "—";
  const model = telemetry.model || "model";
  const calls = telemetry.llm_calls ?? null;

  const cells: { num: string; label: string; sub: string }[] = [
    {
      num: cost,
      label: `cost of ${scope} (AUD)`,
      sub: live ? `measured · ${scope} · ${model} · ${FX_NOTE}` : `no live model call ${scope}`,
    },
    {
      num: latency,
      label: `latency (${scope})`,
      sub: "real wall-clock · end-to-end",
    },
    {
      num: tokens,
      label: "LLM tokens used",
      sub: live
        ? `measured · ${scope}${calls ? ` · ${calls} call${calls === 1 ? "" : "s"}` : ""}`
        : `no LLM tokens ${scope}`,
    },
  ];

  return (
    <div style={heading ? { marginTop: 4 } : undefined}>
      {heading && (
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            gap: 12,
            flexWrap: "wrap",
            marginBottom: 14,
          }}
        >
          <h3
            style={{
              fontFamily: "var(--disp)",
              fontSize: "var(--fs-display-md, 30px)",
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color: "var(--tx, #f2f3f5)",
              margin: 0,
            }}
          >
            {heading}
          </h3>
          {subtitle && (
            <span style={{ fontFamily: "var(--mono)", fontSize: "var(--fs-label-sm, 11.5px)", color: "var(--dim, #9a9a9a)" }}>
              {subtitle}
            </span>
          )}
        </div>
      )}
      {badge && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 14 }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              borderRadius: 8,
              padding: "5px 10px",
              fontFamily: "var(--mono)",
              fontSize: "var(--fs-label-sm, 11.5px)",
              color: accent,
              border: `0.5px solid ${accent}55`,
              background: `${accent}14`,
            }}
          >
            ✓ {badge}
          </span>
        </div>
      )}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
          gap: 1,
          overflow: "hidden",
          borderRadius: 12,
          marginTop: heading ? 0 : 12,
          // Grid gap lines take the lane hue on case pages (--line-lane-grid, set on
          // .case-page); fall back to neutral --line anywhere the token isn't scoped.
          border: "0.5px solid var(--line-lane-grid, var(--line, #2a2a2a))",
          background: "var(--line-lane-grid, var(--line, #2a2a2a))",
        }}
      >
        {cells.map((c) => (
          <div key={c.label} style={{ background: "#22242b", padding: 16 }}>
            <div style={{ fontFamily: "var(--disp)", fontWeight: 600, fontSize: 26, letterSpacing: "-0.02em", color: accent, lineHeight: 1.1 }}>{c.num}</div>
            <div style={{ marginTop: 6, fontFamily: "var(--mono)", fontSize: "var(--fs-label-sm, 11.5px)", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--dim, #9a9a9a)" }}>{c.label}</div>
            <p style={{ margin: "8px 0 0", fontSize: "var(--fs-label-sm, 11.5px)", color: "var(--dim, #9a9a9a)" }}>{c.sub}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
