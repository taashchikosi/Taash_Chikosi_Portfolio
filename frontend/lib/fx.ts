// Currency for the Results tables.
//
// LLM providers (Anthropic, DeepSeek) bill in USD, so every backend measures cost in USD
// (run_telemetry.cost_usd, per-provider token pricing). This portfolio is AU-facing, so the
// Results tables display the LLM cost converted to AUD at a fixed, documented rate. It's an
// approximation (not live FX) — surfaced in the card caption — and the ONE place the rate
// lives, so every project stays consistent. Update USD_TO_AUD here to re-price everywhere.
export const USD_TO_AUD = 1.53; // ≈ AUD/USD 0.65 (mid-2026); update as the rate moves.

export const FX_NOTE = `AUD @ ${USD_TO_AUD}/USD`;

// Format a USD amount as AUD. Adaptive precision: sub-cent runs would read as "A$0.0000"
// at 4dp, so show 2 significant figures below 1¢ to keep the real (tiny) cost legible.
export function fmtAud(usd: number | null | undefined): string {
  if (usd == null) return "—";
  const a = usd * USD_TO_AUD;
  return a >= 0.01 ? `A$${a.toFixed(4)}` : `A$${a.toPrecision(2)}`;
}
